"""
Audio Transcription Module
Extracts audio from video and transcribes using Faster Whisper (CTranslate2)
Generates phrase-level timings compatible with subtitle system
"""

import os
import subprocess
import tempfile
import json
import time
import threading
import numpy as np
from functools import lru_cache
from difflib import SequenceMatcher
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from services.core import binary_manager
from services.core.resource_monitor import get_resource_monitor

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

# --- Windows DLL Search Path Fix ---
if os.name == 'nt':
    try:
        # Allow explicit DLL search path overrides before falling back to project-relative paths.
        override_dirs = [
            os.environ.get('CLIP_DLL_DIR'),
            os.environ.get('CLIP_CUDA_DIR'),
        ]

        # Add local directories to DLL search path so user can drop cublas64_12.dll here
        base_dir = os.path.dirname(os.path.abspath(__file__)) # src
        backend_dir = os.path.dirname(base_dir) # Backend
        project_root = os.path.dirname(backend_dir) # Clipiee Root (d:\\clipiee)

        dll_dirs = []
        for candidate in override_dirs + [base_dir, backend_dir, project_root]:
            if candidate and os.path.exists(candidate) and candidate not in dll_dirs:
                dll_dirs.append(candidate)

        for dll_dir in dll_dirs:
            os.add_dll_directory(dll_dir)
        print(f"[INFO] Added DLL search paths: {', '.join(dll_dirs)}")
    except Exception as e:
        print(f"[WARN] Failed to add DLL directory: {e}") 

# --- Metrics & Classes ---

@dataclass
class TranscriptionMetrics:
    audio_duration_sec: float
    processing_time_sec: float
    real_time_factor: float  # processing_time / audio_duration
    model_name: str
    language: str
    language_confidence: float
    num_segments: int
    num_words: int
    avg_word_confidence: float

# --- Constants ---

HALLUCINATION_PHRASES = [
    "terima kasih", "thank you", "subtitle by", "amara.org", 
    "transcribed by", "copyright", "all rights reserved",
    "subtitles by", "captioned by", "community reviews"
]

# --- Model Caching (Singleton Pattern) ---

_model_cache = {}
_model_lock = threading.Lock()

def get_whisper_model(model_name: str = 'base', device: str = 'auto', compute_type: str = 'int8') -> WhisperModel:
    """
    Cached model loader - loads model only once per configuration
    Thread-safe singleton pattern
    """
    if WhisperModel is None:
        raise ImportError(
            "faster_whisper is not installed. Install ASR extras to enable transcription flows."
        )

    cache_key = f"{model_name}_{device}_{compute_type}"
    
    with _model_lock:
        if cache_key not in _model_cache:
            print(f"[INFO] Loading Whisper model '{model_name}' (requested device={device}, compute={compute_type})...")
            
            # Check memory before loading model
            resource_monitor = get_resource_monitor()
            if not resource_monitor.can_process():
                print(f"[WARN] Low memory detected, waiting for resources...")
                if not resource_monitor.wait_for_resources(timeout=60):
                    raise RuntimeError("Insufficient memory to load Whisper model")
            
            model = None
            last_error = None
            
            # Strategy: List of configurations to try in order of preference.
            # In recovery mode, avoid CPU int8 first because certain CTranslate2 builds
            # can terminate the process at native level on unsupported hosts.
             
            strategies = []
            recovery_safe = os.environ.get("CLIP_RECOVERY_SAFE") == "1"
             
            # If default is auto/cuda, explicitly prefer CUDA strategies first
            if device in ['auto', 'cuda']:
                strategies.extend([
                    ('cuda', 'float16'),      # Best for modern NV GPUs (RTX 30/40)
                    ('cuda', 'int8_float16'), # Memory efficient NV
                    ('cuda', 'int8')          # Fallback NV
                ])
                if device == 'auto':
                    strategies.append(('cpu', 'float32' if recovery_safe else 'int8'))
            else:
                # User specifically asked for CPU or something else, try that first
                strategies.append((device, compute_type))

            # Always have safe fallbacks at the end
            if recovery_safe:
                strategies.append(('cpu', 'float32')) # Universal fallback
                strategies.append(('cpu', 'int8'))
            else:
                strategies.append(('cpu', 'int8'))
                strategies.append(('cpu', 'float32')) # Universal fallback

            # Deduplicate strategies while preserving order
            seen = set()
            attempts = []
            for d, c in strategies:
                if (d, c) not in seen:
                    attempts.append((d, c))
                    seen.add((d, c))

            for dev, comp in attempts:
                try:
                    print(f"[INFO] Attempting to load Whisper with device='{dev}', compute_type='{comp}'...")
                    model = WhisperModel(model_name, device=dev, compute_type=comp, 
                                       num_workers=resource_monitor.get_whisper_threads())
                    
                    # --- DRY RUN VERIFICATION ---
                    # Some DLL errors (like cublas64_12.dll missing) only trigger on first inference, not init.
                    # We treat the model as 'failed' if it crashes on a simple 1-second silent audio.
                    print(f"[INFO] Verifying model health...")
                    try:
                        # 1 second of silence at 16kHz
                        dummy_audio = np.zeros(16000, dtype=np.float32) 
                        segments, _ = model.transcribe(dummy_audio, beam_size=1)
                        list(segments) # Force generator to run
                        print(f"[SUCCESS] Verified Whisper model on {dev} with {comp}")
                        break
                    except Exception as e:
                        print(f"[WARN] verification failed for {dev}/{comp}: {e}")
                        print(f"[WARN] This usually means missing DLLs (e.g. CUDA) or hardware mismatch.")
                        del model
                        model = None
                        last_error = e
                        continue
                        
                except Exception as e:
                    print(f"[WARN] Failed to load with {dev}/{comp}: {e}")
                    last_error = e
                    continue
            
            if model is None:
                print(f"[ERROR] CRITICAL: Copied all fallbacks. Last error: {last_error}")
                if last_error:
                    raise last_error
                else:
                    raise RuntimeError("Failed to load any Whisper model configuration.")
            
            _model_cache[cache_key] = model
        else:
            print(f"[SUCCESS] Using cached model '{model_name}'")
    
    return _model_cache[cache_key]


# --- Core Functions ---

def extract_audio_from_video(video_path: str, output_path: Optional[str] = None) -> Optional[str]:
    """
    Extract audio from video file using direct FFmpeg command (Fast & Low Memory)
    
    Args:
        video_path: Path to video file
        output_path: Optional output path for audio file
        
    Returns:
        Path to extracted audio file
    """
    try:
        abs_video_path = os.path.abspath(video_path)
        print(f"[INFO] Extracting audio from video: {abs_video_path}")
        
        if not os.path.exists(abs_video_path):
            print(f"[ERROR] Video file does not exist at: {abs_video_path}")
        else:
            size_mb = os.path.getsize(abs_video_path) / (1024*1024)
            print(f"[INFO] File size: {size_mb:.2f} MB")
        
        # Check resources before processing
        resource_monitor = get_resource_monitor()
        if not resource_monitor.can_process():
            print(f"[WARN] Low resources, waiting...")
            resource_monitor.wait_for_resources(timeout=60)
        
        if output_path is None:
            # Create a localized temp file to avoid permission issues
            video_dir = os.path.dirname(video_path)
            temp_name = f"temp_audio_{os.path.basename(video_path)}.wav"
            output_path = os.path.join(video_dir, temp_name)
        
        # FFmpeg command: Extract audio to 16kHz mono WAV (Whisper native format)
        # -y: Overwrite output files
        # -vn: Disable video recording
        # -acodec pcm_s16le: PCM signed 16-bit little-endian
        # -ar 16000: Set audio sampling rate to 16000 Hz
        # -ac 1: Set number of audio channels to 1 (mono)
        # -threads: Limit CPU usage (production-grade)
        ffmpeg_exe = binary_manager.get_ffmpeg_path()
        max_threads = resource_monitor.get_ffmpeg_threads()
        
        command = [
            ffmpeg_exe, '-y', '-i', video_path,
            '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
            '-threads', str(max_threads),  # Production-grade CPU limiting
            output_path
        ]
        
        # Suppress output unless error
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        
        print(f"Audio extracted to: {output_path}")
        return output_path
        
    except subprocess.CalledProcessError as e:
        error_output = e.stderr.decode('utf-8') if e.stderr else str(e)
        if 'No such file' in error_output:
            raise FileNotFoundError(f"Video file not found. Please ensure the file was uploaded successfully.")
        elif 'Invalid data' in error_output:
            raise ValueError(f"Video file appears corrupted or invalid. Please try another video.")
        elif 'codec' in error_output.lower():
            raise ValueError(f"Video format not fully supported. Please convert to MP4 and try again.")
        else:
            # Raise detailed FFmpeg error but with user friendly prefix
            print(f"[FFMPEG ERROR DETAILS] {error_output}")
            raise RuntimeError(f"Failed to process audio. FFmpeg Error: {error_output[:200]}...")
            
    except Exception as e:
        print(f"Error extracting audio: {e}")
        import traceback
        traceback.print_exc()
        raise e # Re-raise to bubble up details


def transcribe_audio_with_whisper(audio_path: str, language: str = 'auto', model_name: str = 'base', check_cancelled=None) -> Tuple[Dict[str, Any], Optional[TranscriptionMetrics]]:
    """
    Transcribe audio using Faster Whisper (CTranslate2) with optimized parameters.
    
    Args:
        audio_path: Path to audio file
        language: Language code ('id', 'en', 'auto')
        model_name: Whisper model size
        
    Returns:
        Tuple (result_dict, metrics_obj)
    """
    try:
        start_time = time.perf_counter()
        
        # Load cached model
        # Using 'auto' device which often defaults to CPU on Mac CTranslate2 unless optimized
        model = get_whisper_model(model_name, device="auto", compute_type="int8")
        
        print(f"Transcribing audio...")
        
        # Optimized Transcribe Options
        transcribe_options = {
            'beam_size': 3,          # Reduced from 5 (diminishing returns) for speed
            'best_of': 3,            # Sample 3, pick best
            'temperature': 0.0,      # Deterministic, reduces hallucinations
            'condition_on_previous_text': False, # Prevent hallucination loops (CRITICAL FIX)
            'word_timestamps': True,
            'vad_filter': True,      # Filter out silence
            'vad_parameters': dict(
                min_silence_duration_ms=500,
                speech_pad_ms=400,
                threshold=0.5
            ),
            'compression_ratio_threshold': 2.2, # Stricter detection of repetition loops (was 2.4)
            'log_prob_threshold': -1.0,         # Filter low confidence
            'no_speech_threshold': 0.7,         # Aggressively filter non-speech (was 0.6)
            'repetition_penalty': 1.15,          # Penalize repetitive tokens (Production Grade Fix)
            'max_new_tokens': 128                # Prevent infinite loops (New Fix)
        }
        
        # Set language if specified
        if language != 'auto' and language:
            transcribe_options['language'] = language
        
        # Transcribe
        segments_generator, info = model.transcribe(audio_path, **transcribe_options)
        
        # Warning for low confidence language detection
        detected_lang = info.language
        lang_prob = info.language_probability
        
        if lang_prob < 0.7:
             print(f"[WARN] Low language detection confidence: {lang_prob:.2f}")
             if language == 'auto' and lang_prob < 0.4:
                 print(f"[WARN] Very low confidence, defaulting to English logic might be safer.")
        
        # Process segments safely
        segments = []
        failed_segments = 0
        all_word_confidences = []
        num_words_total = 0
        
        for idx, segment in enumerate(segments_generator):
            # CHECK CANCELLATION
            if check_cancelled and check_cancelled():
                print(f"[INFO] Transcription cancelled by user.")
                raise Exception("Job Cancelled")

            try:
                seg_dict = {
                    'start': segment.start,
                    'end': segment.end,
                    'text': segment.text.strip(),
                    'words': []
                }
                
                # Sanity check timestamps
                if seg_dict['end'] <= seg_dict['start']:
                    failed_segments += 1
                    continue
                
                if segment.words:
                    for word in segment.words:
                        try:
                            w_prob = getattr(word, 'probability', 0.0)
                            all_word_confidences.append(w_prob)
                            num_words_total += 1
                            
                            seg_dict['words'].append({
                                'word': word.word.strip(),
                                'start': word.start,
                                'end': word.end,
                                'probability': w_prob
                            })
                        except Exception as e:
                            print(f"⚠️ Failed to process word in segment {idx}: {e}")
                            continue
                
                segments.append(seg_dict)
                
            except Exception as e:
                print(f"[WARN] Failed to process segment {idx}: {e}")
                failed_segments += 1
                continue
                
        if failed_segments > 0:
            print(f"[WARN] {failed_segments} segments failed to process during correct loop")

        # --- Metrics Calculation ---
        p_time = time.perf_counter() - start_time
        audio_dur = segments[-1]['end'] if segments else 0.1
        
        metrics = TranscriptionMetrics(
            audio_duration_sec=audio_dur,
            processing_time_sec=p_time,
            real_time_factor=p_time / max(audio_dur, 0.1),
            model_name=model_name,
            language=detected_lang,
            language_confidence=lang_prob,
            num_segments=len(segments),
            num_words=num_words_total,
            avg_word_confidence=np.mean(all_word_confidences) if all_word_confidences else 0.0
        )
        
        print(f"Transcription complete!")
        print(f"   Language: {detected_lang} ({lang_prob:.2%})")
        print(f"   Metrics: {metrics.real_time_factor:.2f}x RT, {metrics.avg_word_confidence:.1%} conf")
        
        result_dict = {
            'segments': segments,
            'language': detected_lang
        }
        
        return result_dict, metrics
        
    except Exception as e:
        print(f"Error transcribing audio: {e}")
        import traceback
        traceback.print_exc()
        raise RuntimeError(f"Failed to run AI Transcription. Please try again in a moment.")


def validate_transcription_quality(phrase_timings: List[Dict], min_confidence: float = 0.5) -> List[Dict]:
    """
    Validate transcription quality and flag suspicious segments pattern-analysis
    """
    warnings = []
    
    for i, phrase in enumerate(phrase_timings):
        words = phrase.get('words', [])
        
        if words:
            # Check confidence
            probs = [w.get('probability', 0) for w in words]
            if probs:
                avg_conf = sum(probs) / len(probs)
                if avg_conf < min_confidence:
                    warnings.append({
                        'type': 'low_confidence',
                        'segment': i,
                        'confidence': avg_conf,
                        'text': phrase['text'][:30]
                    })
            
            # Check repetition
            txts = [w.get('text', '').lower() for w in words]
            if len(txts) > 3:
                for j in range(len(txts)-2):
                    if txts[j] == txts[j+1] == txts[j+2]:
                         warnings.append({
                            'type': 'repetition',
                            'segment': i,
                            'repeated_word': txts[j]
                        })
                         break
                         
    if warnings:
        print(f"[WARN] QUALITY WARNINGS: Found {len(warnings)} potential issues")
    
    return warnings


def generate_phrase_timings(whisper_result: Dict, min_duration: float = 0.1, max_duration: float = 8.0, max_chars_per_phrase: int = 60) -> List[Dict]:
    """
    Generate subtitle-optimized phrase timings with smart segmentation based on sentence boundaries and pauses.
    """
    if not whisper_result or 'segments' not in whisper_result:
        return []
    
    phrase_timings = []
    
    # Flatten all words first to easier process streams
    all_words = []
    for segment in whisper_result['segments']:
        if 'words' in segment and segment['words']:
            all_words.extend(segment['words'])
        else:
            # Fallback for segment without word timestamps (rare with word_timestamps=True)
            # Create a dummy single word
            # Clamp segment duration to max 3s per word estimate or hard cap
            dur = segment['end'] - segment['start']
            if dur > 5.0:
                print(f"[WARN] Segment duration {dur}s too long for text '{segment['text']}', clamping end.")
                # Heuristic: 0.5s per word or max 5s
                word_count = len(segment['text'].split())
                new_dur = min(dur, max(1.5, word_count * 0.5))
                segment_end = segment['start'] + new_dur
            else:
                segment_end = segment['end']

            all_words.append({
                'word': segment['text'],
                'start': segment['start'],
                'end': segment_end,
                'probability': 1.0
            })

    if not all_words:
        return []

    # Process word stream
    current_phrase = []
    
    for i, w in enumerate(all_words):
        w_text = w.get('word', '').strip()
        if not w_text:
            continue
            
        current_phrase.append(w)
        
        # --- FIX: Clamp individual word durations ---
        # Sometimes whisper gives a word 5s duration if silence follows.
        # We cap it to prevent "stuck" persistence.
        
        # Smart Clamping based on word length
        # Short words (I, the, it) shouldn't be on screen for 3 seconds.
        word_len = len(w_text)
        max_word_dur = 1.5 if word_len < 5 else 3.0
        
        word_start = w.get('start', 0)
        word_end = w.get('end', 0)
        
        if (word_end - word_start) > max_word_dur:
            w['end'] = word_start + max_word_dur
            # print(f"[FIX] Clamped word '{w_text}' duration for stuck prevention")

        # --- FIX: Prevent Overlap ---
        # Ensure this word doesn't overlap with the NEXT word
        if i < len(all_words) - 1:
            next_start = all_words[i+1].get('start', 0)
            if w['end'] > next_start:
                 w['end'] = next_start
        
        # Decision logic to break phrase
        # 1. Punctuation
        is_sentence_end = any(p in w_text for p in ['.', '!', '?', '。', '...'])
        
        # 2. Pause
        is_pause = False
        if i < len(all_words) - 1:
            pause_dur = all_words[i+1].get('start', 0) - w.get('end', 0)
            if pause_dur > 0.5:
                is_pause = True
        
        # 3. Length
        current_text_len = len(' '.join([x['word'] for x in current_phrase]))
        is_too_long = current_text_len > max_chars_per_phrase
        
        # 4. End of stream
        is_last = (i == len(all_words) - 1)
        
        if is_sentence_end or is_pause or is_too_long or is_last:
            # Construct phrase
            phrase_text = ' '.join([x.get('word', '').strip() for x in current_phrase]).strip()
            
            if not phrase_text:
                current_phrase = []
                continue
                
            start = current_phrase[0].get('start', 0)
            end = current_phrase[-1].get('end', 0)
            duration = end - start
            
            # Filter bad timings
            if min_duration <= duration:
                # If too long, maybe we force split? For now just clamp logic is handled by is_too_long
                
                # Transform to final format
                final_words = []
                for pw in current_phrase:
                    final_words.append({
                        'text': pw.get('word', '').strip(),
                        'start': pw.get('start', 0),
                        'end': pw.get('end', 0),
                        'probability': pw.get('probability', 0)
                    })
                
                phrase_timings.append({
                    'text': phrase_text,
                    'start': start,
                    'end': end,
                    'duration': duration,
                    'words': final_words
                })
            
            current_phrase = []
            
    print(f"[INFO] Generated {len(phrase_timings)} phrase timings from word stream")
    return phrase_timings


def filter_hallucinations(phrase_timings: List[Dict]) -> List[Dict]:
    """
    Removes segments that are likely ASR hallucinations (e.g. 'Terima kasih' in silence).
    Refined logic:
    1. STRICT_PHRASES (Subtitle by, etc): Always drop.
    2. CONVERSATIONAL_PHRASES (Terima kasih, Thank you): 
       - Drop if duration > 5.0s (Hallucination stretching).
       - Drop if sequence repetition.
       - Allow if legitimate short duration (1-4s).
    """
    if not phrase_timings:
        return []
        
    STRICT_PHRASES = [
        "subtitle by", "amara.org", "transcribed by", "copyright", "all rights reserved",
        "subtitles by", "captioned by", "community reviews"
    ]
    
    CONVERSATIONAL_PHRASES = [
        "terima kasih", "thank you", "thanks for watching"
    ]
        
    cleaned_timings = []
    dropped_count = 0
    
    for i, phrase in enumerate(phrase_timings):
        text = phrase.get('text', '').strip().lower()
        start = phrase.get('start', 0)
        end = phrase.get('end', 0)
        duration = end - start
        
        # 1. Strict Filter
        if any(hp in text for hp in STRICT_PHRASES):
             print(f"[FILTER] Dropping strict hallucination: '{phrase['text']}'")
             dropped_count += 1
             continue
             
        # 2. Conversational Filter
        is_conversational_suspect = any(hp in text for hp in CONVERSATIONAL_PHRASES)
        if is_conversational_suspect and len(text) < 40:
            # Check A: Duration vs Length
            # Real "Thank you" is quick. Hallucinated one often fills the silence.
            if duration > 4.0: 
                print(f"[FILTER] Dropping stretched hallucination: '{phrase['text']}' (Duration: {duration:.1f}s)")
                dropped_count += 1
                continue
                
            # Check B: Repetition
            if i > 0 and cleaned_timings:
                prev_text = cleaned_timings[-1].get('text', '').strip().lower()
                if prev_text == text:
                     print(f"[FILTER] Dropping conversational repetition: '{phrase['text']}'")
                     dropped_count += 1
                     continue
             
        cleaned_timings.append(phrase)
        

    if dropped_count > 0:
        print(f"[INFO] Filtered out {dropped_count} hallucinated/repeated segments")
        
    return cleaned_timings


def clean_repetitive_content(phrase_timings: List[Dict], max_repeats: int = 3) -> List[Dict]:
    """
    Cleans up excessive word repetitions (hallucinations) within phrases.
    Uses fuzzy matching to detect "soft" loops (e.g. "keren. keren, keren").
    """
    if not phrase_timings:
        return []
    
    cleaned_count = 0
    
    for phrase in phrase_timings:
        words = phrase.get('words', [])
        if not words or len(words) < 3:
            continue
            
        new_words = []
        
        # Robust adjacent repetition removal
        # We look ahead to catch patterns like "A A A" or "A B A B A B"
        # For now, we focus on the simple generic "word loop" (A A A A)
        
        i = 0
        while i < len(words):
            current_word = words[i]
            
            # Normalize current
            raw_curr = current_word.get('text', '').strip()
            norm_curr = "".join(c for c in raw_curr if c.isalnum()).lower()
            
            if not norm_curr:
                new_words.append(current_word)
                i += 1
                continue
                
            # Look ahead for repetitions
            repeats = 0
            j = i + 1
            timestamps_gap = 0
            
            while j < len(words):
                next_word = words[j]
                raw_next = next_word.get('text', '').strip()
                norm_next = "".join(c for c in raw_next if c.isalnum()).lower()
                
                # Calculate similarity for fuzzy match (handle typos/punctuation diffs)
                similarity = SequenceMatcher(None, norm_curr, norm_next).ratio()
                
                # Threshold 0.85 allows for "keren" vs "kerren" or "keren."
                if similarity > 0.85:
                    repeats += 1
                    j += 1
                else:
                    break
            
            # Decide what to keep
            # We keep the first instance + up to max_repeats-1 subsequent instances
            # So if max_repeats=3, we allow 3 total (1 original + 2 repeats)
            
            # Special case: If the word is very short (<3 chars) allow more? No, usually hallucination.
            
            keep_count = 1 + min(repeats, max_repeats - 1)
            
            # If we have massive repetition (e.g. 10 times), it's definitely hallucination
            # Loop-prevention: If repeats > 5, reduce allow count to 1 (just say it once)
            if repeats > 5:
                keep_count = 1
                
            # Add the words we keep
            new_words.extend(words[i : i + keep_count])
            
            # Skip the ones we drop
            dropped_in_sequence = (1 + repeats) - keep_count
            if dropped_in_sequence > 0:
                cleaned_count += dropped_in_sequence
                
            # Advance pointer
            i += (1 + repeats)

        # If we modified the words list
        if len(new_words) < len(words):
            phrase['words'] = new_words
            # Reconstruct text from kept words (preserving spaces/punctuation best effort)
            # To be precise, we should just join them. 
            phrase['text'] = "".join([w.get('text', '') for w in new_words]).strip()
            # If words have leading space logic (Whisper usually separates logic), this simple join might be tight.
            # But 'text' field is less critical than 'words' timings for the renderer.
            # Let's try to be safer by checking if original text had spaces.
            # Alternative: just join with space. 
            # Whisper words usually come with implicit spacing? 
            # Actually faster-whisper words often lack leading space in 'text' field sometimes, 
            # but usually it's safer to join with space if we don't know.
            # However, looking at original code: ' '.join(...)
            phrase['text'] = ' '.join([x.get('text', '').strip() for x in new_words])
            
    if cleaned_count > 0:
        print(f"[INFO] Cleaned {cleaned_count} repetitive words from transcript (Fuzzy)")
        
    return phrase_timings



def clean_phrase_level_repetition(phrase_timings: List[Dict]) -> List[Dict]:
    """
    Cleans up phrase-level repetitions (hallucination loops).
    Only drops consecutive identical phrases if they occur within a short timeframe (loops).
    Preserves repetitions that are likely intentional emphasis or separate sentences (gap > 2s).
    Uses fuzzy matching to detect specific looping patterns common in mixed-language audio.
    """
    if not phrase_timings:
        return []
    
    # print(f"[DEBUG] clean_phrase_level_repetition: Input has {len(phrase_timings)} phrases")
        
    cleaned = []
    dropped_count = 0
    dropped_details = []
    
    for i, phrase in enumerate(phrase_timings):
        if i == 0:
            cleaned.append(phrase)
            continue
            
        prev_phrase = cleaned[-1]
        
        # Calculate similarity text
        curr_text = "".join(c for c in phrase.get('text', '').lower() if c.isalnum())
        prev_text = "".join(c for c in prev_phrase.get('text', '').lower() if c.isalnum())
        
        # Check time gap (start of current - end of previous)
        time_gap = phrase.get('start', 0) - prev_phrase.get('end', 0)
        
        # Fuzzy match
        is_repeat = False
        
        if not curr_text or not prev_text:
            cleaned.append(phrase)
            continue
            
        # 1. Exact match (fast path)
        if curr_text == prev_text:
             is_repeat = True
        else:
             # 2. Fuzzy match (slow path but necessary for "keren" vs "keren.")
             ratio = SequenceMatcher(None, curr_text, prev_text).ratio()
             if ratio > 0.85: # Allow small variations
                 is_repeat = True
                 
        if is_repeat:
            # If gap is small (hallucination loop), drop it
            # If gap is large (new sentence), keep it
            if time_gap < 2.0:
                dropped_count += 1
                dropped_details.append(f"Phrase #{i} '{phrase.get('text', '')}' at {phrase.get('start', 0):.2f}s (gap: {time_gap:.2f}s)")
                continue
            else:
                # print(f"[DEBUG] Keeping repeated phrase '{phrase.get('text', '')}' (gap: {time_gap:.2f}s > 2.0s)")
                pass
            
        cleaned.append(phrase)
        
    if dropped_count > 0:
        print(f"[INFO] Cleaned {dropped_count} repetitive phrases (loops) from transcript (Fuzzy)")
        for detail in dropped_details[:5]:  # Show first 5
            print(f"  - Dropped: {detail}")
        if len(dropped_details) > 5:
            print(f"  - ... and {len(dropped_details) - 5} more")
    
    # print(f"[DEBUG] clean_phrase_level_repetition: Output has {len(cleaned)} phrases (dropped {dropped_count})")
        
    return cleaned


def transcribe_video(video_path: str, language: str = 'auto', model_name: str = 'base', cleanup_audio: bool = True, check_cancelled=None) -> Tuple[List[Dict], str]:
    """
    Main function: Extract audio from video and transcribe it using Faster Whisper
    """
    audio_path = None
    
    try:
        print(f"\\n{'='*60}")
        print(f"[INFO] VIDEO TRANSCRIPTION STARTING (Faster-Whisper)")
        print(f"{'='*60}")
        print(f"Video: {video_path}")
        print(f"Language: {language}")
        print(f"Model: {model_name}")
        print(f"{'='*60}\\n")
        
        # Step 1: Extract audio
        # Now raises Exception on failure
        audio_path = extract_audio_from_video(video_path)
        
        # Step 2: Transcribe audio
        # Now raises Exception on failure
        # Step 2: Transcribe
        result, metrics = transcribe_audio_with_whisper(audio_path, language, model_name, check_cancelled=check_cancelled)
        
        # Detected Language
        detected_language = result['language']
        if not result:
             raise RuntimeError("No voice/conversation detected in this video.")
            
        # Optional: Print metrics summary
        if metrics:
            print(f"[INFO] Stats: {metrics.num_words} words, {metrics.avg_word_confidence:.2%} confidence")
        
        # Step 3: Generate phrase timings
        phrase_timings = generate_phrase_timings(result)
        
        # Step 3.5: Filter Hallucinations & Clean Repetition
        phrase_timings = clean_repetitive_content(phrase_timings)
        phrase_timings = clean_phrase_level_repetition(phrase_timings)
        phrase_timings = filter_hallucinations(phrase_timings)
        
        # Step 4: Validate
        validate_transcription_quality(phrase_timings)
        
        print(f"\\n{'='*60}")
        print(f"VIDEO TRANSCRIPTION COMPLETE")
        print(f"{'='*60}")
        print(f"Total phrases extracted: {len(phrase_timings)}")

        validate_transcription_quality(phrase_timings)
        
        print(f"\\n{'='*60}")
        print(f"VIDEO TRANSCRIPTION COMPLETE")
        print(f"{'='*60}")
        print(f"Total phrases extracted: {len(phrase_timings)}")
        print(f"{'='*60}\\n")
        
        return phrase_timings, metrics.language
        
    except Exception as e:
        # We catch, print traceback for log, but RE-RAISE so usage code sees the error
        print(f"Error in transcribe_video: {e}")
        import traceback
        traceback.print_exc()
        raise e
        
    finally:
        # Cleanup temporary audio file
        if cleanup_audio and audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
                print(f"Cleaned up temporary audio file")
            except:
                pass


def transcribe_videos_batch(video_paths: List[str], language='auto', model_name='base', max_workers=4) -> Dict[str, List[Dict]]:
    """
    Process multiple videos in parallel using shared cached model
    """
    print(f"[INFO] Batch processing {len(video_paths)} videos with {max_workers} workers...")
    
    # Pre-load model once
    get_whisper_model(model_name)
    
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_video = {
            executor.submit(transcribe_video, video, language, model_name): video 
            for video in video_paths
        }
        
        for future in as_completed(future_to_video):
            video = future_to_video[future]
            try:
                results[video] = future.result()
            except Exception as e:
                print(f"[ERROR] Failed to process {video}: {e}")
                results[video] = []
    
    return results


# Test function
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python audio_transcriber.py <video_path> [language] [model]")
        print("Example: python audio_transcriber.py video.mp4 id base")
        sys.exit(1)
    
    video_path = sys.argv[1]
    language = sys.argv[2] if len(sys.argv) > 2 else 'auto'
    model = sys.argv[3] if len(sys.argv) > 3 else 'base'
    
    if not os.path.exists(video_path):
        print(f"Error: Video file not found: {video_path}")
        sys.exit(1)
    
    phrase_timings = transcribe_video(video_path, language, model)
    
    print(f"\\n[INFO] RESULTS:")
    print(f"Total phrases: {len(phrase_timings)}")
    if phrase_timings:
        print(f"\\nFirst 3 phrases:")
        for i, phrase in enumerate(phrase_timings[:3], 1):
            print(f"  {i}. [{phrase['start']:.2f}s - {phrase['end']:.2f}s] {phrase['text'][:50]}")
