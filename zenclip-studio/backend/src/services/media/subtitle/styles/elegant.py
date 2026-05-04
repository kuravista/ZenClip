
from services.media.subtitle.utils.fonts import get_font_path
from moviepy import TextClip, CompositeVideoClip
import re

def create_elegant_subtitles(config, video_clip, phrase_timings, clip_start, clip_end):
    """
    Creates "Elegant" subtitles (max 3 words at a time).
    Style:
    - Italic Bold (via font selection if possible, currently reliant on config font)
    - Important words: Lime Green (#32CD32)
    - Normal words: White
    - No Glow
    
    Chunking:
    - Max 3 words per chunk
    """
    subtitle_clips = []
    w, h = video_clip.size
    
    # Config
    font = config.get('font', 'PlayfairDisplay-Italic')
    fontsize = int(config.get('fontsize', 70))
    # Base colors
    base_color = 'white'
    highlight_color = config.get('highlight_color', '#ADF91D') 
    stroke_color = config.get('stroke_color', 'black')
    # 3D Effect Config
    # Shadow removed per user request
    stroke_width = 0 # No outline, just shadow
    
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
            
            # Split text if it contains multiple words (fixes "blocky" rapid-pro look)
            # This handles cases where Whisper segments are phrases instead of words
            text_parts = word_info['text'].strip().split()
            if len(text_parts) > 1:
                total_duration = w_end - w_start
                duration_per_word = total_duration / len(text_parts)
                
                for idx, part in enumerate(text_parts):
                    p_start = w_start + (idx * duration_per_word)
                    p_end = p_start + duration_per_word
                    all_words.append({
                        'text': part,
                        'start': p_start,
                        'end': p_end
                    })
            else:
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
        
    # 3. Create Clips (Refactored for 3D)

        # REFACTOR: Let's create pairs of (Shadow, Main) in the loop above?
        # That logic is easier.
        
    # 3. Create Clips (Refactored for 3D)
    font_path = get_font_path(font)
    
    for chunk in chunks:
        if not chunk: continue
        
        chunk_start = chunk[0]['start']
        chunk_end = chunk[-1]['end']
        duration = chunk_end - chunk_start
        if duration < 0.1: duration = 0.1
        
        chunk_size = len(chunk)
        
        temp_main_clips = []
        
        total_w = 0
        max_h = 0
        
        # Pass 1: generate text clips
        for i, w_obj in enumerate(chunk):
            w_text = w_obj['text']
            
            # Color Logic
            w_color = base_color
            is_highlight = False
            if chunk_size == 2: 
                w_color = highlight_color
                is_highlight = True
            elif chunk_size >= 3 and i > 0: 
                w_color = highlight_color
                is_highlight = True
            
            # Font Logic (Dual Font)
            # Normal: Poppins Black (Requested default)
            # Highlight: Playfair Display Italic
            if is_highlight:
                current_font_path = get_font_path('PlayfairDisplay-Italic')
            else:
                # User requested Poppins-Regular for non-highlight
                # We try to find it, otherwise fall back to config default
                current_font_path = get_font_path('Poppins-Regular')
                if not current_font_path or current_font_path == "Arial": # basic fallback check
                     current_font_path = font_path

            # Fallback if None
            if not current_font_path:
                 current_font_path = font_path 

            # Main Clip - Uses PIL for precise rendering to avoid clipping
            
            try:
                from PIL import Image, ImageFont, ImageDraw
                import numpy as np

                # 1. Load Font
                pil_font = ImageFont.truetype(current_font_path, fontsize)
                
                # 2. Measure Text
                dummy_img = Image.new('RGBA', (1, 1), (0,0,0,0))
                draw = ImageDraw.Draw(dummy_img)
                # Ensure we capture everything including descenders
                bbox = draw.textbbox((0, 0), w_text, font=pil_font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
                
                # 3. Create Canvas with Padding
                # Vertical buffer for huge loops/descenders (y, g, j, f)
                pad_y = 40 
                # Minimal horizontal padding to keep spacing tight
                pad_x = 5
                
                # Canvas size
                canvas_w = text_w + (pad_x * 2)
                canvas_h = text_h + (pad_y * 2)
                
                # 4. Draw
                img = Image.new('RGBA', (int(canvas_w), int(canvas_h)), (0,0,0,0))
                draw = ImageDraw.Draw(img)
                
                # Position: offset by bbox[0]/[1] so text ink starts at (0,0) relative to bbox, then add padding
                draw_x = pad_x - bbox[0]
                draw_y = pad_y - bbox[1]
                
                draw.text((draw_x, draw_y), w_text, font=pil_font, fill=w_color)
                
                # 5. Convert to Clip
                img_np = np.array(img)
                from moviepy import ImageClip
                main_clip = ImageClip(img_np).with_duration(duration)
                
            except Exception as e:
                # Fallback to TextClip if PIL fails (e.g. missing dependencies)
                print(f"PIL Text Render Failed: {e}, falling back to TextClip")
                text_content = f"\n{w_text}\n"
                main_clip = TextClip(
                    text=text_content,
                    font=current_font_path,
                    font_size=fontsize,
                    color=w_color,
                    stroke_width=0,
                    method='label'
                )

            
            temp_main_clips.append(main_clip)
            
            total_w += main_clip.w
            max_h = max(max_h, main_clip.h)
            
        # Spacing
        space_w = fontsize * 0.25
        total_w += space_w * (len(temp_main_clips) - 1)
        
        # Scaling
        max_screen_w = w * 0.85 
        scale_factor = 1.0
        if total_w > max_screen_w:
            scale_factor = max_screen_w / total_w
            
        # Positioning
        start_x = (w - (total_w * scale_factor)) / 2
        
        # Move up slightly to avoid bottom clipping
        # Default was 75, change to 70 or config
        vertical_pos_pct = config.get('vertical_position', 70) 
        
        # Center Y
        y_pos_center = int(h * (vertical_pos_pct / 100.0))
        # Top Y for clip
        y_pos = y_pos_center - ((max_h * scale_factor) / 2)
        
        # Safety check: Ensure not too close to bottom
        bottom_edge = y_pos + (max_h * scale_factor)
        margin_bottom = h * 0.1
        if bottom_edge > (h - margin_bottom):
             y_pos = h - margin_bottom - (max_h * scale_factor)
        
        # Build composite for this chunk
        current_x = start_x
        
        for i in range(len(temp_main_clips)):
            main = temp_main_clips[i]
            
            if scale_factor != 1.0:
                main = main.resized(scale_factor)
                
            # Positions
            # Main
            m_x = current_x
            m_y = y_pos
            main = main.with_position((m_x, m_y))
            main = main.with_start(chunk_start).with_duration(duration)
            
            # Animation
            effects = []
            if duration > 0.2:
                try:
                    from moviepy.video.fx import CrossFadeIn, CrossFadeOut
                    effects = [CrossFadeIn(duration=0.1), CrossFadeOut(duration=0.1)]
                except: pass
            
            if effects:
                main = main.with_effects(effects)
                
            # Add to final list
            subtitle_clips.append(main)
            
            current_x += main.w + (space_w * scale_factor)

    return subtitle_clips
