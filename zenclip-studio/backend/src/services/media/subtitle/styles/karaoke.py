from moviepy import TextClip, CompositeVideoClip
import numpy as np
from services.media.subtitle.utils.text import measure_real_height
from services.media.subtitle.utils.fonts import get_font_path
from services.media.subtitle.utils.image import create_rounded_rect_clip, create_emoji_clip
from services.media.subtitle.utils.color import hex_to_rgb
import re

def _generate_text_clip(text, config):
    color = config["color"]
    stroke_color = config["stroke_color"]
    stroke_width = config["stroke_width"]
    font = config["font"]
    fontsize = config["fontsize"]
    
    stroke_width = int(config.get('stroke_width', 3))
    bg_color = config.get('bg_color', 'yellow')
    
    font_path = get_font_path(font) or get_font_path("Montserrat-Bold")
    
    text_padded = text.upper() + "\n "
    
    txt = TextClip(
        text=text_padded, # Assuming word_text_style was a placeholder for text_padded
        font=font_path,  # Use resolved font path
        font_size=fontsize,
        color=color,
        stroke_color=stroke_color,
        stroke_width=stroke_width,
        method="label"
    )
    
    real_h = measure_real_height(txt, buffer=15)
    txt = txt.cropped(y2=real_h)
    
    return txt

def create_karaoke_subtitles(config, video_clip, phrase_timings, clip_start, clip_end):
    print(f"[INFO] Generating Karaoke subtitles for clip {clip_start:.1f}s - {clip_end:.1f}s")
    
    video_w, video_h = video_clip.size
    audio_offset = config.get("audio_offset", 0.0)
    
    active_phrases = []
    for p in phrase_timings:
        if p['end'] > clip_start and p['start'] < clip_end:
            active_phrases.append(p)
    
    active_phrases.sort(key=lambda x: x['start'])
    subtitle_clips = []
    
    highlight_map = config.get("highlight_map", {})
    emoji_map = config.get("emoji_map", {})
    smart_enabled = config.get("smart_subtitles", False)
    if highlight_map or emoji_map:
         smart_enabled = True
    
    for phrase_idx, phrase in enumerate(active_phrases):
        words = phrase.get('words', [])
        
        if not words:
            words = [{
                'text': phrase['text'],
                'start': phrase['start'],
                'end': phrase['end']
            }]
        
        # 1. PREPARE LAYOUT WITH MAX 2 LINES CONSTRAINT
        initial_fontsize = config["fontsize"]
        current_fontsize = initial_fontsize
        word_dims = []
        lines = []
        
        # Retry loop for layout
        attempts = 0
        max_attempts = 5
        
        while attempts < max_attempts:
            # Clean up previous text clips if any
            # (Note: word_dims stores 'txt' which needs closing? The previous code closed 'txt' immediately, 
            # but we need it for width. Let's separate dimension calc from clip gen to be safe, 
            # or just re-gen since 'attempts' will be low)
            
            # Temporary config for this attempt
            attempt_config = config.copy()
            attempt_config["fontsize"] = current_fontsize
            
            temp_dims = []
            stroke_buffer = attempt_config["stroke_width"] * 4
            
            # Measure all words
            for w in words:
                # We need to generate to measure accurately with exact font
                # This is slightly expensive but safest for accuracy
                txt = _generate_text_clip(w['text'], attempt_config)
                temp_dims.append({
                    'w': txt.w + stroke_buffer,
                    'h': txt.h + stroke_buffer,
                    'text': w['text'],
                    'data': w,
                    'raw_w': txt.w, # Store raw text width for checking
                    'raw_h': txt.h
                })
                txt.close()
            
            # Run Layout Logic
            temp_lines = []
            current_line = []
            current_w = 0
            max_w = video_w * config["max_width_percent"]
            space_w = current_fontsize * 0.3
            
            for wd in temp_dims:
                word_with_space = wd['w']
                if current_line:
                    word_with_space += space_w
                
                if current_line and (current_w + word_with_space) > max_w:
                    temp_lines.append(current_line)
                    current_line = [wd]
                    current_w = wd['w']
                else:
                    current_line.append(wd)
                    current_w += word_with_space
            
            if current_line:
                temp_lines.append(current_line)
                
            # Check constraint
            if len(temp_lines) <= 2:
                # Accepted
                lines = temp_lines
                word_dims = temp_dims
                break
            else:
                # Reduce font size and retry
                current_fontsize = int(current_fontsize * 0.85)
                attempts += 1
                if attempts == max_attempts:
                    print("[WARN] Could not fit karaoke text in 2 lines even after resizing. Using last result.")
                    lines = temp_lines
                    word_dims = temp_dims
        
        # Final config used
        final_config = config.copy()
        final_config["fontsize"] = current_fontsize
        
        # Calculate positions
        space_w = current_fontsize * 0.3 # Re-calc space for final
        total_h = sum(max(w['h'] for w in line) for line in lines) + (len(lines) - 1) * 10
        
        vertical_pos_pct = config.get('vertical_position', 75)
        center_y = int(video_h * (vertical_pos_pct / 100.0))
        
        if lines:
            first_line_h = max(w['h'] for w in lines[0])
            start_y = center_y - (first_line_h // 2)
        else:
            start_y = center_y - (total_h // 2)
        
        if start_y < 0: start_y = 10
        if (start_y + total_h) > video_h: start_y = video_h - total_h - 10
        
        current_y = start_y
        
        # Assign coordinates and Line ID to words
        all_positioned_words = []
        for line_idx, line in enumerate(lines):
            line_w = sum(w['w'] for w in line) + (len(line) - 1) * space_w
            start_x = (video_w - line_w) / 2
            current_x = start_x
            
            for wd in line:
                wd['x'] = int(current_x)
                wd['y'] = int(current_y)
                wd['line_idx'] = line_idx # Track line for animation
                all_positioned_words.append(wd)
                current_x += wd['w'] + space_w
            
            current_y += max(w['h'] for w in line) + 10
            
        # 2. CREATE PHRASE COMPOSITE
        p_start = max(0, phrase['start'] - clip_start + audio_offset)
        p_end = min(clip_end - clip_start, phrase['end'] - clip_start + audio_offset)
        
        if phrase_idx < len(active_phrases) - 1:
            next_phrase = active_phrases[phrase_idx + 1]
            next_start = max(0, next_phrase['start'] - clip_start + audio_offset)
            p_end = min(p_end, next_start - 0.2)
        
        phrase_duration = p_end - p_start
        if phrase_duration < 0.1: continue

        elements = []
        
        # A. DYNAMIC HIGHLIGHT WITH SLIDING ANIMATION
        # We create a VideoClip that renders the rounded rect dynamically frame-by-frame
        from moviepy.video.VideoClip import VideoClip
        from PIL import Image, ImageDraw
        
        def make_highlight_frame(t):
            # Create a transparent frame
            # Optimization: could make a smaller clip and move it, but resizing rounded rects distorts corners.
            # For 1080p, creating a full image per frame is heavy but cleanest for custom drawing.
            # To optimize, we can create the frame only for the bounding box needed, but let's stick to full frame for simplicity of positioning first.
            img = Image.new('RGBA', (video_w, video_h), (0,0,0,0))
            draw = ImageDraw.Draw(img)
            
            # Determine geometry
            current_time_abs = p_start + t # Relative to clip start, but our word timings are absolute relative to original clip?
            # Wait, p_start is relative to clip_start. 't' is relative to p_start.
            # So abs_time_in_clip = p_start + t.
            # words[i]['start'] is absolute time in original audio? Yes.
            # Adjust to clip relative:
            
            abs_t_in_clip_time = p_start + t + clip_start - audio_offset
            # No, simplistic:
            # We want to map `t` (0 to phrase_duration) to the word timings.
            # Our word dims rely on `all_positioned_words` which matches `words` list order.
            
            # Find active word
            # Just use the adjusted `t` to find which word we are overlapping or transition between
            
            # `words` has absolute absolute times (e.g. 15.2s). `clip_start` e.g. 10.0s. `audio_offset`.
            # Effective time `et` = clip_start + t
            
            # Actually, let's work in "Time relative to phrase start"
            # t_rel = t
            # word_start_rel = w['start'] - start_time_of_phrase? No, w['start'] - clip_start + audio_offset - p_start
            
            # Let's pre-calculate rel timings for words
            active_geom = None
            
            # Find current word index
            # Logic:
            # If t is in word[i], we are at word[i].
            # If t is between word[i] and word[i+1], interpolate?
            
            current_idx = -1
            # Simple linear search (few words)
            eff_t = t + p_start # relative to clip start
            
            # Adjust words to be comparable
            # word_start_rel_to_clip = w['start'] - clip_start + audio_offset
            
            # Find which "slot" we are in
            
            tgt_idx = -1
            progress = 0.0
            
            # Pre-calc normalized times for this phrase
            word_times = []
            for i, w in enumerate(words):
                s = w['start'] - clip_start + audio_offset - p_start
                e = w['end'] - clip_start + audio_offset - p_start
                word_times.append((s, e))
            
            # Check range
            for i, (s, e) in enumerate(word_times):
                if s <= t <= e:
                    tgt_idx = i
                    progress = 0.0 # Settled
                    break
                
                # Check transition to next
                if i < len(word_times) - 1:
                    next_s = word_times[i+1][0]
                    if e < t < next_s:
                        # In the gap. Interpolate?
                        # Or just hold previous? 
                        # Sliding EFFECT: Slide from i to i+1 during the gap?
                        # If gap is large, sliding might look weird ("floating").
                        # If gap is small (fast speech), sliding is good.
                        # Let's slide during the last 20% of word i and first 20% of word i+1?
                        # Or just pure slide during gap.
                        tgt_idx = i                 # Origin
                        next_dest_idx = i + 1       # Destination
                        
                        gap_dur = next_s - e
                        if gap_dur > 0:
                            # norm_p = (t - e) / gap_dur as slide_factor? 
                            # Usually smooth step (sigmoid) looks better
                            progress = (t - e) / gap_dur
                        else:
                            progress = 1.0
                        break
            
            # Edge case: before first word or after last
            if tgt_idx == -1:
                if t < word_times[0][0]:
                    tgt_idx = 0
                    progress = 0.0
                elif t > word_times[-1][1]:
                    tgt_idx = len(words) - 1
                    progress = 0.0
            
            
            # Calculate Geometry
            if tgt_idx != -1:
                cur_wd = all_positioned_words[tgt_idx]
                
                # Default geom
                padding = 10
                g_x = cur_wd['x'] - padding
                g_y = cur_wd['y'] - padding/2
                g_w = cur_wd['w'] + padding*2
                g_h = cur_wd['h'] + padding
                
                # Handle Interpolation
                # Only interpolate if next exists AND on SAME LINE
                if progress > 0.0 and (tgt_idx + 1) < len(all_positioned_words):
                    next_wd = all_positioned_words[tgt_idx+1]
                    
                    if cur_wd.get('line_idx') == next_wd.get('line_idx'):
                        # Interpolate
                        n_x = next_wd['x'] - padding
                        n_y = next_wd['y'] - padding/2
                        n_w = next_wd['w'] + padding*2
                        n_h = next_wd['h'] + padding
                        
                        # Ease in-out
                        from math import cos, pi
                        # p goes 0->1. Smooth: (1 - cos(p*pi)) / 2
                        ease = (1 - cos(progress * pi)) / 2
                        
                        g_x = g_x + (n_x - g_x) * ease
                        g_y = g_y + (n_y - g_y) * ease
                        g_w = g_w + (n_w - g_w) * ease
                        g_h = g_h + (n_h - g_h) * ease
            
                # Draw
                color = (37, 99, 235) # Default blue
                bg_color_raw = config.get("bg_color", "#2563eb")
                # Specific highlight map override check
                clean_text = re.sub(r'[^\w\s]', '', cur_wd['text']).lower().strip()
                if smart_enabled and highlight_map and clean_text in highlight_map:
                     bg_color_raw = highlight_map[clean_text] # Use specific color if mapped

                if isinstance(bg_color_raw, str):
                    color = hex_to_rgb(bg_color_raw)
                elif isinstance(bg_color_raw, tuple):
                    color = bg_color_raw
                    
                # Alpha support? ImageDraw does supporting Fill with alpha
                # Assuming color is RGB, let's add alpha if needed or strict RGB
                
                # Draw Rounded Rect
                # PIL does not have built-in rounded rect with radius in older versions, but draw.rounded_rectangle exists in newer PIL
                # Clipiee seems to use PIL.
                try:
                    draw.rounded_rectangle([g_x, g_y, g_x+g_w, g_y+g_h], radius=15, fill=color)
                except AttributeError:
                    draw.rectangle([g_x, g_y, g_x+g_w, g_y+g_h], fill=color)
            
            return np.array(img)

        # Create the highlight clip
        highlight_clip = VideoClip(make_frame=make_highlight_frame, duration=phrase_duration)
        elements.append(highlight_clip)
        
        # B. TEXT OVERLAY
        for w_data in all_positioned_words:
            txt = _generate_text_clip(w_data['text'], final_config)
            txt = txt.with_position((int(w_data['x']), int(w_data['y'])))
            txt = txt.with_start(0).with_duration(phrase_duration)
            elements.append(txt)
            
        phrase_clip = CompositeVideoClip(elements, size=video_clip.size)
        phrase_clip = phrase_clip.with_start(p_start).with_duration(phrase_duration).with_fps(30)

        # Apply Smooth Animation (Fade In)
        try:
            from moviepy.video.fx import CrossFadeIn
            phrase_clip = phrase_clip.with_effects([CrossFadeIn(duration=0.1)])
        except ImportError:
            # Fallback
            class SimpleFadeIn:
                def __init__(self, duration):
                    self.duration = duration
                def copy(self):
                    return SimpleFadeIn(self.duration)
                def apply(self, clip):
                    return clip.with_opacity(lambda t: min(1.0, max(0.0, t / self.duration)))
            
            phrase_clip = phrase_clip.with_effects([SimpleFadeIn(0.1)])
        
        subtitle_clips.append(phrase_clip)
            
    return subtitle_clips
