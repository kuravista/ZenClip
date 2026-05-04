
from moviepy import TextClip, CompositeVideoClip
import numpy as np
from services.media.subtitle.utils.text import measure_real_height
from services.media.subtitle.utils.fonts import get_font_path
from services.media.subtitle.utils.image import create_emoji_clip
import re

# Issue #7: Config
RAPID_CONFIG = {
    'fontsize_multiplier': 1.5,
    'min_duration': 0.05,
    'fade_threshold': 0.2,
    'fade_duration_ratio': 0.3,
    'fade_duration_max': 0.1,
    'vertical_position_default': 75
}

def create_rapid_fire_subtitles(config, video_clip, phrase_timings, clip_start, clip_end):
    """
    Creates single-word subtitles that appear one by one (Rapid Fire).
    Optimized for fast speech sync with error recovery.
    """
    subtitle_clips = []
    w, h = video_clip.size
    
    highlight_map = config.get("highlight_map", {})
    emoji_map = config.get("emoji_map", {})
    smart_enabled = config.get("smart_subtitles", False)
    if highlight_map or emoji_map:
         smart_enabled = True
    
    # Issue #1: Font Resolution
    font_name = config.get('font', 'Arial')
    # Font path resolved here or inside loop? Better inside loop if we want to support per-word fonts (unlikely)
    # But get_font_path caches, so it's fast.
    
    fontsize = int(config.get('fontsize', 70) * RAPID_CONFIG['fontsize_multiplier'])
    color = config.get('color', config.get('text_color', 'white'))
    stroke_color = config.get('stroke_color', 'black')
    stroke_width = int(config.get('stroke_width', 2))
    
    # 1. Collect all words with absolute timing
    all_words = []
    for phrase in phrase_timings:
        if phrase['end'] < (clip_start - 1.5) or phrase['start'] > (clip_end + 1.5):
            continue
            
        words = phrase.get('words', [])
        if not words: continue
        
        for word_info in words:
            w_start = word_info['start'] - clip_start
            w_end = word_info['end'] - clip_start
            
            # Skip words outside clip range
            if w_end < 0: continue
            if w_start > (clip_end - clip_start): continue
                
            all_words.append({
                'text': word_info['text'],
                'start': w_start,
                'end': w_end, 
                'orig_duration': w_end - w_start
            })
    
    # Sort by start time
    all_words.sort(key=lambda x: x['start'])
    
    # 2. Strict Timing Logic (Cut Back Strategy)
    final_clips_data = []
    
    for i in range(len(all_words)):
        current_word = all_words[i]
        
        start_time = max(0, current_word['start'])
        
        # Determine end time
        if i < len(all_words) - 1:
            next_word_start = all_words[i+1]['start']
            # If next word starts before this one ends, cut this one short
            end_time = min(current_word['end'], next_word_start)
        else:
            end_time = current_word['end']
            
        duration = end_time - start_time
        
        # Minimum duration floor
        if duration < RAPID_CONFIG['min_duration']:
            duration = RAPID_CONFIG['min_duration']
            
        final_clips_data.append({
            'text': current_word['text'],
            'start': start_time,
            'duration': duration
        })

    # 3. Create MoviePy Clips
    for item in final_clips_data:
        w_start = item['start']
        dur = item['duration']
        word_text = item['text']
        
        word_clean = re.sub(r'[^\w\s]', '', word_text).lower().strip()
        
        current_color = color
        current_stroke = stroke_color
        
        if smart_enabled and word_clean in highlight_map:
                current_color = highlight_map[word_clean]
        
        # Issue #1: Robust Font Path
        font_path = get_font_path(font_name)
        
        text_padded = word_text + "\n "
        
        txt_clip = TextClip(
            text=text_padded,
            font=font_path,
            font_size=fontsize,
            color=current_color,
            stroke_color=current_stroke,
            stroke_width=stroke_width,
            method='label'
        )
        
        # Issue #6: Error Recovery
        try:
            real_h = measure_real_height(txt_clip, buffer=15)
            # Ensure real_h is valid and not larger than clip height
            if real_h > 0 and real_h < txt_clip.h:
                txt_clip = txt_clip.cropped(y2=real_h)
        except Exception as e:
            # Degrade gracefully - print warning but keep original uncropped clip
            if config.get('debug_logging'):
                print(f"  ⚠️ Cropping failed for '{word_text}': {e}")
        
        # Max width constraint
        max_w = int(w * 0.9)
        if txt_clip.w > max_w:
            txt_clip = txt_clip.resized(width=max_w)
        
        # Positioning
        vertical_pos_pct = config.get('vertical_position', RAPID_CONFIG['vertical_position_default'])
        y_pos = int((h * (vertical_pos_pct / 100.0)) - (txt_clip.h / 2))
        
        txt_clip = txt_clip.with_position(('center', y_pos))
        txt_clip = txt_clip.with_start(w_start).with_duration(dur)

        # Adaptive Animation
        if dur > RAPID_CONFIG['fade_threshold']:
            try:
                from moviepy.video.fx import CrossFadeIn
                fade_dur = min(RAPID_CONFIG['fade_duration_max'], dur * RAPID_CONFIG['fade_duration_ratio'])
                txt_clip = txt_clip.with_effects([CrossFadeIn(duration=fade_dur)])
            except ImportError:
                pass
        
        subtitle_clips.append(txt_clip)
        
        # Emoji Support
        if smart_enabled and word_clean in emoji_map:
            emoji_char = emoji_map[word_clean]
            emoji_size = int(fontsize * 1.5)
            try:
                emoji_clip = create_emoji_clip(emoji_char, size=emoji_size)
                
                if emoji_clip:
                    e_x = w/2 - emoji_size/2
                    e_y = h/2 - fontsize - emoji_size/2 - 20
                    
                    emoji_clip = emoji_clip.with_position((e_x, e_y))
                    emoji_clip = emoji_clip.with_start(w_start).with_duration(dur)
                    subtitle_clips.append(emoji_clip)
            except Exception as e:
                print(f"Failed to create emoji clip: {e}")

    return subtitle_clips
