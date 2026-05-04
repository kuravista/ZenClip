"""
Boxies Subtitle Style
Creates subtitles with a maximum of 2 lines, where the second line has a background box.
Simple static text without highlight animation.
"""

from moviepy import CompositeVideoClip, TextClip, ColorClip
from services.media.subtitle.utils.fonts import get_font_path
from services.media.subtitle.utils.text import measure_real_height

# Configuration for Boxies style
BOXIES_CONFIG = {
    'chunk_size': 5,              # Words per subtitle chunk
    'max_lines': 2,               # Fixed at 2 lines
    'max_width_ratio': 0.80,      # Maximum width as percentage of video width
    'word_spacing_px': 8,         # Horizontal spacing between words
    'line_gap_px': 5,             # Vertical gap between lines (reduced for tighter spacing)
    'box_padding_h': 20,          # Horizontal padding for line 2 box
    'box_padding_v': 6,           # Vertical padding for line 2 box (reduced for tighter spacing)
    'min_word_duration_ms': 50    # Minimum duration for a word
}


def create_boxies_subtitles(config, video_clip, phrase_timings, clip_start, clip_end):
    """
    Create boxies-style subtitles with 2-line limit and background box on second line.
    No highlight animation - simple static text.
    
    Args:
        config: Configuration dictionary with style settings
        video_clip: The video clip to add subtitles to
        phrase_timings: List of phrase timing dictionaries with words
        clip_start: Start time of the clip
        clip_end: End time of the clip
    
    Returns:
        List of subtitle CompositeVideoClip objects
    """
    print(f"[INFO] Generating Boxies subtitles for clip {clip_start:.1f}s - {clip_end:.1f}s")
    
    video_w, video_h = video_clip.size
    audio_offset = config.get("audio_offset", 0.0)
    
    # Collect all words within clip boundaries
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
    
    # Chunk words
    CHUNK_SIZE = BOXIES_CONFIG['chunk_size']
    chunks = [all_words[i:i + CHUNK_SIZE] for i in range(0, len(all_words), CHUNK_SIZE)]
    
    subtitle_clips = []
    
    for chunk_idx, chunk in enumerate(chunks):
        if not chunk:
            continue
        
        chunk_start_abs = chunk[0]['start']
        chunk_end_abs = chunk[-1]['end']
        
        rel_chunk_start = chunk_start_abs - clip_start + audio_offset
        rel_chunk_end = chunk_end_abs - clip_start + audio_offset
        rel_chunk_start = max(0, rel_chunk_start)
        
        chunk_duration = rel_chunk_end - rel_chunk_start
        if chunk_duration < 0.1:
            continue
        
        # Split chunk into 2 lines (distribute evenly)
        num_words = len(chunk)
        line1_count = (num_words + 1) // 2  # First line gets more if odd number
        line2_count = num_words - line1_count
        
        line1_words = chunk[:line1_count]
        line2_words = chunk[line1_count:]
        
        # Get font and config
        font_path = get_font_path(config["font"])
        fontsize = config["fontsize"]
        color = config.get("color", "white")
        stroke_color = config.get("stroke_color", "black")
        stroke_width = config.get("stroke_width", 3)
        
        # Render line 1 text (if any)
        if line1_count > 0:
            line1_text = ' '.join([w['text'] for w in line1_words]).upper()
            
            # Add padding spaces and newlines to prevent stroke from cropping text at edges
            padded_text = f"  {line1_text}  \n "
            
            line1_clip = TextClip(
                text=padded_text,
                font=font_path,
                font_size=fontsize,
                color=color,
                stroke_color=stroke_color,
                stroke_width=stroke_width,
                method="label"
            )
            
            # Reduce height by cropping transparent bottom (the newline buffer)
            try:
                # measure_real_height finds the lowest non-transparent pixel
                # We add a small buffer (e.g. 5px) to be safe, but main goal is removing the huge \n space
                real_h = measure_real_height(line1_clip, buffer=5)
                if real_h > 0 and real_h < line1_clip.h:
                    # Crop the clip to its real visual height plus a tiny margin
                    line1_clip = line1_clip.cropped(y2=real_h)
            except Exception as e:
                print(f"[WARN] Failed to measure/crop line 1 height: {e}")
            
            line1_w = line1_clip.w
            line1_h = line1_clip.h
        else:
            line1_clip = None
            line1_w = 0
            line1_h = 0
        
        # Render line 2 text (if any)
        if line2_count > 0:
            line2_text = ' '.join([w['text'] for w in line2_words]).upper()
            
            # Add padding spaces and newlines to prevent stroke from cropping text at edges
            padded_text = f"  {line2_text}  \n "
            
            line2_clip = TextClip(
                text=padded_text,
                font=font_path,
                font_size=fontsize,
                color=color,
                stroke_color=stroke_color,
                stroke_width=stroke_width,
                method="label"
            )
            
            # Reduce height by cropping transparent bottom
            try:
                real_h = measure_real_height(line2_clip, buffer=5)
                if real_h > 0 and real_h < line2_clip.h:
                    line2_clip = line2_clip.cropped(y2=real_h)
            except Exception as e:
                print(f"[WARN] Failed to measure/crop line 2 height: {e}")
            
            line2_w = line2_clip.w
            line2_h = line2_clip.h
            
            # Create background box for line 2 - fit exactly to text size
            box_padding_h = BOXIES_CONFIG['box_padding_h']
            box_padding_v = BOXIES_CONFIG['box_padding_v']
            
            box_w = line2_w + (box_padding_h * 2)
            box_h = line2_h + (box_padding_v * 2)
            
            # Create background box
            bg_color_hex = config.get("bg_color", "#2563eb")
            bg_opacity = config.get("bg_opacity", 0.75)
            
            # Convert hex to RGB
            bg_color_hex = bg_color_hex.lstrip('#')
            bg_color_rgb = tuple(int(bg_color_hex[i:i+2], 16) for i in (0, 2, 4))
            
            bg_box = ColorClip(
                size=(int(box_w), int(box_h)),
                color=bg_color_rgb
            ).with_opacity(bg_opacity).with_fps(30)
        else:
            line2_clip = None
            line2_w = 0
            line2_h = 0
            bg_box = None
            box_w = 0
            box_h = 0
        
        # Calculate total layout dimensions
        # Use box width if line 2 exists, otherwise use line 1 width
        if line2_count > 0:
            layout_width = max(line1_w, box_w)  # Use max of box and line 1 width
        else:
            layout_width = line1_w
        
        line_gap = BOXIES_CONFIG['line_gap_px']
        layout_height = line1_h + (line_gap + box_h if line2_count > 0 else 0)
        
        # Build composite elements
        elements = []
        
        # Animation timings - longer for smoother effect
        popup_delay = 0.2  # Delay for line 2 popup after line 1 (seconds)
        popup_duration = 0.3  # Duration of popup animation (seconds) - longer for smoothness
        
        # Add line 1 (centered) with smooth fade-in animation
        if line1_clip is not None:
            line1_x = (layout_width - line1_w) // 2
            line1_positioned = line1_clip.with_position((int(line1_x), 0))
            line1_positioned = line1_positioned.with_start(0).with_duration(chunk_duration)
            
            # Apply smooth fade-in using CrossFadeIn
            try:
                from moviepy.video.fx import CrossFadeIn
                line1_with_fade = line1_positioned.with_effects([CrossFadeIn(popup_duration)])
                elements.append(line1_with_fade)
            except Exception as e:
                print(f"  ⚠️ Animation failed for line1: {e}")
                elements.append(line1_positioned)
        
        # Add line 2 with background box (centered) with delayed smooth fade-in
        if line2_clip is not None and bg_box is not None:
            line2_y = line1_h + line_gap
            
            # Center the background box within layout
            box_x = (layout_width - box_w) // 2
            
            # Create a delayed version of the background box
            print(f"[DEBUG] Creating background box:")
            print(f"  - Color RGB: {bg_color_rgb}")
            print(f"  - Opacity: {bg_opacity}")
            print(f"  - Size: {int(box_w)}x{int(box_h)} px")
            print(f"  - Position: ({int(box_x)}, {int(line2_y)})")
            print(f"  - Start time: {popup_delay}s")
            print(f"  - Duration: {chunk_duration - popup_delay}s")
            
            bg_positioned = bg_box.with_position((int(box_x), int(line2_y)))
            bg_positioned = bg_positioned.with_start(popup_delay).with_duration(chunk_duration - popup_delay)
            
            # Apply smooth fade-in
            try:
                from moviepy.video.fx import CrossFadeIn
                bg_with_fade = bg_positioned.with_effects([CrossFadeIn(popup_duration)])
                elements.append(bg_with_fade)
                print(f"[DEBUG] ✓ Background box added to elements (with fade)")
            except Exception as e:
                print(f"  ⚠️ Animation failed for box: {e}")
                elements.append(bg_positioned)
                print(f"[DEBUG] ✓ Background box added to elements (no fade)")

            
            # Center the text within the box
            text_x = (layout_width - line2_w) // 2
            text_y = line2_y + box_padding_v
            
            # Create delayed line 2 text
            line2_positioned = line2_clip.with_position((int(text_x), int(text_y)))
            line2_positioned = line2_positioned.with_start(popup_delay).with_duration(chunk_duration - popup_delay)
            
            # Apply smooth fade-in
            try:
                from moviepy.video.fx import CrossFadeIn
                line2_with_fade = line2_positioned.with_effects([CrossFadeIn(popup_duration)])
                elements.append(line2_with_fade)
            except Exception as e:
                print(f"  ⚠️ Animation failed for line2: {e}")
                elements.append(line2_positioned)
        
        # Create composite
        chunk_composite = CompositeVideoClip(
            elements,
            size=(int(layout_width), int(layout_height))
        ).with_fps(30)
        
        # Position on video
        vertical_pos_percent = config.get("vertical_position", 75)
        y_pos = int(video_h * (vertical_pos_percent / 100.0)) - (layout_height // 2)
        y_pos = max(50, min(y_pos, video_h - layout_height - 50))
        
        chunk_composite = chunk_composite.with_position(("center", int(y_pos)))
        chunk_composite = chunk_composite.with_start(rel_chunk_start).with_duration(chunk_duration)
        
        subtitle_clips.append(chunk_composite)
    
    print(f"[INFO] Created {len(subtitle_clips)} boxies subtitle chunks")
    return subtitle_clips
