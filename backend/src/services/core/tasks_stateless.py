from utils.logger import log
import utils.encoding_fix
import os
import time
import sys
import json
import subprocess
import tempfile

from services.media.video_cutter import cut_video_clips
from services.media.ffmpeg_pipeline import cut_video_clips_ffmpeg
from services.core.cache import get_cached_transcript, save_transcript_to_cache, get_file_hash
from services.core import binary_manager
from services.core.resource_monitor import get_resource_monitor

from services.media.audio_transcriber import transcribe_video, clean_repetitive_content, clean_phrase_level_repetition
from services.ai.llm_analyzer import analyze_transcript_with_llm

def transcribe_step(video_path, transcription_mode='fast', check_cancelled=None):
    """
    Extracts transcript from video. 
    Checks cache first.
    Returns list of phrase timings.
    """
    log.section("Transcript Extraction")
    log.step(f"Extracting transcript: {video_path}", module="Transcriber")
    
    # Check Cache
    file_hash = get_file_hash(video_path)
    phrase_timings = None
    language = 'en' # Default
    
    if file_hash:
        result = get_cached_transcript(file_hash)
        if result:
            phrase_timings, language = result
            # CRITICAL FIX: Clean Repetition even if cached (in case cache is bad)
            log.step("Clearing cached transcript", module="Transcriber")
            phrase_timings = clean_repetitive_content(phrase_timings)
            phrase_timings = clean_phrase_level_repetition(phrase_timings)
        
    if phrase_timings:
        log.success(f"Using cached transcript (lang={language})", module="Transcriber")
        return phrase_timings, language
    
    # If using YouTube and have video ID, we might check YT transcript?
    # But here we have a file path. `get_file_hash` handles file hashing.
    # If we want to check YT transcript, we'd need the video ID which is lost here 
    # unless we pass it. But for simplicity let's stick to audio if not in cache,
    # OR we can assume if it was downloaded via tasks_stateless, we might have cached it by ID there?
    # For now, simplistic approach: Transcribe file.
    
    model_name = 'base'
    if transcription_mode == 'accurate':
        model_name = 'large-v3'
    elif transcription_mode == 'small':
        model_name = 'small'
    
    if os.environ.get('CLIP_RECOVERY_SAFE') == '1':
        worker_script = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'media',
            'transcribe_subprocess.py'
        )
        fd, output_path = tempfile.mkstemp(prefix='recovery-transcribe-', suffix='.json')
        os.close(fd)

        command = [
            sys.executable,
            worker_script,
            '--video',
            video_path,
            '--language',
            'auto',
            '--model',
            model_name,
            '--output',
            output_path,
        ]

        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUNBUFFERED'] = '1'

        log.step("Running transcription in isolated recovery subprocess", module="Transcriber")
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=os.getcwd(),
            env=env,
        )

        try:
            start_time = time.time()
            timeout_seconds = 25
            while process.poll() is None:
                if check_cancelled and check_cancelled():
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise Exception("Job Cancelled")
                if time.time() - start_time > timeout_seconds:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise RuntimeError(
                        "Recovery transcription timed out while loading the bundled Whisper runtime. "
                        "This machine likely has a native CTranslate2/OpenMP compatibility issue."
                    )
                time.sleep(0.5)

            stdout, stderr = process.communicate()
            stdout = (stdout or '').strip()
            stderr = (stderr or '').strip()

            if stdout:
                print(stdout)
            if stderr:
                print(stderr)

            payload = {}
            if os.path.exists(output_path):
                try:
                    if os.path.getsize(output_path) > 0:
                        with open(output_path, 'r', encoding='utf-8') as handle:
                            payload = json.load(handle)
                except json.JSONDecodeError:
                    payload = {}

            if process.returncode != 0:
                error_message = payload.get('error') or stderr or stdout or 'Transcription subprocess terminated unexpectedly'
                raise RuntimeError(f"Recovery transcription failed safely: {error_message}")

            if not payload:
                raise RuntimeError(
                    'Recovery transcription worker exited without producing transcript output. '
                    'This usually indicates a native faster_whisper/ctranslate2 crash on this machine.'
                )

            phrase_timings = payload.get('phrase_timings', [])
            language = payload.get('language', 'en')
        finally:
            try:
                if os.path.exists(output_path):
                    os.remove(output_path)
            except Exception:
                pass
    else:
        # PASS CANCELLATION CHECK
        phrase_timings, language = transcribe_video(video_path, language='auto', model_name=model_name, check_cancelled=check_cancelled)
    
    if phrase_timings and file_hash:
        save_transcript_to_cache(file_hash, phrase_timings, source_type='upload', extra_meta={'filename': os.path.basename(video_path)}, language=language)

    # transcribe_video now raises specific exceptions on failure
    # so we don't need to check for empty list and raise generic error.
    # if not phrase_timings:
    #    raise Exception("Gagal mengekstrak transkrip dari video")
        
    log.success(f"Transcript extracted: {len(phrase_timings)} phrases, lang={language}", module="Transcriber")
    return phrase_timings, language

def analyze_step(phrase_timings, num_clips, min_duration, video_type, custom_prompt, api_key, api_provider, hook_style='preset-1', language='en', check_cancelled=None):
    """
    Analyzes transcript to find viral clips.
    """
    transcript_text = '\n'.join([phrase['text'] for phrase in phrase_timings])
    
    # Handle "auto" duration
    actual_min_duration = 30 if str(min_duration).lower() == "auto" else int(min_duration)
    
    log.step("Analyzing transcript for viral clips", module="Analyzer")
    
    if api_key:
         os.environ['DEEPSEEK_API_KEY'] = api_key

    clips_data = analyze_transcript_with_llm(
        transcript_text, 
        phrase_timings, 
        num_clips=num_clips, 
        min_duration=actual_min_duration,
        video_type=video_type,
        custom_prompt=custom_prompt,
        api_key=api_key, # Explicitly pass the key
        api_provider=api_provider,
        hook_style=hook_style,
        language=language,
        check_cancelled=check_cancelled
    )
    
    # clips_data = analyze_transcript_with_llm(...) will now raise specific exceptions on failure
    # so we do not need to check 'if not clips_data' and raise a generic error.
    # The worker will catch the detailed ValidationError/InvalidResponseError.
    
    # if not clips_data:
    #     raise Exception("Gagal menganalisis konten untuk klip viral")
        
    return clips_data

def cut_step(video_path, clips_data, phrase_timings, config, job_id=None, progress_callback=None, check_cancelled=None):
    """
    Cuts video clips based on analysis.
    config: dict containing subtitle options, hook options, etc.
    job_id: optional, used to create unique output subfolder
    """
    # ... (function body remains same until call)
    add_subtitles = config.get('add_subtitles', False)
    subtitle_config = config.get('subtitle_config')
    min_duration = config.get('min_duration', 30)
    video_aspect = config.get('video_aspect', '9:16')
    randomize_metadata = config.get('randomize_metadata', False)
    custom_metadata = config.get('custom_metadata')
    add_viral_hook = config.get('add_viral_hook', False)
    hook_styles = config.get('hook_styles', {})
    
    use_original_resolution = (video_aspect == 'original')
    
    # Resolution Mapping
    # Resolution Mapping
    target_resolution = (1080, 1920) # Default 9:16
    canvas_resolution = (1080, 1920) # Default Canvas is 9:16 Portrait

    if video_aspect == '16:9':
        target_resolution = (1920, 1080)
        canvas_resolution = (1920, 1080) # No padding for landscape
    elif video_aspect == '1:1':
        # Inset video with padding (980px width on 1080px canvas) - Matches Mac Logic
        target_resolution = (980, 980)
        # canvas_resolution remains (1080, 1920) for padding
    elif video_aspect == '4:5':
        # Inset video with padding (980px width on 1080px canvas) - Matches Mac Logic
        target_resolution = (980, 1225)
        # canvas_resolution remains (1080, 1920) for padding
    elif video_aspect == 'original':
        target_resolution = None 
        canvas_resolution = None
    
    # Get CLIPS_DIR from app context
    # Import here to avoid circular dependency
    from app import CLIPS_DIR
    
    # Ensure output folder with unique job ID if provided
    output_folder = CLIPS_DIR
    if job_id:
        output_folder = os.path.join(CLIPS_DIR, job_id)
        
    os.makedirs(output_folder, exist_ok=True)

    
    
    # INJECT GLOBAL SETTINGS INTO CLIPS_DATA
    # process_single_clip expects these in the clip_info dict
    for clip in clips_data:
        # 1. Watermark
        if config.get('add_watermark') or config.get('addWatermark'):
            clip['add_watermark'] = True
            
            # Construct watermark config from global config
            # Frontend sends mixed case sometimes, so we check both or assume config is normalized
            # Based on CreateTab.tsx, these are the keys:
            w_config = {}
            w_config['watermark_type'] = config.get('watermark_type') or config.get('watermarkType', 'text')
            w_config['watermark_text'] = config.get('watermark_text') or config.get('watermarkText', '')
            # For image, we might need to handle file path? Frontend sends file upload separately usually? 
            # Or if it's a settings object, it typically has the path if saved on backend.
            # Assuming key is 'watermark_image_path' in saved settings ??
            # Checking CreateTab.tsx: formData.append('watermarkImage', ...) -> saved to where?
            # Usually settings endpoint saves files and stores path in json.
            w_config['watermark_image_path'] = config.get('watermark_image_path') or config.get('watermarkImagePath')
            w_config['watermark_opacity'] = config.get('watermark_opacity') or config.get('watermarkOpacity', 0.5)
            w_config['watermark_position'] = config.get('watermark_position') or config.get('watermarkPosition', 'bottom_right')
            w_config['watermark_size'] = config.get('watermark_size') or config.get('watermarkSize', 0.3)
            w_config['watermark_font'] = config.get('watermark_font') or config.get('watermarkFont', 'Arial-Bold')
            
            clip['watermark_config'] = w_config
            
    # Calculate optimal workers based on mode (Eco/Turbo)
    monitor = get_resource_monitor()
    max_workers, encoding_threads = monitor.get_optimal_worker_config()
    # Use 0 (auto) for encoding threads — lets FFmpeg use all available cores
    encoding_threads = 0
    encoding_preset = config.get('encoding_preset', 'medium')
    
    log.info(f"Video cutter: {max_workers} workers, threads=auto, preset={encoding_preset}, class={monitor.machine_class}", module="Cutter")

    # Use FFmpeg pipeline for video cutting
    quality_preset = config.get('quality_preset', 'balanced')
    add_watermark = config.get('add_watermark') or config.get('addWatermark')
    watermark_config = None
    if add_watermark:
        watermark_config = {
            'watermark_type': config.get('watermark_type') or config.get('watermarkType', 'text'),
            'watermark_text': config.get('watermark_text') or config.get('watermarkText', ''),
            'watermark_image_path': config.get('watermark_image_path') or config.get('watermarkImagePath'),
            'watermark_opacity': config.get('watermark_opacity') or config.get('watermarkOpacity', 0.5),
            'watermark_position': config.get('watermark_position') or config.get('watermarkPosition', 'bottom_right'),
            'watermark_size': config.get('watermark_size') or config.get('watermarkSize', 0.3),
            'watermark_font': config.get('watermark_font') or config.get('watermarkFont', 'Arial-Bold'),
        }

    clip_paths = cut_video_clips_ffmpeg(
        video_path,
        clips_data,
        output_folder=output_folder,
        add_subtitles=add_subtitles,
        phrase_timings=phrase_timings,
        subtitle_config=subtitle_config,
        add_viral_hook=add_viral_hook,
        hook_styles=hook_styles,
        target_resolution=target_resolution,
        canvas_resolution=canvas_resolution,
        add_watermark=add_watermark or False,
        watermark_config=watermark_config,
        quality_preset=quality_preset,
        progress_callback=progress_callback,
        check_cancelled=check_cancelled,
        max_workers=max_workers,
        cta_config=config.get('cta_config'),
        randomize_metadata=randomize_metadata,
    )
    
    # Return formatted info
    clips_info = []
    for i, (clip_path, clip_data) in enumerate(zip(clip_paths, clips_data)):
        if clip_path is None:
            log.warn(f"Skipping failed clip {i+1}", module="Cutter")
            continue
            
        duration_sec = clip_data['end_time'] - clip_data['start_time']
        clips_info.append({
            'path': clip_path.replace('\\', '/'),  # Normalize for cross-platform browser consumption
            'topic': clip_data['topic'],
            'reason': clip_data.get('reason', ''),
            'caption': clip_data.get('viral_caption', ''),
            'hook_heading': clip_data.get('hook_heading', ''),
            'hook_subheading': clip_data.get('hook_subheading', ''),
            'duration': f"{duration_sec:.1f}"
        })
        
    return clips_info
