"""
ffmpeg_filter_builder.py - Builds FFmpeg -filter_complex strings
for the ZenClip video processing pipeline.
"""
from typing import Optional


# Quality presets mapping
QUALITY_PRESETS = {
    'draft': {
        'encoding_preset': 'ultrafast',
        'crf': 28,
        'track_sample_interval': 1.0,
    },
    'balanced': {
        'encoding_preset': 'fast',
        'crf': 23,
        'track_sample_interval': 0.5,
    },
    'quality': {
        'encoding_preset': 'medium',
        'crf': 20,
        'track_sample_interval': 0.25,
    },
}

DEFAULT_PRESET = 'balanced'


def get_preset(name: str) -> dict:
    """Get quality preset config by name. Falls back to balanced."""
    return QUALITY_PRESETS.get(name, QUALITY_PRESETS[DEFAULT_PRESET])


def crop_and_scale_filter(crop_w, crop_h, crop_x, crop_y,
                          scale_w, scale_h, output_label):
    """Combined crop + scale in one filter chain segment."""
    return (f'[0:v]crop={crop_w}:{crop_h}:{crop_x}:{crop_y},'
            f'scale={scale_w}:{scale_h}[{output_label}]')


def crop_scale_from_label(input_label, crop_w, crop_h, crop_x, crop_y,
                          scale_w, scale_h, output_label):
    """Crop + scale from a labeled input (not 0:v)."""
    return (f'[{input_label}]crop={crop_w}:{crop_h}:{crop_x}:{crop_y},'
            f'scale={scale_w}:{scale_h}[{output_label}]')


def overlay_filter(base_label, overlay_label, x, y, output_label,
                   enable_expr=None):
    """Build overlay filter.

    Args:
        base_label: Input label for base video (e.g., 'v0')
        overlay_label: Input label for overlay (e.g., '1:v')
        x, y: Overlay position in pixels
        output_label: Output stream label
        enable_expr: FFmpeg expression like 'between(t,0,3.5)'
    """
    parts = [f'[{base_label}][{overlay_label}]overlay={x}:{y}']
    if enable_expr:
        parts.append(f"enable='{enable_expr}'")
    parts.append('format=auto')
    return ':'.join(parts) + f'[{output_label}]'


def subtitle_vf(ass_path, fonts_dir=None):
    """Build -vf subtitles filter string from ASS file.

    FFmpeg filter syntax uses ':' as option separator and '\\' as escape char.
    On Windows, drive letter colons (C:) must be escaped as \\: to avoid
    being parsed as option separators.
    """
    # Convert backslashes to forward slashes (FFmpeg accepts both on Windows)
    safe_path = ass_path.replace('\\', '/')
    # Escape colons so FFmpeg doesn't treat them as option separators
    safe_path = safe_path.replace(':', '\\:')
    if fonts_dir:
        safe_fonts = fonts_dir.replace('\\', '/').replace(':', '\\:')
        return f"subtitles={safe_path}:fontsdir={safe_fonts}"
    return f"subtitles={safe_path}"


def pad_filter(canvas_w, canvas_h, output_label, input_label):
    """Build pad filter to place video on a larger canvas."""
    return (f'[{input_label}]pad={canvas_w}:{canvas_h}:'
            f'(ow-iw)/2:(oh-ih)/2:black[{output_label}]')


def drawtext_filter(text, x, y, fontsize=24, opacity=0.3, font=None, fontcolor='white'):
    """Build drawtext filter for text watermark."""
    f = f"drawtext=text='{text}':fontcolor={fontcolor}@{opacity}:fontsize={fontsize}:x={x}:y={y}"
    if font:
        f += f":fontfile='{font}'"
    return f


# Watermark position presets → FFmpeg x,y expressions
_WATERMARK_POS_MAP = {
    'top_left':      ('10', '10'),
    'top_right':     ('W-tw-10', '10'),
    'top_center':    ('(W-tw)/2', '10'),
    'bottom_left':   ('10', 'H-th-10'),
    'bottom_right':  ('W-tw-10', 'H-th-10'),
    'bottom_center': ('(W-tw)/2', 'H-th-10'),
    'center':        ('(W-tw)/2', '(H-th)/2'),
}


def watermark_position_to_xy(position, fallback_x='W-tw-10', fallback_y='H-th-10'):
    """Convert a watermark position string or dict to (x_expr, y_expr) for FFmpeg.

    Args:
        position: One of 'top_left', 'top_right', 'bottom_left', 'bottom_right',
                  'top_center', 'bottom_center', 'center', or a dict {x, y} with
                  values in 0.0-1.0 range (fraction of video dimensions).
        fallback_x: Default x expression if position is unrecognised.
        fallback_y: Default y expression if position is unrecognised.

    Returns:
        (x_expr, y_expr) — FFmpeg expression strings.
    """
    if isinstance(position, str):
        return _WATERMARK_POS_MAP.get(position, (fallback_x, fallback_y))
    if isinstance(position, dict):
        # Fractional 0-1 position → pixel expression
        xp = position.get('x', 0.9)
        yp = position.get('y', 0.9)
        return (f'W*{xp}', f'H*{yp}')
    return (fallback_x, fallback_y)


def build_filter_complex(filters):
    """Join multiple filter chain segments into a -filter_complex string."""
    return ';\n'.join(filters)


def build_encoding_args(codec, preset, crf, audio_codec='aac',
                        audio_bitrate='192k'):
    """Build FFmpeg encoding arguments list."""
    return [
        '-c:v', codec,
        '-pix_fmt', 'yuv420p',
        '-preset', preset,
        '-crf', str(crf),
        '-c:a', audio_codec,
        '-b:a', audio_bitrate,
        '-movflags', '+faststart',
    ]
