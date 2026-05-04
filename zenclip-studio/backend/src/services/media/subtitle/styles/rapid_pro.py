from services.media.subtitle.utils.fonts import get_font_path

from moviepy import TextClip
import re

def create_rapid_pro_subtitles(config, video_clip, phrase_timings, clip_start, clip_end):
    """
    Creates "Rapid Pro" subtitles (max 3 words at a time).
    Coloring:
    - 1 word: White
    - 2 words: Yellow, Yellow
    - 3 words: White, Yellow, Yellow
    """
    subtitle_clips = []
    w, h = video_clip.size
    
    # Config
    font = config.get('font', 'Arial')
    fontsize = int(config.get('fontsize', 70))
    # Base colors (though we override specific words)
    base_color = config.get('color', 'white') # Default white
    highlight_color = config.get('highlight_color', 'yellow') # Use highlight color for the "yellow" parts
    stroke_color = config.get('stroke_color', 'black')
    stroke_width = int(config.get('stroke_width', 2))
    
    # 1. Collect all words
    all_words = []
    for phrase in phrase_timings:
        if phrase['end'] < (clip_start - 1.5) or phrase['start'] > (clip_end + 1.5):
            continue
        
        words = phrase.get('words', [])
        # If no word-level timings, fallback to splitting phrase linearly? 
        # For now assume word-level exists as per other styles.
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

    # 2. Group into chunks (Max 3 words, smart grouping?)
    # Simple strategy: Greedy chunks of 3, unless pause or sentence break?
    # Prompt says "shows max 3 words". It acts like "Mozi" but with specific coloring.
    # Let's use similar logic to Mozi but strict cap at 3.
    
    chunks = []
    current_chunk = []
    
    for word in all_words:
        current_chunk.append(word)
        
        # Check if we should break chunk
        # Break if 3 words reached
        if len(current_chunk) >= 3:
            chunks.append(current_chunk)
            current_chunk = []
            
    if current_chunk:
        chunks.append(current_chunk)
        
    # 3. Create Clips
    for chunk in chunks:
        if not chunk: continue
        
        # Determine duration: Start of first word to End of last word
        chunk_start = chunk[0]['start']
        chunk_end = chunk[-1]['end']
        duration = chunk_end - chunk_start
        
        if duration < 0.1: duration = 0.1
        
        # Determine Colors based on chunk size
        # 1 word: White
        # 2 words: Yellow, Yellow
        # 3 words: White, Yellow, Yellow
        
        chunk_size = len(chunk)
        
        # We need to build a single TextClip with colored substrings? 
        # MoviePy's TextClip doesn't support rich text easily without ImageMagick's Pango or similar.
        # However, our ASS generator handles rich text.
        # For MoviePy preview/generation (legacy/fallback), we might struggle with multi-color in one text clip easily.
        # Strategy: Use CompositeVideoClip of individual word TextClips positioned together? 
        # OR just use "Caption" method with standard color for preview, and specific color for final?
        # User specified "analyze rapid_fire.py". Rapid Fire is 1 word at a time.
        # "Rapid Pro ... is like a rapid style but it shows max 3 words"
        # If it shows 3 words, are they sequential (one by one accumulating) or all at once?
        # "shows max 3 words" usually implies a block.
        # "if it just 2 words both are yellow"
        # I will assume it shows the BLOCK of words all at once for the duration of the 3 words.
        
        # For MovePy implementation (Preview/Non-ASS):
        # Implementing multi-color text in one line is hard in MoviePy standard TextClip.
        # We can construct the text string, but coloring is per-clip.
        # We can try to composite 3 clips horizontally?
        # Or just fallback to a 'primary' color for preview?
        # Let's try to composite them to be accurate.
        
        # Calculate combined text for width measurement?
        full_text_str = " ".join([w['text'] for w in chunk])
        
        # We can create individual clips for each word and composite them? 
        # Positioning relative to each other is tricky without font metrics.
        # But we can try just centering the whole block.
        
        # Simpler approach for MoviePy:
        # Just use the "2 word = Yellow / 3 word = Mixed" logic but apply to the dominant color or just single color?
        # The user specifically asked for coloring.
        # Let's try to make separate TextClips for each word and concatenate them horizontally?
        # That's complicated for spacing.
        
        # Alternative: Standard TextClip allows `color` argument.
        # Maybe we just create ONE text clip with the "Dominant" color for preview?
        # 1 word: White
        # 2 words: Yellow
        # 3 words: White (Start) + Yellow (End). 
        # If we must show it, let's use the 2-word yellow logic.
        # For 3 words, maybe just make them all Yellow for preview? Or White?
        # User might be disappointed if preview is wrong.
        
        # Let's try to do it right with composite.
        # We need to measure text width.
        
        # Font handling
        font_path = get_font_path(font)
        
        word_clips = []
        total_w = 0
        max_h = 0
        
        # First pass: Create clips to measure
        # We need to determine color per word index
        
        temp_clips = []
        for i, w_obj in enumerate(chunk):
            w_text = w_obj['text']
            
            # Determine Color
            # Default White
            w_color = 'white'
            
            if chunk_size == 1:
                w_color = 'white'
            elif chunk_size == 2:
                w_color = highlight_color # Yellow
            elif chunk_size == 3:
                if i == 0:
                    w_color = 'white'
                else:
                    w_color = highlight_color # Yellow (2nd and 3rd)
            
            txt_clip = TextClip(
                text=w_text,
                font=font_path,
                font_size=fontsize,
                color=w_color,
                stroke_color=stroke_color,
                stroke_width=stroke_width,
                method='label',
                # Fix: Specify height to prevent clipping of descenders/strokes
                size=(None, int(fontsize * 1.4))
            )
            temp_clips.append(txt_clip)
            total_w += txt_clip.w
            max_h = max(max_h, txt_clip.h)
            
        # Add spacing width
        space_w = fontsize * 0.3 # Approx space width
        total_w += space_w * (len(temp_clips) - 1)
        
        # Limit total width
        max_screen_w = w * 0.9
        scale_factor = 1.0
        if total_w > max_screen_w:
            scale_factor = max_screen_w / total_w
            # We will resize afterwards or reduce fontsize? 
            # Resize is easier.
            
        # Composite them
        # Start X position: Center is w/2. 
        # Leftmost X = (w - total_w*scale)/2
        
        start_x = (w - (total_w * scale_factor)) / 2
        current_x = start_x
        
        vertical_pos_pct = config.get('vertical_position', 75)
        # Center Y
        y_pos = int((h * (vertical_pos_pct / 100.0)) - ((max_h * scale_factor) / 2))

        final_composite_clips = []
        
        for i, clip in enumerate(temp_clips):
            if scale_factor != 1.0:
                clip = clip.resized(scale_factor)
                
            clip = clip.with_position((current_x, y_pos))
            clip = clip.with_start(chunk_start).with_duration(duration)
            
            # Animation (Fade)
            if duration > 0.2:
                try:
                    from moviepy.video.fx import CrossFadeIn, CrossFadeOut
                    clip = clip.with_effects([CrossFadeIn(duration=0.1), CrossFadeOut(duration=0.1)])
                except: pass
                
            final_composite_clips.append(clip)
            
            # Update X
            current_x += clip.w + (space_w * scale_factor)
            
        subtitle_clips.extend(final_composite_clips)
        
    return subtitle_clips
