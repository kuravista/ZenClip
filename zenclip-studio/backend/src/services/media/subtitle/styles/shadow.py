from services.media.subtitle.utils.fonts import get_font_path
from moviepy import TextClip, CompositeVideoClip
try:
    from moviepy.video.fx import CrossFadeIn, CrossFadeOut
except ImportError:
    # Fallback for older moviepy versions or different import structures
    def CrossFadeIn(duration):
        return lambda clip: clip.crossfadein(duration)
    def CrossFadeOut(duration):
        return lambda clip: clip.crossfadeout(duration)

def create_shadow_subtitles(config, video_clip, phrase_timings, clip_start, clip_end):
    """
    Creates "Shadow" subtitles (2 lines, ~6-8 words).
    Animation: Shadow animation in and out (Fade + Drop Shadow effect).
    """
    subtitle_clips = []
    w, h = video_clip.size
    
    # Config
    font = config.get('font', 'Arial')
    fontsize = int(config.get('fontsize', 60)) # Slightly smaller for 2 lines
    color = config.get('color', 'white')
    stroke_color = config.get('stroke_color', 'black')
    stroke_width = int(config.get('stroke_width', 2))
    
    shadow_color = config.get('shadow_color', 'black')
    shadow_offset = int(config.get('shadow_offset', 5))
    
    # 1. Collect all words (same as rapid_pro)
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

    # 2. Group into chunks (Max 8 words for 2 lines)
    chunks = []
    current_chunk = []
    
    for word in all_words:
        current_chunk.append(word)
        if len(current_chunk) >= 8:
            chunks.append(current_chunk)
            current_chunk = []
            
    if current_chunk:
        chunks.append(current_chunk)
        
    # 3. Create Clips
    font_path = get_font_path(font)
    
    for chunk in chunks:
        if not chunk: continue
        
        chunk_start = chunk[0]['start']
        chunk_end = chunk[-1]['end']
        duration = chunk_end - chunk_start
        if duration < 0.1: duration = 0.1
        
        # Join text
        raw_text = " ".join([w['text'] for w in chunk])
        
        # Word wrap using 'caption' method which handles newlines better
        # We enforce a width to ensure centering and wrapping
        final_text = raw_text # Let caption handle wrapping or use current split logic?
        # User manual split logic (4+4) is usually preferred.
        words_in_chunk = [w['text'] for w in chunk]
        mid = len(words_in_chunk) // 2
        line1 = " ".join(words_in_chunk[:mid])
        line2 = " ".join(words_in_chunk[mid:])
        final_text = f"{line1}\n{line2}" if line2 else line1
        
        # Add a newline and space to force extra height at the bottom and prevent clipping of descenders
        # preventing "g", "y", "j" from being cut off due to tight ImageMagick bounding box
        final_text += "\n "
        
        # Create Main Text
        # Use 'caption' method with fixed width (80% of video) to handle layout and padding naturally
        txt_width = int(w * 0.8)
        
        txt_clip = TextClip(
            text=final_text,
            font=font_path,
            font_size=fontsize,
            color=color,
            stroke_color=stroke_color,
            stroke_width=stroke_width,
            method='caption', # Better for layout and descenders
            size=(txt_width, None), # Fixed width, auto height
            text_align='center'
        )
        
        # Position
        center_x = w / 2
        vertical_pos_pct = config.get('vertical_position', 75)
        center_y = int(h * (vertical_pos_pct / 100.0))
        target_pos = (center_x - txt_clip.w/2, center_y - txt_clip.h/2) # Centered in the 80% box, and box centered on screen
        
        # Initial Position (Lower)
        start_pos = (target_pos[0], target_pos[1] + 50) # 50px lower
        
        txt_clip = txt_clip.with_duration(duration)

        # Animation: Swipe In (Slide Up + Fade In)
        # Swipe Out (Slide Up + Fade Out?? or Just Swipe Out Down? "Swipe in Swipe out")
        # Let's do Slide Up In from bottom, Slide Up Out to top? Or Slide Down Out?
        # "Swipe in swipe out" usually implies consistent direction or reverse.
        # Let's do: Slide Up In, Slide Up Hint Out? Or just Fade Out?
        # Let's do Slide Up In (from +50 to 0) and Fade In.
        # For Out: Fade Out is safer. "Swipe out" might mean Slide Down.
        # Let's try Slide Up (In) and Slide Down (Out)
        
        anim_duration = 0.3
        
        def position_anim(t):
            # t is time from start of clip
            if t < anim_duration:
                # Slide In (Upward: +50 -> 0)
                progress = t / anim_duration
                # Cubic Ease Out: 1 - (1 - t)^3
                progress = 1 - (1 - progress) ** 3
                y_off = 50 * (1 - progress)
                return (target_pos[0], target_pos[1] + y_off)
            elif t > duration - anim_duration:
                # Slide Out (Downward: 0 -> +50)
                # Time from start of exit
                t_exit = t - (duration - anim_duration)
                progress = t_exit / anim_duration
                # Cubic Ease In: t^3
                progress = progress ** 3
                y_off = 50 * progress
                return (target_pos[0], target_pos[1] + y_off)
            else:
                return target_pos

        if duration > anim_duration * 2:
            txt_clip = txt_clip.with_position(position_anim)
            # Removed CrossFade effects to prevent mask composition errors (ValueError: operands could not be broadcast)
        else:
            txt_clip = txt_clip.with_position(target_pos)
            
        combined = CompositeVideoClip([txt_clip], size=video_clip.size).with_start(chunk_start).with_duration(duration)
        subtitle_clips.append(combined)
        
    return subtitle_clips
