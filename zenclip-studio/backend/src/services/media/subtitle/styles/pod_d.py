import math
from services.media.subtitle.utils.fonts import get_font_path
from moviepy import TextClip
import re

def create_pod_d_subtitles(config, video_clip, phrase_timings, clip_start, clip_end):
    """
    Creates "Pod D" subtitles (max 3 words at a time).
    Based on Rapid Pro but:
    - Default color is Pastel Pink (#FFB6C1)
    - No Glow
    - Has Stroke
    """
    subtitle_clips = []
    w, h = video_clip.size
    
    # Config
    font = config.get('font', 'Arial')
    fontsize = int(config.get('fontsize', 70))
    
    # Pod D Specific Colors
    PINK_COLOR = '#FFB6C1'
    highlight_color = config.get('highlight_color', 'yellow') 
    stroke_color = config.get('stroke_color', 'black')
    stroke_width = int(config.get('stroke_width', 0))
    # Enforce default stroke if not provided or 0, matching frontend
    if stroke_width <= 0:
        stroke_width = 3
    
    # 1. Collect all words
    all_words = []
    for phrase in phrase_timings:
        if phrase['end'] < (clip_start - 1.5) or phrase['start'] > (clip_end + 1.5):
            continue
        
        words = phrase.get('words', [])
        if not words: continue 
        
        for word_info in words:
            w_start = word_info['start'] - clip_start
            w_end = word_info['end'] - clip_start
            
            if w_end < -1.5 or w_start > (clip_end - clip_start + 1.5): continue
            
            all_words.append({
                'text': word_info['text'],
                'start': w_start,
                'end': w_end
            })
            
    all_words.sort(key=lambda x: x['start'])
    
    if not all_words: return []

    # 2. Group into chunks (Max 3 words)
    chunks = []
    current_chunk = []
    
    for word in all_words:
        current_chunk.append(word)
        if len(current_chunk) >= 3:
            chunks.append(current_chunk)
            current_chunk = []
            
    if current_chunk:
        chunks.append(current_chunk)
        
    # 3. Create Clips
    for chunk in chunks:
        if not chunk: continue
        
        chunk_start = chunk[0]['start']
        chunk_end = chunk[-1]['end']
        duration = chunk_end - chunk_start
        
        if duration < 0.1: duration = 0.1
        
        chunk_size = len(chunk)
        font_path = get_font_path(font)
        
        # Calculate visual layout
        temp_clips = []
        total_w = 0
        max_h = 0
        
        for i, w_obj in enumerate(chunk):
            w_text = w_obj['text']
            
            # Color Logic
            w_color = PINK_COLOR
            
            # All words are now Pink.
            
            txt_clip = TextClip(
                text=w_text,
                font=font_path,
                font_size=fontsize,
                color=w_color,
                stroke_color=stroke_color,
                stroke_width=stroke_width,
                method='label',
                size=(None, int(fontsize * 2.0))
            )
            temp_clips.append(txt_clip)
            total_w += txt_clip.w
            max_h = max(max_h, txt_clip.h)
            
        space_w = fontsize * 0.3
        total_w += space_w * (len(temp_clips) - 1)
        
        max_screen_w = w * 0.9
        scale_factor = 1.0
        if total_w > max_screen_w:
            scale_factor = max_screen_w / total_w
            
        start_x = (w - (total_w * scale_factor)) / 2
        current_x = start_x
        
        vertical_pos_pct = config.get('vertical_position', 75)
        y_pos = int((h * (vertical_pos_pct / 100.0)) - ((max_h * scale_factor) / 2))

        final_composite_clips = []
        
        for i, clip in enumerate(temp_clips):
            if scale_factor != 1.0:
                clip = clip.resized(scale_factor)
                
            # Capture width for layout BEFORE applying dynamic animation
            # Dynamic animation (resize) changes .w to the size at t=0 (which is small/zero)
            layout_w = clip.w
                
            clip = clip.with_position((current_x, y_pos))
            clip = clip.with_start(chunk_start).with_duration(duration)
            
            if duration > 0.2:
                # Custom Pop-In-Out Animation (Frontend match)
                center_x = current_x + (layout_w / 2)
                center_y = y_pos + (clip.h / 2)
                orig_w = layout_w * 1.0 # Ensure float copy
                orig_h = clip.h * 1.0
                
                # Define animation function with closure over duration
                def make_pop_anim(dur):
                    def anim(t):
                        scale = 1.0
                        # Pop In (0 -> 1.2 -> 1.0)
                        # Smoother Sine Ease
                        if t < 0.1:
                            # 0 to 1.2
                            progress = t / 0.1
                            scale = 1.2 * math.sin(progress * math.pi / 2)
                        elif t < 0.2:
                            # 1.2 to 1.0
                            progress = (t - 0.1) / 0.1
                            scale = 1.2 - (0.2 * progress)
                        # Pop Out (1.0 -> 0.0) at end
                        elif t > (dur - 0.1):
                            remain = dur - t
                            scale = remain / 0.1
                        else:
                            scale = 1.0
                            
                        return max(0.1, scale)
                    return anim

                pop_anim_func = make_pop_anim(duration)

                # Apply resize animation
                clip = clip.resized(pop_anim_func)
                
                # Apply position correction to keep centered
                # Capture variables by value (cx=center_x, etc) to Fix Loop bug
                clip = clip.with_position(lambda t, cx=center_x, cy=center_y, ow=orig_w, oh=orig_h, af=pop_anim_func: 
                                          (cx - (ow * af(t))/2, cy - (oh * af(t))/2))
                
                # Apply Opacity Animation
                try:
                    from moviepy.video.fx import CrossFadeIn, CrossFadeOut
                    clip = clip.with_effects([CrossFadeIn(duration=0.1), CrossFadeOut(duration=0.1)])
                except ImportError:
                    pass
                
            final_composite_clips.append(clip)
            current_x += layout_w + (space_w * scale_factor)
            
        subtitle_clips.extend(final_composite_clips)
        
    return subtitle_clips
