"""
ffmpeg_pipeline.py - Direct FFmpeg pipeline for video clip processing.

Replaces MoviePy's frame-by-frame Python processing with FFmpeg CLI calls.
FFmpeg handles crop, scale, overlay, subtitle burn-in, and encoding
in a single C-optimized, multi-threaded pass.
"""
import os
import re
import time
import random
import tempfile
import subprocess
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed

from .ffmpeg_filter_builder import (
    get_preset, build_encoding_args, overlay_filter, subtitle_vf,
    pad_filter, drawtext_filter, build_filter_complex,
    watermark_position_to_xy,
)
from .ffmpeg_crop import compute_static_crop


def _get_ffmpeg_path():
    """Get FFmpeg executable path."""
    try:
        from services.core.binary_manager import get_ffmpeg_path
        return get_ffmpeg_path()
    except ImportError:
        return 'ffmpeg'


def _get_ffprobe_path():
    """Get ffprobe executable path (same dir as ffmpeg)."""
    ffmpeg_path = _get_ffmpeg_path()
    if ffmpeg_path == 'ffmpeg':
        return 'ffprobe'
    # Replace ffmpeg with ffprobe in the same directory
    ffmpeg_dir = os.path.dirname(ffmpeg_path)
    return os.path.join(ffmpeg_dir, 'ffprobe')


def _probe_video_dimensions(video_path: str) -> Tuple[int, int]:
    """Probe actual video resolution.

    Tries: 1) ffprobe, 2) ffmpeg -i parsing, 3) MoviePy.
    Falls back to (1920, 1080).
    """
    # Method 1: ffprobe
    try:
        ffprobe = _get_ffprobe_path()
        if os.path.isfile(ffprobe) or ffprobe == 'ffprobe':
            cmd = [
                ffprobe, '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height',
                '-of', 'csv=p=0',
                video_path,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(',')
                if len(parts) >= 2:
                    w, h = int(parts[0]), int(parts[1])
                    if w > 0 and h > 0:
                        _log(f"[Probe] ffprobe: {w}x{h}")
                        return w, h
    except Exception:
        pass

    # Method 2: ffmpeg -i (parse stderr for resolution)
    try:
        ffmpeg = _get_ffmpeg_path()
        cmd = [ffmpeg, '-hide_banner', '-i', video_path]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )
        # ffmpeg -i exits with code 1 but prints info to stderr
        stderr = result.stderr or ''
        # Match patterns like "1920x1080" or "1280x720"
        match = re.search(r'(\d{2,5})x(\d{2,5})', stderr)
        if match:
            w, h = int(match.group(1)), int(match.group(2))
            if w > 0 and h > 0:
                _log(f"[Probe] ffmpeg -i: {w}x{h}")
                return w, h
    except Exception:
        pass

    # Method 3: MoviePy (always available since we use it for face tracking)
    try:
        from moviepy import VideoFileClip
        video = VideoFileClip(video_path)
        w, h = int(video.w), int(video.h)
        video.close()
        if w > 0 and h > 0:
            _log(f"[Probe] MoviePy: {w}x{h}")
            return w, h
    except Exception:
        pass

    _log(f"[WARN] All probe methods failed for {video_path}, using 1920x1080")
    return 1920, 1080


def _get_codec():
    """Get optimal video codec."""
    from services.media.video_encoder import get_optimal_video_codec
    return get_optimal_video_codec()


def _analyze_face_positions(clip_path: str, start: float, end: float,
                            enable_tracking: bool = True,
                            num_samples: int = 10,
                            check_cancelled=None) -> dict:
    """Run face analysis on a video clip using OpenCV."""
    from moviepy import VideoFileClip
    from services.media.face_detector import analyze_face_positions

    video = None
    try:
        video = VideoFileClip(clip_path)
        clip = video.subclipped(start, end)
        result = analyze_face_positions(
            clip, num_samples=num_samples,
            enable_tracking=enable_tracking,
            check_cancelled=check_cancelled,
        )
        return result
    except Exception as e:
        _log(f"[WARN] Face analysis failed: {e}")
        return None
    finally:
        if video:
            try:
                video.close()
            except Exception:
                pass


def _render_hook_png(preset: str, hook_styles: dict,
                     video_width: int, video_height: int,
                     duration: float, config=None):
    """Render hook overlay to PNG. Returns (path, position) or None."""
    try:
        if preset == 'preset-2':
            from services.media.subtitle.preset2_hook import _render_preset2_hook
            return _render_preset2_hook(config, hook_styles, video_width, video_height, duration)
        elif preset == 'preset-3':
            from services.media.subtitle.preset3_hook import _render_preset3_hook
            return _render_preset3_hook(config, hook_styles, video_width, video_height, duration)
        elif preset == 'preset-4':
            from services.media.subtitle.preset4_hook import _render_preset4_hook
            return _render_preset4_hook(config, hook_styles, video_width, video_height, duration)
        else:  # preset-1 (default)
            from services.media.video_cutter import create_viral_hook_overlay
            heading = hook_styles.get('headline', '')
            subheading = hook_styles.get('subheading', '')
            return create_viral_hook_overlay(
                heading, subheading,
                duration=duration, width=video_width,
                style_config=hook_styles, return_png=True)
    except Exception as e:
        _log(f"[WARN] Hook render failed: {e}")
        return None


def _generate_subtitle_ass(phrase_timings, clip_start: float, clip_end: float,
                           video_size: Tuple[int, int],
                           style_config: dict,
                           hook_duration: Optional[float] = None,
                           suppress_during_hook: bool = False) -> Optional[str]:
    """Generate ASS subtitle file. Returns path or None."""
    from services.media.subtitle.ass_generator import generate_ass_file

    tmp_dir = tempfile.mkdtemp(prefix='zenclip_subs_')
    ass_path = os.path.join(tmp_dir, 'subtitles.ass')

    # Filter out phrases during hook intro if suppress_during_hook.
    # hook_duration is relative to clip start (e.g., 3.5s), but phrase_timings
    # use absolute timestamps. Convert to absolute for comparison.
    timings = phrase_timings
    if suppress_during_hook and hook_duration:
        hook_end_absolute = clip_start + hook_duration
        timings = [p for p in phrase_timings if p.get('start', 0) >= hook_end_absolute]

    if not timings:
        return None

    success = generate_ass_file(
        ass_path, timings, clip_start, clip_end,
        video_size, style_config=style_config)

    # Debug: log first 30 lines of ASS file for troubleshooting
    if success and ass_path:
        try:
            with open(ass_path, 'r', encoding='utf-8') as f:
                ass_lines = f.readlines()[:30]
            _log(f"[DEBUG] ASS file preview ({len(ass_lines)} lines):")
            for i, line in enumerate(ass_lines[:15]):
                _log(f"  {i+1}: {line.rstrip()}")
            if len(ass_lines) > 15:
                _log(f"  ... ({len(ass_lines) - 15} more header lines)")
        except Exception:
            pass

    return ass_path if success else None


def parse_ffmpeg_progress(stderr_line: str, clip_duration: float) -> Optional[float]:
    """Parse FFmpeg stderr line for progress. Returns 0.0-1.0 or None."""
    match = re.search(r'time=(\d+):(\d+):(\d+)(?:\.(\d+))?', stderr_line)
    if not match:
        return None

    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    frac = match.group(4)
    ms = int(frac) / (10 ** len(frac)) if frac else 0.0

    current_time = hours * 3600 + minutes * 60 + seconds + ms
    if clip_duration <= 0:
        return None
    return min(1.0, current_time / clip_duration)


def _position_to_ffmpeg(pos_tuple, video_width, video_height):
    """Convert ('center', y_value) to FFmpeg overlay x:y coordinates.

    For x='center': calculates (video_width - overlay_width) / 2.
    For y: if numeric, use as-is; if 'top'/'center'/'bottom', calculate position.
    """
    if pos_tuple is None:
        return 0, 0

    x_str, y_val = pos_tuple

    # X: 'center' means horizontally centered
    # We can't know overlay width here, so use expression
    if x_str == 'center':
        x = 0  # Will be handled by overlay=x expression
    else:
        x = int(x_str)

    # Y: handle named positions
    if isinstance(y_val, (int, float)):
        y = int(y_val)
    elif isinstance(y_val, str):
        if y_val == 'top':
            y = 0
        elif y_val == 'center':
            y = video_height // 4  # Upper-center area for hooks
        elif y_val == 'bottom':
            y = video_height // 2  # Lower area
        else:
            y = 0
    else:
        y = 0

    return x, y


def run_ffmpeg_clip(
    input_path: str,
    output_path: str,
    start_time: float,
    duration: float,
    target_w: int,
    target_h: int,
    crop_rect=None,
    hook_png_path: Optional[str] = None,
    hook_position: tuple = None,
    hook_duration: float = 3.5,
    hook_full_duration: bool = False,
    ass_path: Optional[str] = None,
    fonts_dir: Optional[str] = None,
    canvas_w: Optional[int] = None,
    canvas_h: Optional[int] = None,
    watermark_image: Optional[str] = None,
    watermark_text: Optional[str] = None,
    watermark_config: Optional[dict] = None,
    quality_preset: str = 'balanced',
    progress_callback: Optional[Callable[[float], None]] = None,
    check_cancelled: Optional[Callable[[], bool]] = None,
    randomize_metadata: bool = False,
) -> Optional[str]:
    """Process a single clip via FFmpeg.

    Returns output file path on success, None on failure.
    """
    ffmpeg = _get_ffmpeg_path()
    preset = get_preset(quality_preset)
    codec_name, codec_params = _get_codec()

    encoding_preset = preset['encoding_preset']
    crf = preset['crf']

    # Build inputs
    inputs = ['-y', '-ss', str(start_time), '-t', str(duration), '-i', input_path]

    if hook_png_path:
        inputs.extend(['-i', hook_png_path])

    if watermark_image:
        inputs.extend(['-i', watermark_image])

    # Build filter chain
    filters = []
    current_label = '0:v'
    step_num = 0

    # Step 1: Crop + Scale (use lanczos for best quality when upscaling)
    if crop_rect:
        step_label = f'v{step_num}'
        filters.append(
            f'[{current_label}]crop={crop_rect.width}:{crop_rect.height}:'
            f'{crop_rect.x}:{crop_rect.y},scale={target_w}:{target_h}:flags=lanczos[{step_label}]'
        )
        current_label = step_label
        step_num += 1
    else:
        # No crop — just scale
        step_label = f'v{step_num}'
        filters.append(f'[{current_label}]scale={target_w}:{target_h}:flags=lanczos[{step_label}]')
        current_label = step_label
        step_num += 1

    # Step 2: Canvas padding (if needed)
    if canvas_w and canvas_h and (canvas_w != target_w or canvas_h != target_h):
        pad_label = f'v{step_num}'
        filters.append(pad_filter(canvas_w, canvas_h, pad_label, current_label))
        current_label = pad_label
        step_num += 1

    # Step 3: Hook overlay
    if hook_png_path:
        hook_label = f'v{step_num}'
        hx, hy = _position_to_ffmpeg(hook_position, target_w, target_h)
        enable = None if hook_full_duration else f"between(t,0,{hook_duration})"
        # Use (W-w)/2 for horizontal centering if hook_position x is 'center'
        if hook_position and hook_position[0] == 'center':
            hx_expr = '(W-w)/2'
        else:
            hx_expr = str(hx)
        filters.append(overlay_filter(current_label, '1:v', hx_expr, hy, hook_label, enable_expr=enable))
        current_label = hook_label
        step_num += 1

    # Step 4: Watermark
    if watermark_image:
        wm_label = f'v{step_num}'
        wm_config = watermark_config or {}
        wm_opacity = wm_config.get('opacity', 0.3)
        # Resolve position from string preset (e.g. 'bottom_right') or x,y dict
        wm_pos = wm_config.get('position', 'bottom_right')
        wm_x, wm_y = watermark_position_to_xy(wm_pos)
        # For image overlay use pixel values for expressions that reference overlay dims
        filters.append(
            f'[{current_label}][2:v]overlay={wm_x}:{wm_y}:'
            f'format=auto:alpha={wm_opacity}[{wm_label}]'
        )
        current_label = wm_label
        step_num += 1
    elif watermark_text:
        wm_config = watermark_config or {}
        wm_opacity = wm_config.get('opacity', 0.3)
        # watermark_size: scale factor (0.0-1.0) → fontsize relative to video height
        wm_size = wm_config.get('fontsize', 24)
        if wm_size <= 1:
            # Treat as scale factor — convert to pixel fontsize
            wm_fontsize = max(12, int(target_h * wm_size * 0.5))
        else:
            wm_fontsize = int(wm_size)
        # Resolve position from string preset (e.g. 'bottom_right') or x,y dict
        wm_pos = wm_config.get('position', 'bottom_right')
        wm_x, wm_y = watermark_position_to_xy(wm_pos)
        # Resolve font file path
        wm_font_path = None
        wm_font_name = watermark_config.get('font') if isinstance(watermark_config, dict) else None
        if wm_font_name:
            try:
                from services.media.subtitle.utils.fonts import FontManager
                fm = FontManager()
                resolved = fm.get_font_path(wm_font_name)
                if resolved:
                    wm_font_path = resolved.replace('\\', '/').replace(':', '\\:')
            except Exception:
                pass
        wm_label = f'v{step_num}'
        filters.append(
            f"[{current_label}]{drawtext_filter(watermark_text, wm_x, wm_y, wm_fontsize, wm_opacity, font=wm_font_path)}[{wm_label}]"
        )
        current_label = wm_label
        step_num += 1

    # Build FFmpeg command
    # Strategy: use -filter_complex for all video processing (crop, overlay, etc.)
    # then pipe through a second FFmpeg pass for subtitles if needed.
    # OR: use a single-pass approach where filter_complex handles everything.
    # FFmpeg's subtitles filter CAN be used in filter_complex but only on unlabeled inputs.
    # So we do TWO passes when subtitles are needed with filter_complex.

    cmd = [ffmpeg] + inputs

    has_filters = len(filters) > 0

    if has_filters:
        filter_str = build_filter_complex(filters)
        cmd.extend(['-filter_complex', filter_str])

    # Subtitles: use -vf when no filter_complex, or embed in 2nd pass
    need_subtitle_pass = False
    if ass_path and not has_filters:
        # Simple case: no filter_complex, just -vf subtitles
        sub_str = subtitle_vf(ass_path, fonts_dir)
        cmd.extend(['-vf', sub_str])
    elif ass_path and has_filters:
        # Two-pass: first pass does filter_complex, second adds subtitles
        need_subtitle_pass = True

    # Metadata
    if randomize_metadata:
        import uuid as _uuid
        cmd.extend([
            '-metadata', f'comment=ID:{_uuid.uuid4()}',
            '-metadata', 'description=AutoClip',
            '-metadata', f'title=Clip_{_uuid.uuid4().hex[:8]}',
        ])
    else:
        cmd.extend(['-metadata', 'comment=', '-metadata', 'description='])

    # Encoding args
    cmd.extend(build_encoding_args(codec_name, encoding_preset, crf))

    # Map final video stream + audio
    if has_filters:
        cmd.extend(['-map', f'[{current_label}]'])
    cmd.extend(['-map', '0:a'])

    # Output: if two-pass needed, first pass goes to temp file
    if need_subtitle_pass:
        temp_output = output_path.replace('.mp4', '_temp.mp4')
        cmd.append(temp_output)
    else:
        cmd.append(output_path)

    _log(f"[FFmpeg] Processing clip → {os.path.basename(output_path)}")
    if need_subtitle_pass:
        _log(f"[FFmpeg] Two-pass mode: crop/overlay pass + subtitle pass")
    _log(f"[FFmpeg] FULL CMD: {' '.join(cmd)}")

    try:
        proc = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            universal_newlines=True,
        )

        # Collect all stderr for error reporting while parsing progress
        all_stderr = []
        while True:
            if check_cancelled and check_cancelled():
                proc.kill()
                proc.wait()
                return None

            line = proc.stderr.readline()
            if not line:
                break

            all_stderr.append(line)
            if progress_callback and 'time=' in line:
                pct = parse_ffmpeg_progress(line, duration)
                if pct is not None:
                    progress_callback(pct)

        proc.wait()

        if proc.returncode != 0:
            stderr_text = ''.join(all_stderr[-20:])  # Last 20 lines
            _log(f"[FFmpeg] Error (exit {proc.returncode})")
            _log(f"[FFmpeg] STDERR (last 20 lines):\n{stderr_text}")
            # Retry with libx264 if hardware codec failed
            if codec_name != 'libx264':
                _log("[FFmpeg] Retrying with libx264...")
                return _retry_with_libx264(cmd, codec_name, encoding_preset, crf,
                                           output_path, duration, progress_callback,
                                           check_cancelled)
            return None

        # Two-pass subtitle mode
        if need_subtitle_pass:
            actual_output = temp_output
            if not (os.path.exists(actual_output) and os.path.getsize(actual_output) > 0):
                _log(f"[FFmpeg] First pass output missing: {actual_output}")
                return None

            # Second pass: burn in subtitles
            _log(f"[FFmpeg] Second pass: burning subtitles")

            # CRITICAL: Windows absolute paths with drive letters (C:) break
            # FFmpeg's filter parser because ':' is the option separator.
            # ALSO: topic names can contain ':', "'", and other chars that break
            # FFmpeg's option parser.
            # Solution: use a safe, simple filename (subs.ass) with cwd=clip_dir.
            import shutil
            clip_dir = os.path.dirname(output_path)
            # Use a fixed safe name — no colons, no quotes, no special chars
            local_ass_name = 'subs.ass'
            local_ass = os.path.join(clip_dir, local_ass_name)
            shutil.copy2(ass_path, local_ass)

            # Build subtitle filter with fontsdir so custom fonts work.
            # Copy fonts dir next to ASS file to avoid Windows colon issues.
            local_fonts_dir = None
            if fonts_dir and os.path.isdir(fonts_dir):
                local_fonts_name = '_fonts'
                local_fonts_path = os.path.join(clip_dir, local_fonts_name)
                if not os.path.exists(local_fonts_path):
                    try:
                        shutil.copytree(fonts_dir, local_fonts_path)
                    except Exception:
                        local_fonts_path = None
                if local_fonts_path and os.path.isdir(local_fonts_path):
                    local_fonts_dir = local_fonts_name

            sub_str = f'subtitles={local_ass_name}'
            if local_fonts_dir:
                sub_str += f':fontsdir={local_fonts_dir}'
            _log(f"[FFmpeg] Subtitle filter: {sub_str}")

            subtitle_crf = max(crf - 4, 15)
            pass2_cmd = [
                ffmpeg, '-y',
                '-i', actual_output,
                '-vf', sub_str,
                '-c:v', codec_name, '-pix_fmt', 'yuv420p', '-preset', encoding_preset, '-crf', str(subtitle_crf),
                '-c:a', 'copy',
                '-movflags', '+faststart',
            ]
            if randomize_metadata:
                import uuid as _uuid
                pass2_cmd.extend([
                    '-metadata', f'comment=ID:{_uuid.uuid4()}',
                    '-metadata', 'description=AutoClip',
                    '-metadata', f'title=Clip_{_uuid.uuid4().hex[:8]}',
                ])
            else:
                pass2_cmd.extend(['-metadata', 'comment=', '-metadata', 'description='])
            pass2_cmd.append(output_path)
            _log(f"[FFmpeg] PASS2 CMD: {' '.join(pass2_cmd)}")

            try:
                proc2 = subprocess.Popen(
                    pass2_cmd,
                    cwd=clip_dir,
                    stderr=subprocess.PIPE, stdout=subprocess.PIPE,
                    universal_newlines=True,
                )

                pass2_stderr = []
                while True:
                    if check_cancelled and check_cancelled():
                        proc2.kill()
                        proc2.wait()
                        try: os.remove(actual_output)
                        except: pass
                        try: os.remove(local_ass)
                        except: pass
                        return None
                    line = proc2.stderr.readline()
                    if not line:
                        break
                    pass2_stderr.append(line)
                    if progress_callback and 'time=' in line:
                        pct = parse_ffmpeg_progress(line, duration)
                        if pct is not None:
                            progress_callback(pct)

                proc2.wait()

                # Cleanup temp file, local ASS copy, and local fonts copy
                try: os.remove(actual_output)
                except: pass
                try: os.remove(local_ass)
                except: pass
                try:
                    if local_fonts_path and os.path.isdir(local_fonts_path):
                        shutil.rmtree(local_fonts_path, ignore_errors=True)
                except: pass

                if proc2.returncode != 0:
                    stderr_text = ''.join(pass2_stderr[-20:])
                    _log(f"[FFmpeg] Subtitle pass FAILED (exit {proc2.returncode})")
                    _log(f"[FFmpeg] PASS2 STDERR:\n{stderr_text}")
                    # FALLBACK: rename first-pass output (no subs) as final output
                    # so the clip is still usable
                    if os.path.exists(temp_output) and os.path.getsize(temp_output) > 0:
                        _log(f"[FFmpeg] Falling back to clip WITHOUT subtitles")
                        import shutil as _shutil
                        _shutil.move(temp_output, output_path)
                    else:
                        return None
            except Exception as e2:
                _log(f"[FFmpeg] Subtitle pass exception: {e2}")
                # Fallback: use first-pass output without subtitles
                if os.path.exists(temp_output) and os.path.getsize(temp_output) > 0:
                    import shutil as _shutil
                    _shutil.move(temp_output, output_path)
                else:
                    return None

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
        return None

    except Exception as e:
        _log(f"[FFmpeg] Exception: {e}")
        import traceback
        traceback.print_exc()
        return None


def _retry_with_libx264(original_cmd, failed_codec, preset, crf,
                         output_path_or_cmd, clip_duration, progress_callback,
                         check_cancelled):
    """Retry FFmpeg with libx264 after hardware codec failure."""
    # Rebuild command with libx264
    cmd = [original_cmd[0]]  # ffmpeg path
    skip_next = False
    replace_output = None

    for i, arg in enumerate(original_cmd[1:], 1):
        if skip_next:
            skip_next = False
            cmd.append('libx264' if arg == failed_codec else arg)
            continue
        if arg == '-c:v' and i + 1 < len(original_cmd) and original_cmd[i + 1] == failed_codec:
            cmd.append('-c:v')
            skip_next = True
            continue
        cmd.append(arg)

    try:
        proc = subprocess.Popen(
            cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE,
            universal_newlines=True,
        )

        while True:
            if check_cancelled and check_cancelled():
                proc.kill()
                proc.wait()
                return None
            line = proc.stderr.readline()
            if not line:
                break
            if progress_callback and 'time=' in line:
                pct = parse_ffmpeg_progress(line, clip_duration)
                if pct is not None:
                    progress_callback(pct)

        proc.wait()

        if proc.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
        return None
    except Exception:
        return None


def _log(msg: str):
    """Print to stdout AND append to log file."""
    print(msg, flush=True)
    try:
        log_path = os.path.join(tempfile.gettempdir(), "zenclip_backend.log")
        import re
        clean = re.sub(r'\033\[[0-9;]*m', '', msg)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(clean.rstrip() + "\n")
    except Exception:
        pass


_CTA_IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tiff', '.tif'}
_CTA_VIDEO_EXTS = {'.mp4', '.mov', '.mkv', '.webm', '.avi'}


def _resolve_cta_path(path: Optional[str], clip_index: int = 0) -> Optional[str]:
    """Resolve CTA path — if it's a directory, pick a random media file from it.

    Uses clip_index as part of the seed so each clip gets a different random pick
    while still being deterministic within a single job run.
    """
    if not path:
        return None
    if os.path.isfile(path):
        return path
    if os.path.isdir(path):
        supported = _CTA_IMAGE_EXTS | _CTA_VIDEO_EXTS
        files = [
            os.path.join(path, f)
            for f in os.listdir(path)
            if os.path.splitext(f)[1].lower() in supported
        ]
        if not files:
            return None
        # Use clip_index to ensure different clips get different CTA files
        random.seed(clip_index + int(time.time()))
        chosen = random.choice(files)
        return chosen
    return None


def _detect_cta_type(path: str, fallback: str = 'image') -> str:
    """Auto-detect CTA type from file extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext in _CTA_VIDEO_EXTS:
        return 'video'
    if ext in _CTA_IMAGE_EXTS:
        return 'image'
    return fallback


def append_cta_to_clip(
    clip_path: str,
    cta_path: str,
    cta_type: str,
    cta_duration: float,
    output_path: str,
    target_w: int = 1080,
    target_h: int = 1920,
) -> Optional[str]:
    """Append a CTA (image or video) to the end of a clip via FFmpeg concat.

    For image CTA: creates a video from the static image (looped for cta_duration).
    For video CTA: re-encodes to match clip resolution/codec, trims to cta_duration.
    Then concatenates clip + CTA using FFmpeg concat demuxer.

    Args:
        clip_path: Path to the main clip (already processed with subs/hooks/watermark).
        cta_path: Path to CTA image file (png/jpg) or video file (mp4).
        cta_type: 'image' or 'video'.
        cta_duration: Duration of the CTA segment in seconds (1-30).
        output_path: Where to write the final clip+CTA file.
        target_w: Width to scale CTA to (must match clip).
        target_h: Height to scale CTA to (must match clip).

    Returns:
        output_path on success, None on failure.
    """
    ffmpeg = _get_ffmpeg_path()
    if not os.path.exists(clip_path):
        _log(f"[CTA] Clip not found: {clip_path}")
        return None
    if not os.path.exists(cta_path):
        _log(f"[CTA] CTA media not found: {cta_path}")
        return None

    tmpdir = tempfile.mkdtemp(prefix="zenclip_cta_")
    try:
        # Step 1: Prepare CTA segment as a compliant intermediate video
        cta_segment = os.path.join(tmpdir, "cta_segment.mp4")

        if cta_type == "image":
            # Image → video: loop static image, add silent audio to match clip streams
            cmd = [
                ffmpeg, "-y",
                "-loop", "1",
                "-i", cta_path,
                "-f", "lavfi",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-t", str(cta_duration),
                "-vf", f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                "-ac", "2",
                "-shortest",
                cta_segment,
            ]
        else:
            # Video CTA: re-encode to match clip format, trim to cta_duration
            cmd = [
                ffmpeg, "-y",
                "-i", cta_path,
                "-t", str(cta_duration),
                "-vf", f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                "-ac", "2",
                cta_segment,
            ]

        _log(f"[CTA] Preparing CTA segment: type={cta_type}, dur={cta_duration}s, res={target_w}x{target_h}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            _log(f"[CTA] Failed to create CTA segment: {result.stderr[-500:]}")
            return None

        if not os.path.exists(cta_segment) or os.path.getsize(cta_segment) < 100:
            _log(f"[CTA] CTA segment is empty or missing")
            return None

        # Step 2: Ensure main clip has audio stream (for concat compatibility)
        clip_with_audio = os.path.join(tmpdir, "clip_audio.mp4")
        cmd = [
            ffmpeg, "-y",
            "-i", clip_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-ac", "2",
            # Add silent audio if clip has no audio track
            "-shortest",
            clip_with_audio,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0 or not os.path.exists(clip_with_audio):
            # Fallback: add silent audio track
            _log(f"[CTA] Clip has no audio, adding silent track")
            cmd = [
                ffmpeg, "-y",
                "-i", clip_path,
                "-f", "lavfi",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                clip_with_audio,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                _log(f"[CTA] Failed to add silent audio: {result.stderr[-300:]}")
                return None

        # Step 3: Concat using concat demuxer (most reliable method)
        concat_list = os.path.join(tmpdir, "concat.txt")
        # Use forward slashes for FFmpeg compatibility on Windows
        clip_audio_safe = clip_with_audio.replace("\\", "/")
        cta_segment_safe = cta_segment.replace("\\", "/")
        with open(concat_list, "w", encoding="utf-8") as f:
            f.write(f"file '{clip_audio_safe}'\n")
            f.write(f"file '{cta_segment_safe}'\n")

        cmd = [
            ffmpeg, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ]

        _log(f"[CTA] Concatenating clip + CTA → {output_path}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            _log(f"[CTA] Concat failed: {result.stderr[-500:]}")
            return None

        if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
            _log(f"[CTA] SUCCESS: {output_path} ({os.path.getsize(output_path)} bytes)")
            return output_path
        else:
            _log(f"[CTA] Output file missing or empty")
            return None

    except subprocess.TimeoutExpired:
        _log(f"[CTA] FFmpeg timeout")
        return None
    except Exception as e:
        _log(f"[CTA] Error: {e}")
        return None
    finally:
        # Cleanup temp files
        try:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


def process_single_clip_ffmpeg(args) -> Optional[str]:
    """Process a single clip via FFmpeg pipeline (worker function)."""
    (clip_index, clip_data, total_clips, video_path, output_folder,
     phrase_timings, subtitle_config, add_subtitles,
     add_viral_hook, hook_styles, target_resolution, canvas_resolution,
     add_watermark, watermark_config, quality_preset,
     cancel_event, cta_config, randomize_metadata) = args

    start_time = clip_data.get('start_time', 0)
    end_time = clip_data.get('end_time', 60)
    duration = end_time - start_time

    _log(f"[Pipeline] Clip {clip_index}: {start_time:.1f}s-{end_time:.1f}s ({duration:.1f}s), topic={clip_data.get('topic','?')}")

    if duration <= 0:
        _log(f"[Pipeline] Clip {clip_index}: INVALID duration={duration}, skipping")
        return None

    def check_cancelled():
        return cancel_event and cancel_event.is_set()

    # Output path
    topic = clip_data.get('topic', 'untitled').replace(' ', '_')[:30]
    output_filename = f"clip_{clip_index}_{topic}.mp4"
    output_path = os.path.join(output_folder, output_filename)

    target_w, target_h = target_resolution or (1080, 1920)

    try:
        # Step 0: Probe actual video dimensions
        video_w, video_h = _probe_video_dimensions(video_path)
        _log(f"[Pipeline] Clip {clip_index}: Source video {video_w}x{video_h}, target {target_w}x{target_h}")

        # Step 1: Face tracking analysis (Python/OpenCV)
        crop_rect = None

        # Only do face-tracking crop if source resolution is high enough.
        # Upscaling from a tiny crop (e.g. 202x360 → 1080x1920) produces
        # terrible quality. Minimum source width for face crop = 480px.
        min_source_width_for_crop = 480
        if video_w >= min_source_width_for_crop:
            face_analysis = _analyze_face_positions(
                video_path, start_time, end_time,
                enable_tracking=True, num_samples=10,
                check_cancelled=check_cancelled,
            )

            if face_analysis and face_analysis.get('detected'):
                center_x = face_analysis.get('avg_center_x', None)
                positions = face_analysis.get('positions', [])
                crop_rect = compute_static_crop(
                    video_w, video_h,
                    target_w, target_h,
                    center_x=center_x,
                )
                _log(f"[Pipeline] Clip {clip_index}: Face detected at x={center_x}, crop={crop_rect}")
            else:
                _log(f"[Pipeline] Clip {clip_index}: No face detected, using full frame")
        else:
            _log(f"[Pipeline] Clip {clip_index}: Source {video_w}x{video_h} too small for face crop (min {min_source_width_for_crop}px), using full frame")

        # Step 2: Hook overlay
        hook_png = None
        hook_pos = None
        hook_dur = 3.5
        hook_full = False
        if add_viral_hook and hook_styles:
            # Merge AI-generated hook text (from clip_data) with user settings
            # (from hook_styles). AI text takes priority, user text is fallback.
            merged_styles = dict(hook_styles)  # copy to avoid mutation
            final_heading = clip_data.get('hook_heading') or hook_styles.get('headline', '')
            final_subheading = clip_data.get('hook_subheading') or hook_styles.get('subheading', '')
            final_top_text = clip_data.get('hook_top_text') or hook_styles.get('top_text', '')
            final_preset2_content = clip_data.get('preset2_content') or hook_styles.get('preset2_content', '')

            merged_styles['headline'] = final_heading
            merged_styles['subheading'] = final_subheading
            merged_styles['top_text'] = final_top_text
            merged_styles['preset2_content'] = final_preset2_content

            hook_style = merged_styles.get('hook_style', 'preset-1')

            # Check if there's enough text to render a hook
            should_render = False
            if hook_style == 'preset-2':
                should_render = bool(final_preset2_content)
            else:
                should_render = bool(final_heading or final_subheading or final_top_text)

            _log(f"[Pipeline] Clip {clip_index}: Hook style={hook_style}, render={should_render}, heading='{final_heading[:30] if final_heading else ''}...'")

            if should_render:
                hook_result = _render_hook_png(
                    hook_style, merged_styles,
                    target_w, target_h, duration,
                    config=clip_data,
                )
                if hook_result:
                    hook_png, hook_pos = hook_result
                    hook_full = merged_styles.get('full_duration', False)
                    hook_dur = duration if hook_full else 3.5
                    _log(f"[Pipeline] Clip {clip_index}: Hook rendered: {hook_png}")
                else:
                    _log(f"[Pipeline] Clip {clip_index}: Hook returned None (render failed)")
            else:
                _log(f"[Pipeline] Clip {clip_index}: Hook skipped — no text content for {hook_style}")

        # Step 3: Subtitle generation
        ass_path = None
        fonts_dir = None
        if add_subtitles and phrase_timings:
            # CRITICAL: copy the dict to prevent mutation by generate_ass_file()
            # which doubles fontsize in-place. Without copying, each clip would
            # double the fontsize exponentially (48→96→192→384→...).
            style_config = dict(subtitle_config) if subtitle_config else {'style': 'shadow'}
            # Fontsize for FFmpeg ASS at PlayResY 1920. generate_ass_file()
            # doubles this value. 18 → 36 = ~1.9% of 1920 (small, clean).
            if 'fontsize' not in style_config:
                style_config['fontsize'] = 18
            suppress_hook = add_viral_hook and not hook_styles.get('full_duration', False)
            ass_path = _generate_subtitle_ass(
                phrase_timings, start_time, end_time,
                (target_w, target_h), style_config,
                hook_duration=hook_dur if suppress_hook else None,
                suppress_during_hook=suppress_hook,
            )
            # Try to find fonts directory
            try:
                from services.core.binary_manager import get_sidecar_dir
                fd = os.path.join(get_sidecar_dir(), 'fonts')
                if os.path.isdir(fd):
                    fonts_dir = fd
            except Exception:
                pass
            # Fallback: look in backend/static/fonts (where fonts actually live)
            if not fonts_dir:
                for candidate in [
                    # ffmpeg_pipeline.py is at backend/src/services/media/
                    # Need to go up 4 levels to reach backend/static/fonts
                    os.path.join(os.path.dirname(__file__), '..', '..', '..', 'static', 'fonts'),
                    os.path.join(os.path.dirname(__file__), '..', 'resources', 'fonts'),
                    os.path.join(os.path.dirname(__file__), '..', '..', 'resources', 'fonts'),
                ]:
                    c = os.path.normpath(candidate)
                    if os.path.isdir(c):
                        fonts_dir = c
                        break
            _log(f"[Pipeline] Clip {clip_index}: Subtitles: ass={ass_path}, fonts={fonts_dir}")
        wm_image = None
        wm_text = None
        wm_config_dict = None
        if add_watermark and watermark_config:
            wm_type = watermark_config.get('watermark_type',
                      watermark_config.get('watermarkType', 'text'))
            if wm_type == 'image':
                wm_image = watermark_config.get('watermark_image_path',
                           watermark_config.get('watermarkImagePath'))
            else:
                wm_text = watermark_config.get('watermark_text',
                          watermark_config.get('watermarkText', 'ZenClip'))
            wm_config_dict = {
                'opacity': float(watermark_config.get('watermark_opacity',
                           watermark_config.get('watermarkOpacity', 0.3))),
                'fontsize': watermark_config.get('watermark_size',
                            watermark_config.get('watermarkSize', 24)),
                'position': watermark_config.get('watermark_position',
                            watermark_config.get('watermarkPosition', 'bottom_right')),
                'font': watermark_config.get('watermark_font',
                        watermark_config.get('watermarkFont')),
            }

        # Step 5: Canvas padding
        canvas_w, canvas_h = None, None
        if canvas_resolution:
            cw, ch = canvas_resolution
            if cw != target_w or ch != target_h:
                canvas_w, canvas_h = cw, ch

        # Step 6: Run FFmpeg
        _log(f"[Pipeline] Clip {clip_index}: Running FFmpeg — crop={crop_rect}, hook={hook_png is not None}, subs={ass_path is not None}, preset={quality_preset}")
        result = run_ffmpeg_clip(
            input_path=video_path,
            output_path=output_path,
            start_time=start_time,
            duration=duration,
            target_w=target_w,
            target_h=target_h,
            crop_rect=crop_rect,
            hook_png_path=hook_png,
            hook_position=hook_pos,
            hook_duration=hook_dur,
            hook_full_duration=hook_full,
            ass_path=ass_path,
            fonts_dir=fonts_dir,
            canvas_w=canvas_w,
            canvas_h=canvas_h,
            watermark_image=wm_image,
            watermark_text=wm_text,
            watermark_config=wm_config_dict,
            quality_preset=quality_preset,
            progress_callback=None,
            check_cancelled=check_cancelled,
            randomize_metadata=randomize_metadata,
        )

        if result:
            _log(f"[Pipeline] Clip {clip_index}: SUCCESS → {result}")
        else:
            _log(f"[Pipeline] Clip {clip_index}: FAILED — FFmpeg returned None")
            return result

        # Step 7: CTA append (after all processing is done)
        if cta_config and cta_config.get('enabled'):
            cta_path_raw = cta_config.get('path')
            cta_type = cta_config.get('type', 'image')
            cta_duration = cta_config.get('duration', 5.0)

            # Resolve CTA path: if directory, pick a random media file
            cta_path = _resolve_cta_path(cta_path_raw, clip_index)
            if cta_path:
                # Auto-detect type from extension when picked from folder
                cta_type = _detect_cta_type(cta_path, fallback=cta_type)

            if cta_path and os.path.exists(cta_path):
                cta_output = os.path.join(output_folder, f"cta_{output_filename}")
                _log(f"[Pipeline] Clip {clip_index}: Appending CTA ({cta_type}, {cta_duration}s) from {os.path.basename(cta_path)}")
                cta_result = append_cta_to_clip(
                    clip_path=result,
                    cta_path=cta_path,
                    cta_type=cta_type,
                    cta_duration=cta_duration,
                    output_path=cta_output,
                    target_w=target_w,
                    target_h=target_h,
                )
                if cta_result:
                    # Replace original clip with CTA-appended version
                    try:
                        os.replace(cta_result, output_path)
                    except OSError:
                        # Fallback: copy then delete
                        import shutil
                        shutil.copy2(cta_result, output_path)
                    _log(f"[Pipeline] Clip {clip_index}: CTA appended → {output_path}")
                else:
                    _log(f"[Pipeline] Clip {clip_index}: CTA failed, keeping original clip")
            else:
                _log(f"[Pipeline] Clip {clip_index}: CTA enabled but media not found at {cta_path_raw}")

        return output_path


    except Exception as e:
        _log(f"[ERROR] Clip {clip_index} failed: {e}")
        import traceback
        tb = traceback.format_exc()
        _log(f"[ERROR] Traceback:\n{tb}")
        return None


def cut_video_clips_ffmpeg(
    video_path: str,
    clips_data: list,
    output_folder: str = 'clips',
    add_subtitles: bool = False,
    phrase_timings: list = None,
    subtitle_config: dict = None,
    add_viral_hook: bool = False,
    hook_styles: dict = None,
    target_resolution: tuple = None,
    canvas_resolution: tuple = None,
    add_watermark: bool = False,
    watermark_config: dict = None,
    quality_preset: str = 'balanced',
    progress_callback: Callable = None,
    check_cancelled: Callable = None,
    max_workers: int = 1,
    cta_config: dict = None,
    randomize_metadata: bool = False,
) -> list:
    """Main entry point: cut video into clips using FFmpeg pipeline.

    Args:
        progress_callback: Called with (clip_index, total_clips, clip_progress)
        check_cancelled: Returns True if job should be cancelled

    Returns:
        List of output file paths (None for failed clips)
    """
    import multiprocessing

    os.makedirs(output_folder, exist_ok=True)

    total_clips = len(clips_data)
    cancel_event = multiprocessing.Manager().Event()

    # Build task tuples
    tasks = []
    for i, clip_data in enumerate(clips_data):
        task_args = (
            i, clip_data, total_clips, video_path, output_folder,
            phrase_timings, subtitle_config, add_subtitles,
            add_viral_hook, hook_styles or {},
            target_resolution or (1080, 1920),
            canvas_resolution,
            add_watermark, watermark_config,
            quality_preset,
            cancel_event,
            cta_config,
            randomize_metadata,
        )
        tasks.append(task_args)

    output_paths = [None] * total_clips

    if max_workers <= 1:
        # Sequential processing
        for i, task in enumerate(tasks):
            if check_cancelled and check_cancelled():
                break
            result = process_single_clip_ffmpeg(task)
            output_paths[i] = result
            if progress_callback:
                progress_callback(i, total_clips, 1.0 if result else 0.0)
    else:
        # Parallel processing
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for i, task in enumerate(tasks):
                future = executor.submit(process_single_clip_ffmpeg, task)
                futures[future] = i

            for future in as_completed(futures):
                idx = futures[future]
                try:
                    output_paths[idx] = future.result()
                except Exception as e:
                    _log(f"[ERROR] Clip {idx} raised: {e}")
                    output_paths[idx] = None

                if progress_callback:
                    progress_callback(idx, total_clips, 1.0)

    return output_paths
