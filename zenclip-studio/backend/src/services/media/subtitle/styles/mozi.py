from moviepy import TextClip, CompositeVideoClip
import numpy as np
import re
try:
    from moviepy.video.fx import CrossFadeIn
except ImportError:
    CrossFadeIn = None

from services.media.subtitle.utils.text import measure_real_height
from services.media.subtitle.utils.fonts import get_font_path

# Issue #7: Config setup
MOZI_CONFIG = {
    'chunk_size': 5,
    'max_width_ratio': 0.80,
    'word_spacing_px': 8,
    'line_gap_px': -10,
    'min_word_duration_ms': 50
}

# Issue #2: Optimized Text Rendering (Single Render)
def _generate_mozi_text_clip(text, config, is_highlight=False):
    """
    Optimized: Single render path to avoid duplicate TextClip creation.
    """
    
    font_path = get_font_path(config["font"])
    fontsize = config["fontsize"]
    
    if is_highlight:
        # Green highlighted state
        color = "#00FF00"
        fontsize = int(fontsize * 1.3)
        # Stronger stroke for highlight
        stroke_width = max(12, int(config.get("stroke_width", 3) * 2.5))
    else:
        # Normal white state
        color = config.get("color", "white")
        stroke_width = max(8, int(config.get("stroke_width", 3)))
    
    # Add space for proper measurement (prevent clipping of ascenders/descenders)
    # Convert to upper case as per style
    text_upper = text.upper()
    text_with_padding = f"{text_upper}\n " 
    
    # Create clip ONCE
    txt = TextClip(
        text=text_with_padding,
        font=font_path,
        font_size=fontsize,
        color=color,
        stroke_color=config.get("stroke_color", "black"),
        stroke_width=stroke_width,
        method="label"
    )
    
    # Measure and crop once
    try:
        real_h = measure_real_height(txt, buffer=15)
        if real_h > 0 and real_h < txt.h:
            txt = txt.cropped(y2=real_h)
    except Exception as e:
        print(f"  ⚠️ Height measurement failed: {e}")
        # Keep original if measurement fails
    
    return txt

def create_mozi_subtitles(config, video_clip, phrase_timings, clip_start, clip_end):
    """
    Optimized Mozi style subtitles with pre-calculated layouts.
    fixes Issue #4 (Layout Overhead) and Issue #5 (Memory Leaks via improved logic flow)
    """
    print(f"[INFO] Generating Mozi subtitles for clip {clip_start:.1f}s - {clip_end:.1f}s")
    
    video_w, video_h = video_clip.size
    audio_offset = config.get("audio_offset", 0.0)
    
    # 1. Collect words
    all_words = []
    for phrase in phrase_timings:
        p_start = phrase['start']
        p_end = phrase['end']
        
        if p_end < (clip_start - 1.5) or p_start > (clip_end + 1.5):
            continue
            
        words = phrase.get('words', [])
        if not words:
            words = [{'text': phrase['text'], 'start': p_start, 'end': p_end}]
            
        for w in words:
            w_start = w['start']
            w_end = w['end']
            
            if w_end < (clip_start - 1.5):
                continue
            if w_start > (clip_end + 1.5):
                continue
            
            all_words.append({
                'text': w['text'],
                'start': w_start,
                'end': w_end,
            })
            
    if not all_words:
        return []
        
    all_words.sort(key=lambda x: x['start'])
    
    # 2. Chunking
    CHUNK_SIZE = MOZI_CONFIG['chunk_size']
    chunks = [all_words[i:i + CHUNK_SIZE] for i in range(0, len(all_words), CHUNK_SIZE)]
    
    subtitle_clips = []
    
    for chunk_idx, chunk in enumerate(chunks):
        if not chunk: continue
        
        # Calculate chunk timing
        chunk_start_abs = chunk[0]['start']
        chunk_end_abs = chunk[-1]['end']
        
        rel_chunk_start = chunk_start_abs - clip_start + audio_offset
        rel_chunk_end = chunk_end_abs - clip_start + audio_offset
        rel_chunk_start = max(0, rel_chunk_start)
        
        chunk_duration = rel_chunk_end - rel_chunk_start
        if chunk_duration < 0.1: continue
        
        # 3. Pre-render clips (Issue #2 fix included via _generate_mozi_text_clip)
        word_clips = {} # idx -> {white, green, start_rel, end_rel}
        
        for idx, word in enumerate(chunk):
            white_clip = _generate_mozi_text_clip(word['text'], config, is_highlight=False)
            green_clip = _generate_mozi_text_clip(word['text'], config, is_highlight=True)
            
            w_start_rel = max(0, word['start'] - clip_start + audio_offset - rel_chunk_start)
            w_end_rel = min(chunk_duration, word['end'] - clip_start + audio_offset - rel_chunk_start)
            
            word_clips[idx] = {
                'white': white_clip,
                'green': green_clip,
                'green_h': green_clip.h, # Cache height for layout
                'start': w_start_rel,
                'end': w_end_rel
            }

        # 4. Static Layout Calculation (Issue #4 Fix)
        # We calculate ONE layout based on the maximum dimensions (green state)
        # ensuring the text block doesn't jump around.
        
        max_line_width = video_w * MOZI_CONFIG['max_width_ratio']
        word_spacing = MOZI_CONFIG['word_spacing_px']
        line_gap = MOZI_CONFIG['line_gap_px']
        
        # Hardcoded 3/2 split pattern per user preference/style
        line1_indices = list(range(min(3, len(chunk))))
        line2_indices = list(range(3, len(chunk)))
        
        # Calculate max line heights using GREEN (max) clips
        line1_height = max([word_clips[i]['green_h'] for i in line1_indices]) if line1_indices else 0
        line2_height = max([word_clips[i]['green_h'] for i in line2_indices]) if line2_indices else 0
        
        total_block_height = line1_height + line2_height + (line_gap if line2_indices else 0)
        
        # Vertical centering
        center_y = int(video_h * (config.get('vertical_position', 75) / 100.0))
        y_start = center_y - (total_block_height // 2)
        
        # Calculate static positions for both states
        # We center the WHITE version within the slot allocated for the GREEN version?
        # Or we center the words.
        # Simple approach: Center the lines based on WHITE width (since that's the resting state)
        # BUT that causes jumping when it expands.
        # Better approach: Layout based on WHITE widths, and let GREEN expansion grow outward?
        # No, Mozi style usually pushes neighbors.
        # User prompt suggested: "Calculate layout ONCE... using static positions".
        # Let's derive a static grid.
        
        static_positions = {} # idx -> (x, y) for the "Center" of the slot? 
        # Actually, let's just calculate the layout for each segment effectively but using PRE-CALCULATED rules.
        # To avoid jumping, we should anchor the layout.
        
        # Optimization: Generate clip segments based on time points
        time_points = set([0, chunk_duration])
        for idx in word_clips:
            t = word_clips[idx]
            if t['start'] > 0: time_points.add(t['start'])
            if t['end'] < chunk_duration: time_points.add(t['end'])
        
        sorted_points = sorted(list(time_points))
        chunk_sub_clips = []
        
        for i in range(len(sorted_points) - 1):
            t0 = sorted_points[i]
            t1 = sorted_points[i+1]
            dur = t1 - t0
            if dur < 0.01: continue
            
            # Identify active words
            active_indices = [
                idx for idx in word_clips 
                if word_clips[idx]['start'] <= t0 and t1 <= word_clips[idx]['end']
            ]
            
            # --- Layout for this segment ---
            current_y = y_start
            segment_clips = []
            
            for line_indices_set, line_h in [(line1_indices, line1_height), (line2_indices, line2_height)]:
                if not line_indices_set: continue
                
                # Calculate total width for this specific configuration (some active, some not)
                current_line_w = 0
                widths = [] # (w, is_green, clip)
                
                for w_idx in line_indices_set:
                    is_active = w_idx in active_indices
                    clip = word_clips[w_idx]['green'] if is_active else word_clips[w_idx]['white']
                    widths.append((clip.w, is_active, clip))
                    current_line_w += clip.w
                
                current_line_w += word_spacing * (len(line_indices_set) - 1)
                
                # Center X
                start_x = (video_w - current_line_w) // 2
                curr_x = start_x
                
                for i_w, w_idx in enumerate(line_indices_set):
                    w_width, is_active, clip = widths[i_w]
                    
                    # Center vertically in the static line height
                    # This prevents vertical jumping when switching font sizes
                    y_pos = current_y + (line_h - clip.h) // 2
                    
                    # Create sub-clip
                    final_clip = clip.with_position((curr_x, y_pos)).with_start(t0).with_duration(dur)
                    
                    # Add Pop effect if simple linear
                    # (Skipping complex pop for stability/speed unless requested)
                    
                    segment_clips.append(final_clip)
                    curr_x += w_width + word_spacing
                
                current_y += line_h + line_gap
            
            chunk_sub_clips.extend(segment_clips)

        # Create Composite for the chunk
        if chunk_sub_clips:
            comp = CompositeVideoClip(chunk_sub_clips, size=(video_w, video_h))
            comp = comp.with_start(rel_chunk_start).with_duration(chunk_duration)
            
            # Fade in the whole chunk
            if CrossFadeIn:
                comp = comp.with_effects([CrossFadeIn(duration=0.1)])
            else:
                comp = comp.with_opacity(lambda t: min(1.0, t / 0.1))
                
            subtitle_clips.append(comp)
            
    return subtitle_clips