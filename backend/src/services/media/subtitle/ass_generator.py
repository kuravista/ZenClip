import os
import re
import math
import numpy as np
from .utils.color import hex_to_rgb
from .utils.fonts import get_font_path
from PIL import ImageFont, ImageDraw, Image
from fontTools.ttLib import TTFont

def get_font_metadata(font_path):
    """
    Extract actual font family name and style flags from TTF/OTF file.
    Returns: (family_name, is_bold, is_italic)
    """
    try:
        font = TTFont(font_path)
        
        # Name table contains font metadata
        name_table = font['name']
        
        family_name = None
        subfamily_name = None
        
        for record in name_table.names:
            # Platform ID 3 = Windows (most compatible)
            # Platform ID 1 = Mac (fallback)
            if record.platformID in [3, 1]:
                if record.nameID == 1:  # Family
                    family_name = record.toUnicode()
                elif record.nameID == 2:  # Subfamily (Regular, Bold, Italic, etc.)
                    subfamily_name = record.toUnicode()
        
        # Fallback if no family name found
        if not family_name:
            family_name = os.path.splitext(os.path.basename(font_path))[0]
            
        # Parse style from subfamily
        is_bold = False
        is_italic = False
        
        if subfamily_name:
            sub = subfamily_name.lower()
            if 'bold' in sub:
                is_bold = True
            if 'italic' in sub or 'oblique' in sub:
                is_italic = True
                
        return family_name, is_bold, is_italic
        
    except Exception as e:
        print(f"⚠️ Font parsing failed: {e}, using filename fallback")
        return os.path.splitext(os.path.basename(font_path))[0], False, False

def sanitize_ass_text(text):
    """
    Sanitize text for ASS format to prevent injection/breakage.
    """
    if not text: return ""
    # Replace braces with full-width variants or strict escaping
    text = text.replace('{', '\\{').replace('}', '\\}')
    return text


def seconds_to_ass_time(seconds):
    """Convert seconds to ASS format H:MM:SS.cs"""
    try:
        if not isinstance(seconds, (int, float)):
           seconds = 0.0
        if seconds < 0:
           seconds = 0.0
        # Prevent NaN/Inf
        if seconds != seconds or seconds == float('inf'):
           seconds = 0.0
           
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centiseconds = int((seconds * 100) % 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"
    except:
        return "0:00:00.00"

def rgb_to_ass_color(rgb):
    """Convert RGB tuple to ASS color &HBBGGRR"""
    # ASS alpha is &H00 (opaque) to &HFF (transparent), usually we want opaque here
    if not rgb: return "&H00FFFFFF"
    return f"&H00{rgb[2]:02X}{rgb[1]:02X}{rgb[0]:02X}"

def hex_string_to_ass(hex_color):
    """Convert hex string (e.g. #FF0000) to ASS color"""
    try:
        rgb = hex_to_rgb(hex_color)
        return rgb_to_ass_color(rgb)
    except:
        return "&H00FFFFFF"

def generate_ass_header(title, width, height, style_config):
    """Generate ASS Script Info and Styles"""
    
    font_name = style_config.get('font', 'Arial')
    
    # Use centralized font path resolution
    font_path = get_font_path(font_name)
    
    ass_font_name = font_name
    bold_val = 0
    italic_val = 0
    
    # Only extract metadata if we have a valid path
    if font_path and os.path.isabs(font_path) and os.path.exists(font_path):
        try:
            family_name, is_bold, is_italic = get_font_metadata(font_path)
            
            # Use the extracted family name (e.g. "Playfair Display")
            ass_font_name = family_name
            
            # Set ASS style flags (-1 is true in ASS usually, but 1 works too. 0 is false)
            bold_val = -1 if is_bold else 0
            italic_val = -1 if is_italic else 0
            
            # print(f"  📝 ASS Font Detected: Family='{ass_font_name}', Bold={is_bold}, Italic={is_italic}")
            
        except Exception as e:
            print(f"⚠️ Error extracting font metadata for '{font_name}': {e}")
            # Fallback to filename (might fail if spaces etc, but usually safest fallback)
            ass_font_name = font_name
            bold_val = 0
            italic_val = 0
    else:
        # No path found, use the provided name as-is
        ass_font_name = font_name
        bold_val = 0
        italic_val = 0

    
    fontsize = style_config.get('fontsize', 70)

    primary_color = hex_string_to_ass(style_config.get('color', '#FFFFFF'))
    outline_color = hex_string_to_ass(style_config.get('stroke_color', '#000000'))
    
    outline_width = style_config.get('stroke_width', 2)
    # Background opacity/box
    # ASS uses BorderStyle=1 (Outline) or 3 (Opaque Box). 
    # Current implementation uses TextClip which has stroke. 
    border_style = 1
    
    vertical_pos_percent = style_config.get('vertical_position', 75)
    # Convert % to pixel margin from bottom roughly, or use Alignment 2 (bottom center) and vertical margin
    # Alignment 2 is Bottom Center.
    # MarginV = height - (height * vertical_pos / 100)
    # Example: 75% down means 25% from bottom.
    margin_v = int(height * (1 - (vertical_pos_percent / 100.0)))
    
    # Define HighlightBox style (BorderStyle=3 for Opaque Box)
    # Background color comes from OutlineColour when BorderStyle=3
    # Use a nice Blue for background: &H00E25D33 (Royal Blue ish)
    box_color = "&H00E25D33"
    
    header = f"""[Script Info]
; Script generated by AutoClip ASS Generator
Title: {title}
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{ass_font_name},{fontsize},{primary_color},&H000000FF,{outline_color},&H00000000,{bold_val},{italic_val},0,0,100,100,0,0,{border_style},{outline_width},0,2,10,10,{margin_v},1
Style: HighlightBox,{ass_font_name},{fontsize},&H0000FF00,&H000000FF,{box_color},&H00000000,{bold_val},{italic_val},0,0,100,100,0,0,3,{outline_width},0,2,10,10,{margin_v},1
Style: KaraokeYellow,Montserrat,{fontsize},&H0000FFFF,&H00999999,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,{outline_width},0,2,10,10,{margin_v},1
Style: MoziDim,{ass_font_name},{fontsize},&H00999999,&H000000FF,{outline_color},&H00000000,{bold_val},{italic_val},0,0,100,100,0,0,1,{outline_width},0,2,10,10,{margin_v},1
Style: KaraokeGreen,Montserrat,{fontsize},&H0000FF00,&H00999999,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,{outline_width},0,2,10,10,{margin_v},1


[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return header

def realign_words(phrase):
    """
    Smart realignment that preserves timing characteristics.
    Only realign if absolutely necessary (user edited).
    """
    text = phrase.get('text', '').strip()
    words = phrase.get('words', [])
    
    if not text:
        return []
    
    def normalize(s):
        return re.sub(r'\s+', ' ', s).strip()
    
    words_text = ' '.join([w['text'] for w in words]).strip()
    
    # If match, use original precise timings
    if words and normalize(words_text) == normalize(text):
        return words
    
    # Mismatch - user edited
    # Try to preserve original timing distribution
    
    new_split = text.split()
    old_split = [w['text'] for w in words]
    
    # If same word count, try 1:1 mapping (Best case: just a typo fix)
    if len(new_split) == len(old_split):
        return [
            {
                'text': new_split[i],
                'start': words[i]['start'],
                'end': words[i]['end']
            }
            for i in range(len(new_split))
        ]
    
    # Different word count - use weighted distribution
    # But preserve pause patterns from original if possible
    
    start_time = phrase['start']
    
    # Sync Fix: If original words exist, use the first word's start time 
    # instead of the phrase start time (which often includes silence/breath).
    if words and len(words) > 0:
        start_time = words[0]['start']
        
    end_time = phrase['end']
    # Sync Fix: Also use last word boundaries if available
    if words and len(words) > 0:
         end_time = words[-1]['end']
    
    duration = end_time - start_time
    
    if not words:
        # No original timing - linear-ish fallback
        word_dur = duration / len(new_split)
        return [
            {
                'text': w,
                'start': start_time + i * word_dur,
                'end': start_time + (i + 1) * word_dur
            }
            for i, w in enumerate(new_split)
        ]
    
    # Calculate average pause from original
    # (Gap between end of word N and start of word N+1)
    original_pauses = []
    for i in range(len(words) - 1):
        gap = words[i+1]['start'] - words[i]['end']
        original_pauses.append(max(0, gap))
    
    import numpy as np
    avg_pause = np.mean(original_pauses) if original_pauses else 0.05
    
    # Distribute new words with preserved pause pattern
    # Total time needed for pauses
    total_pause_time = avg_pause * (len(new_split) - 1)
    
    # Time available for actual speech
    available_speech_time = duration - total_pause_time
    
    # If pauses take up too much time (e.g. added many words), reduce pause assumption
    if available_speech_time < (duration * 0.5):
        available_speech_time = duration * 0.9 # Give 90% to text
        total_pause_time = duration * 0.1
        if len(new_split) > 1:
            avg_pause = total_pause_time / (len(new_split) - 1)
        else:
            avg_pause = 0
    
    # Weight by character count (better than nothing)
    total_chars = sum(len(w) for w in new_split)
    
    new_words_timings = []
    current_time = start_time
    
    for i, w in enumerate(new_split):
        char_ratio = len(w) / total_chars if total_chars > 0 else (1 / len(new_split))
        w_duration = char_ratio * available_speech_time
        
        # Ensure minimum duration for visibility
        if w_duration < 0.1: w_duration = 0.1
        
        real_end = current_time + w_duration
        if real_end > end_time: real_end = end_time
        
        new_words_timings.append({
            'text': w,
            'start': current_time,
            'end': real_end
        })
        
        current_time += w_duration + avg_pause
        if current_time > end_time: current_time = end_time
    
    return new_words_timings

def generate_rapid_fire_events(timings, clip_start, clip_end, style_config):
    """
    Generate events for 'rapid' style (one word at a time).
    VISUAL: Single word displayed huge + white with thick black stroke.
    Word pops in with scale animation. Each word is 1.5x normal size.
    Font: Impact/Heavy Bold for maximum punch.
    """
    events = []

    highlight_map = style_config.get("highlight_map", {})
    smart_enabled = style_config.get("smart_subtitles", False)
    if highlight_map: smart_enabled = True

    white_ass = "&H00FFFFFF"
    yellow_ass = "&H0000FFFF"  # Yellow for highlighted words
    stroke_ass = "&H00000000"  # Black stroke

    base_fontsize = style_config.get('fontsize', 70)
    large_fontsize = int(base_fontsize * 1.5)

    # 1. Collect all words
    all_words = []
    for phrase in timings:
        if phrase['end'] < (clip_start - 1.5) or phrase['start'] > (clip_end + 1.5):
            continue
        words = realign_words(phrase)
        if not words: continue
        for word_info in words:
            w_start = word_info['start'] - clip_start
            w_end = word_info['end'] - clip_start
            if w_end < -1.5 or w_start > (clip_end - clip_start + 1.5): continue
            all_words.append({
                'text': word_info['text'],
                'start': w_start,
                'end': w_end,
            })

    all_words.sort(key=lambda x: x['start'])

    # 2. Timing Logic (Cut Back)
    for i in range(len(all_words)):
        word = all_words[i]
        start = max(0, word['start'])

        if i < len(all_words) - 1:
            next_start = all_words[i+1]['start']
            end = min(word['end'], next_start)
        else:
            end = word['end']

        duration = end - start
        if duration < 0.05: duration = 0.05
        real_end = start + duration

        # 3. Formatting
        text = sanitize_ass_text(word['text'])
        clean_word = re.sub(r'[^\w\s]', '', text).lower().strip()

        # Highlight color
        color = white_ass
        if smart_enabled and clean_word in highlight_map:
            color = hex_string_to_ass(highlight_map[clean_word])

        # Fade in/out
        fade_tag = ""
        if duration > 0.15:
            fade_ms = int(min(80, duration * 200))
            fade_tag = f"\\fad({fade_ms},{fade_ms})"

        # Build: large font, bold, thick stroke
        final_text = (
            f"{{\\c{color}\\fs{large_fontsize}\\b1"
            f"\\bord5\\3c{stroke_ass}"
            f"{fade_tag}}}"
            f"{text}"
        )

        events.append({
            'start': start,
            'end': real_end,
            'text': final_text
        })

    return events

def generate_karaoke_events(timings, clip_start, clip_end, style_config):
    """
    Generate events for 'karaoke' style using ASS native \\kf tags.

    VISUAL: Word-by-word smooth color sweep. Words start dim gray (SecondaryColour),
    then smoothly transition to yellow (PrimaryColour) as each word is spoken.
    Uses KaraokeYellow style definition from ASS header.

    HOW \\kf WORKS:
    - Style's PrimaryColour = what words turn INTO (yellow)
    - Style's SecondaryColour = what words are BEFORE (dim gray)
    - \\kf<centiseconds> = duration before next word starts transitioning
    - libass handles the smooth gradient sweep natively

    Layout: 2 lines, max 6 words per chunk.
    Font: Montserrat Black.
    """
    events = []

    # 1. Collect all words with timing
    all_words = []
    for phrase in timings:
        if phrase['end'] < (clip_start - 1.5) or phrase['start'] > (clip_end + 1.5):
            continue
        words = realign_words(phrase)
        if not words:
            continue
        for w in words:
            w_start = w['start'] - clip_start
            w_end = w['end'] - clip_start
            if w_end < -1.5 or w_start > (clip_end - clip_start + 1.5):
                continue
            all_words.append({
                'text': w['text'],
                'start': w_start,
                'end': w_end
            })

    if not all_words:
        return []

    all_words.sort(key=lambda x: x['start'])

    # 2. Group into chunks (max 6 words for 2-line display)
    chunks = []
    current_chunk = []
    current_chars = 0

    for w in all_words:
        wlen = len(w['text'])
        if len(current_chunk) >= 6 or (current_chars + wlen) > 30:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_chars = 0
        current_chunk.append(w)
        current_chars += wlen

    if current_chunk:
        chunks.append(current_chunk)

    # 3. Generate ONE event per chunk using \kf tags
    for chunk in chunks:
        if not chunk:
            continue

        chunk_start = chunk[0]['start']
        chunk_end = chunk[-1]['end']
        duration = chunk_end - chunk_start
        if duration < 0.1:
            continue

        # Split into 2 lines
        mid = (len(chunk) + 1) // 2
        line1 = chunk[:mid]
        line2 = chunk[mid:]

        # Build karaoke text with \kf tags
        # \kf duration is in centiseconds (1/100th of a second)
        karaoke_parts = []

        all_chunk_words = line1[:]
        if line2:
            # Insert \N line break between line1 and line2
            pass

        for i, w in enumerate(line1):
            w_text = sanitize_ass_text(w['text'])
            word_dur_cs = max(1, int((w['end'] - w['start']) * 100))
            karaoke_parts.append(f"{{\\kf{word_dur_cs}}}{w_text}")

        if line2:
            karaoke_parts.append("\\N")  # Line break
            for w in line2:
                w_text = sanitize_ass_text(w['text'])
                word_dur_cs = max(1, int((w['end'] - w['start']) * 100))
                karaoke_parts.append(f"{{\\kf{word_dur_cs}}}{w_text}")

        full_text = " ".join(karaoke_parts)
        # Remove space around \N line break
        full_text = full_text.replace(" \\N ", "\\N")

        # Fade in at chunk start
        fade_tag = "\\fad(150,100)" if duration > 0.2 else ""
        final_text = f"{{{fade_tag}}}{full_text}"

        events.append({
            'start': chunk_start,
            'end': chunk_end,
            'text': final_text,
            'Style': 'KaraokeYellow'  # Use the dedicated karaoke style
        })

    return events

def generate_mozi_events(timings, clip_start, clip_end, style_config):
    """
    Generate events for 'mozi' style — per-word highlight with 1.5x size boost.

    VISUAL: Shows 3-5 words at a time. The currently spoken word is bright green
    at 1.5x font size. Other words are dim gray at normal size.
    Per-word highlight sweep — one word highlighted at a time.

    HOW IT WORKS:
    - Group words into chunks of 3-5
    - Generate ONE event per word within each chunk
    - Each event renders the full chunk but with different word highlighted
    - Uses \\c + \\fs override tags for active word styling
    """
    events = []

    # Collect all words with timing
    all_words = []
    for phrase in timings:
        if phrase['end'] < (clip_start - 1.5) or phrase['start'] > (clip_end + 1.5):
            continue
        words = realign_words(phrase)
        if not words:
            continue
        for w in words:
            w_start = w['start'] - clip_start
            w_end = w['end'] - clip_start
            if w_end < -1.5 or w_start > (clip_end - clip_start + 1.5):
                continue
            all_words.append({
                'text': w['text'],
                'start': w_start,
                'end': w_end
            })

    if not all_words:
        return []

    all_words.sort(key=lambda x: x['start'])

    # Group into chunks of 3-5 words
    chunks = []
    current_chunk = []
    current_chars = 0

    for w in all_words:
        wlen = len(w['text'])
        if len(current_chunk) >= 5 or (current_chars + wlen) > 28:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_chars = 0
        current_chunk.append(w)
        current_chars += wlen

    if current_chunk:
        chunks.append(current_chunk)

    fontsize = style_config.get('fontsize', 70)
    active_fontsize = int(fontsize * 1.5)
    # Bright green for active word, dim gray for others
    active_color = "&H0000FF00"   # Bright green (BGR)
    dim_color = "&H00999999"      # Dim gray

    # Generate one event per word — each highlights a different word
    for chunk in chunks:
        if not chunk:
            continue

        chunk_start = chunk[0]['start']
        chunk_end = chunk[-1]['end']
        chunk_duration = chunk_end - chunk_start

        # Pre-chunk: show all words dim during brief lead-in
        # Generate per-word events
        for i, word in enumerate(chunk):
            w_start = word['start']
            w_end = word['end']
            w_dur = w_end - w_start
            if w_dur < 0.05:
                continue

            # Build text: all words visible, but active one is highlighted + 1.5x
            parts = []
            for j, w in enumerate(chunk):
                w_text = sanitize_ass_text(w['text'])
                if j == i:
                    # Active word: bright green + 1.5x font size
                    parts.append(f"{{\\c{active_color}\\fs{active_fontsize}\\b1}}{w_text}{{\\c{dim_color}\\fs{fontsize}\\b0}}")
                else:
                    # Dim word
                    parts.append(f"{{\\c{dim_color}\\fs{fontsize}}}{w_text}")

            full_text = " ".join(parts)

            # Fade in for first word of chunk
            fade_tag = ""
            if i == 0 and chunk_duration > 0.2:
                fade_tag = "\\fad(120,80)"

            final_text = f"{{{fade_tag}}}{full_text}"

            events.append({
                'start': w_start,
                'end': w_end,
                'text': final_text,
                'Style': 'Default'
            })

        # Brief gap after chunk (if no overlap with next chunk)
        # Add a small fade-out event showing all words dim
        if chunk_duration > 0.5:
            gap_start = chunk_end
            gap_end = chunk_end + 0.15
            parts = []
            for w in chunk:
                w_text = sanitize_ass_text(w['text'])
                parts.append(f"{{\\c{dim_color}\\fs{fontsize}}}{w_text}")
            gap_text = " ".join(parts)
            events.append({
                'start': gap_start,
                'end': gap_end,
                'text': f"{{\\fad(0,100)}}{gap_text}",
                'Style': 'Default'
            })

    return events

def generate_rapid_pro_events(timings, clip_start, clip_end, style_config):
    """
    Generate events for 'rapid_pro' style with glow effect.
    VISUAL: Dual-layer neon glow. Yellow highlighted words with soft glow behind.
    Max 3 words per chunk.
    1 word = white. 2 words = both yellow. 3+ = first white, rest yellow.
    Layer 0 = soft diffuse glow, Layer 1 = sharp text.
    """
    events = []

    white_ass = "&H00FFFFFF"
    h_color_hex = style_config.get('highlight_color', '#FFD700')
    highlight_ass = hex_string_to_ass(h_color_hex)

    def get_word_color(chunk_size, word_index):
        if chunk_size == 1:
            return white_ass
        elif chunk_size == 2:
            return highlight_ass
        else:
            return white_ass if word_index == 0 else highlight_ass

    # 1. Collect words
    all_words = []
    for phrase in timings:
        if phrase['end'] < (clip_start - 1.5) or phrase['start'] > (clip_end + 1.5):
            continue
        words = realign_words(phrase)
        if not words: continue
        for w in words:
            w_start = w['start'] - clip_start
            w_end = w['end'] - clip_start
            if w_end < -1.5 or w_start > (clip_end - clip_start + 1.5): continue
            all_words.append({
                'text': w['text'],
                'start': w_start,
                'end': w_end
            })

    all_words.sort(key=lambda x: x['start'])
    if not all_words: return []

    # 2. Chunking
    chunks = []
    current_chunk = []
    for w in all_words:
        current_chunk.append(w)
        if len(current_chunk) >= 3:
            chunks.append(current_chunk)
            current_chunk = []
    if current_chunk:
        chunks.append(current_chunk)

    # 3. Generate Events
    for chunk in chunks:
        if not chunk: continue

        chunk_start = chunk[0]['start']
        chunk_end = chunk[-1]['end']
        duration = chunk_end - chunk_start
        if duration < 0.1: continue

        chunk_size = len(chunk)

        glow_parts = []
        front_parts = []

        for i, w in enumerate(chunk):
            color = get_word_color(chunk_size, i)
            w_text = sanitize_ass_text(w['text'])
            glow_parts.append(f"{{\\c{color}\\3c{color}}}{w_text}")
            front_parts.append(f"{{\\c{color}}}{w_text}")

        glow_text_content = ' '.join(glow_parts)
        front_text_content = ' '.join(front_parts)

        # Position
        video_size = style_config.get('video_size', (1080, 1920))
        width, height = video_size
        vertical_pos_percent = style_config.get('vertical_position', 75)
        pos_x = int(width / 2)
        pos_y = int(height * (vertical_pos_percent / 100.0))
        pos_tag = f"\\pos({pos_x},{pos_y})"

        fade_tag = "\\fad(100,100)" if duration > 0.2 else ""

        # Layer 0: Glow (soft blur + thick border for diffuse effect)
        glow_text = f"{{\\b1\\bord6\\blur25{fade_tag}{pos_tag}}}{glow_text_content}"
        events.append({
            'start': chunk_start,
            'end': chunk_end,
            'text': glow_text,
            'Layer': 0
        })

        # Layer 1: Sharp text face
        front_text = f"{{\\b1\\bord1\\blur0{fade_tag}{pos_tag}}}{front_text_content}"
        events.append({
            'start': chunk_start,
            'end': chunk_end,
            'text': front_text,
            'Layer': 1
        })

    return events
    
def generate_pod_d_events(timings, clip_start, clip_end, style_config):
    """
    Generate events for 'pod_d' style.
    VISUAL: Pastel Pink text (#FFB6C1) with thick black stroke.
    Pop-in animation (scale up then settle). Max 3 words per chunk.
    1 word = all pink. 2 words = both yellow. 3+ = first pink, rest yellow.
    No glow layer (single layer only).
    """
    events = []

    # Colors
    pink_ass = "&H00C1B6FF"  # Pastel Pink BGR

    h_color_hex = style_config.get('highlight_color', '#FFD700')
    highlight_ass = hex_string_to_ass(h_color_hex)

    stroke_color_hex = style_config.get('stroke_color', '#000000')
    stroke_ass = hex_string_to_ass(stroke_color_hex)
    stroke_width = max(style_config.get('stroke_width', 4), 3)

    base_fontsize = style_config.get('fontsize', 70)

    def get_word_color(chunk_size, word_index):
        if chunk_size == 1:
            return pink_ass
        elif chunk_size == 2:
            return highlight_ass
        else:
            return pink_ass if word_index == 0 else highlight_ass

    # 1. Collect words
    all_words = []
    for phrase in timings:
        if phrase['end'] < (clip_start - 1.5) or phrase['start'] > (clip_end + 1.5):
            continue
        words = realign_words(phrase)
        if not words: continue
        for w in words:
            w_start = w['start'] - clip_start
            w_end = w['end'] - clip_start
            if w_end < -1.5 or w_start > (clip_end - clip_start + 1.5): continue
            all_words.append({
                'text': w['text'],
                'start': w_start,
                'end': w_end
            })

    all_words.sort(key=lambda x: x['start'])
    if not all_words: return []

    # 2. Chunking
    chunks = []
    current_chunk = []
    for w in all_words:
        current_chunk.append(w)
        if len(current_chunk) >= 3:
            chunks.append(current_chunk)
            current_chunk = []
    if current_chunk:
        chunks.append(current_chunk)

    # 3. Generate Events
    for chunk in chunks:
        if not chunk: continue

        chunk_start = chunk[0]['start']
        chunk_end = chunk[-1]['end']
        duration = chunk_end - chunk_start
        if duration < 0.1: continue

        chunk_size = len(chunk)

        parts = []
        for i, w in enumerate(chunk):
            color = get_word_color(chunk_size, i)
            w_text = sanitize_ass_text(w['text'])
            parts.append(f"{{\\c{color}}}{w_text}")

        full_text = ' '.join(parts)

        # Fade
        fade_tag = ""
        if duration > 0.2:
            fade_tag = "\\fad(100,100)"

        # Stroke
        border_tag = f"\\b1\\bord{stroke_width}\\3c{stroke_ass}"

        final_text = f"{{{border_tag}{fade_tag}}}{full_text}"

        events.append({
            'start': chunk_start,
            'end': chunk_end,
            'text': final_text,
            'Layer': 1
        })

    return events

def generate_elegant_events(timings, clip_start, clip_end, style_config):
    """
    Generate events for 'elegant' style.
    VISUAL: Dual-font design. Poppins Regular (white) + Playfair Display Italic (lime green).
    Max 3 words per chunk. Cinematic blur-to-focus animation.
    2 words = all highlighted. 3+ words = first normal, rest highlighted.
    """
    events = []

    # Config
    highlight_color_hex = style_config.get('highlight_color', '#ADF91D')
    highlight_ass = hex_string_to_ass(highlight_color_hex)
    white_ass = "&H00FFFFFF"

    font_normal = "Poppins"
    font_highlight = "Playfair Display"

    # 1. Collect and Split Words
    all_words = []
    for phrase in timings:
        if phrase['end'] < (clip_start - 1.5) or phrase['start'] > (clip_end + 1.5):
            continue
        words = realign_words(phrase)
        if not words: continue
        for w in words:
            w_start = w['start'] - clip_start
            w_end = w['end'] - clip_start
            if w_end < -1.5 or w_start > (clip_end - clip_start + 1.5): continue
            all_words.append({
                'text': w['text'],
                'start': w_start,
                'end': w_end
            })

    all_words.sort(key=lambda x: x['start'])
    if not all_words: return []

    # 2. Group into chunks (Max 3)
    chunks = []
    current_chunk = []
    for w in all_words:
        current_chunk.append(w)
        if len(current_chunk) >= 3:
            chunks.append(current_chunk)
            current_chunk = []
    if current_chunk:
        chunks.append(current_chunk)

    # 3. Generate Events
    for chunk in chunks:
        if not chunk: continue

        chunk_start = chunk[0]['start']
        chunk_end = chunk[-1]['end']
        duration = chunk_end - chunk_start
        if duration < 0.1: continue

        chunk_size = len(chunk)

        line_parts = []
        for i, w in enumerate(chunk):
            w_text = sanitize_ass_text(w['text'])

            is_highlight = False
            if chunk_size == 2:
                is_highlight = True
            elif chunk_size >= 3 and i > 0:
                is_highlight = True

            if is_highlight:
                # Playfair Display, Italic, Bold, Lime Green
                part = f"{{\\fn{font_highlight}\\i1\\b1\\c{highlight_ass}\\bord2}}{w_text}"
            else:
                # Poppins, Normal, Bold, White
                part = f"{{\\fn{font_normal}\\i0\\b1\\c{white_ass}\\bord1}}{w_text}"

            line_parts.append(part)

        final_text = " ".join(line_parts)

        # Smooth fade only (no \t animations — unreliable in FFmpeg burn-in)
        if duration > 0.2:
            anim_tags = "{\\fad(150,150)}"
            final_text = f"{anim_tags}{final_text}"

        events.append({
            'start': chunk_start,
            'end': chunk_end,
            'text': final_text
        })

    return events


def _get_fonts_dir():
    """Find the fonts directory in the project."""
    candidates = [
        os.path.join(os.path.dirname(__file__), '..', '..', 'static', 'fonts'),
        os.path.join(os.path.dirname(__file__), '..', 'resources', 'fonts'),
    ]
    for c in candidates:
        c = os.path.normpath(c)
        if os.path.isdir(c):
            return c
    return None


def _embed_fonts_section(style):
    """
    Generate [Fonts] section for ASS file with base64-encoded fonts.
    This makes the ASS file self-contained — no external fontsdir needed.
    libass will use these embedded fonts automatically.
    """
    fonts_dir = _get_fonts_dir()
    if not fonts_dir:
        return ""

    # Map styles to their required fonts
    style_font_map = {
        'karaoke':    ['Montserrat-Black.otf', 'Montserrat-Bold.otf'],
        'mozi':       ['Montserrat-Black.otf', 'Montserrat-Bold.otf'],
        'elegant':    ['Poppins-Regular.ttf', 'Poppins-Bold.ttf', 'PlayfairDisplay-Italic.ttf'],
        'boxies':     ['Poppins-Bold.ttf', 'Poppins-Regular.ttf'],
        'shadow':     ['Poppins-Bold.ttf', 'Poppins-Regular.ttf'],
        'pod_d':      ['Poppins-Bold.ttf', 'Poppins-Regular.ttf'],
        'rapid_pro':  ['Poppins-Bold.ttf', 'Poppins-Regular.ttf'],
        'prince':     ['Poppins-Black.ttf', 'Poppins-Regular.ttf', 'PlayfairDisplay-Italic.ttf'],
        'rapid':      ['Poppins-Bold.ttf', 'Poppins-Regular.ttf'],
        'phrase':     ['Poppins-Regular.ttf'],
    }

    needed = style_font_map.get(style, ['Poppins-Regular.ttf', 'Poppins-Bold.ttf'])

    import base64
    fonts_section = ""
    fonts_found = 0

    for font_file in needed:
        font_path = os.path.join(fonts_dir, font_file)
        if not os.path.exists(font_path):
            continue

        try:
            with open(font_path, 'rb') as f:
                raw = f.read()
            encoded = base64.b64encode(raw).decode('ascii')

            # ASS fontname: use the filename without extension
            fontname = os.path.splitext(font_file)[0]

            # Wrap at 80 chars
            lines = [encoded[i:i+80] for i in range(0, len(encoded), 80)]

            fonts_section += f"\nfontname: {fontname}\n"
            fonts_section += '\n'.join(lines) + '\n'
            fonts_found += 1
        except Exception:
            pass

    if fonts_found > 0:
        return f"\n[Fonts]\n{fonts_section}"
    return ""


def generate_phrase_events(timings, clip_start, clip_end, style_config):
    """
    Generate simple phrase-level events (fallback for unknown styles).
    Shows full phrase at once without word-level animation.
    """
    events = []
    
    for phrase in timings:
        if phrase['end'] < (clip_start - 1.5) or phrase['start'] > (clip_end + 1.5):
            continue
        
        p_start = max(0, phrase['start'] - clip_start)
        p_end = min(clip_end - clip_start, phrase['end'] - clip_start)
        
        duration = p_end - p_start
        if duration < 0.1:
            continue
        
        text = sanitize_ass_text(phrase['text'])
        fade_tag = "{\\fad(100,0)}"
        
        events.append({
            'start': p_start,
            'end': p_end,
            'text': f"{fade_tag}{text}"
        })
    
    return events

def generate_prince_events(timings, clip_start, clip_end, style_config):
    """
    Generate events for 'prince' style.
    VISUAL: Dual-font hierarchy. Poppins Black for short words,
    Playfair Display Italic for important/long words (>4 chars).
    Max 6 words split into 2 lines (3+3). White text with black outline.
    Smooth fade animation.
    """
    events = []

    white_ass = "&H00FFFFFF"
    stroke_ass = "&H00000000"

    font_main = "Poppins"
    font_accent = "Playfair Display"

    # 1. Collect words
    all_words = []
    for phrase in timings:
        if phrase['end'] < (clip_start - 1.5) or phrase['start'] > (clip_end + 1.5):
            continue
        words = realign_words(phrase)
        if not words: continue
        for w in words:
            w_start = w['start'] - clip_start
            w_end = w['end'] - clip_start
            if w_end < -1.5 or w_start > (clip_end - clip_start + 1.5): continue
            all_words.append({
                'text': w['text'],
                'start': w_start,
                'end': w_end
            })

    all_words.sort(key=lambda x: x['start'])
    if not all_words: return []

    # 2. Chunking (Max 6 words, split into 2 lines)
    chunks = []
    current_chunk = []
    for w in all_words:
        current_chunk.append(w)
        if len(current_chunk) >= 6:
            chunks.append(current_chunk)
            current_chunk = []
    if current_chunk:
        chunks.append(current_chunk)

    # 3. Generate Events
    for chunk in chunks:
        if not chunk: continue

        chunk_start = chunk[0]['start']
        chunk_end = chunk[-1]['end']
        duration = chunk_end - chunk_start
        if duration < 0.1: continue

        line1_words = chunk[:3]
        line2_words = chunk[3:]

        lines = [line1_words, line2_words]
        final_lines_text = []

        for line_words in lines:
            if not line_words: continue
            line_parts = []
            for w in line_words:
                w_text = sanitize_ass_text(w['text'])
                is_important = len(w['text']) > 4

                if is_important:
                    # Playfair Display, Italic, Bold, larger
                    part = (
                        f"{{\\fn{font_accent}\\i1\\b1\\c{white_ass}"
                        f"\\bord3\\3c{stroke_ass}\\fs"
                        f"{int(style_config.get('fontsize', 70) * 1.2)}}}"
                        f"{w_text}"
                    )
                else:
                    # Poppins, Bold, normal size
                    part = f"{{\\fn{font_main}\\b1\\c{white_ass}\\bord2\\3c{stroke_ass}}}{w_text}"

                line_parts.append(part)

            final_lines_text.append(" ".join(line_parts))

        full_text = "\\N".join(final_lines_text)

        # Smooth fade only (no \t animations — unreliable in FFmpeg burn-in)
        anim_tags = "{\\fad(200,200)}"
        full_text = f"{anim_tags}{full_text}"

        events.append({
            'start': chunk_start,
            'end': chunk_end,
            'text': full_text
        })

    return events

def generate_shadow_events(timings, clip_start, clip_end, style_config):
    """
    Generate events for 'shadow' style.
    VISUAL: White text with thick black outline + deep shadow.
    2-line layout. Slide-up animation. Font: Poppins Bold.
    No word-level animation - reads like real subtitles.
    """
    events = []

    # Config
    color_hex = style_config.get('color', '#FFFFFF')
    color_ass = hex_string_to_ass(color_hex)

    stroke_color_hex = style_config.get('stroke_color', '#000000')
    stroke_ass = hex_string_to_ass(stroke_color_hex)
    stroke_width = style_config.get('stroke_width', 4)

    # 1. Collect words
    all_words = []
    for phrase in timings:
        if phrase['end'] < (clip_start - 1.5) or phrase['start'] > (clip_end + 1.5):
            continue
        words = realign_words(phrase)
        if not words: continue
        for w in words:
            w_start = w['start'] - clip_start
            w_end = w['end'] - clip_start
            if w_end < -1.5 or w_start > (clip_end - clip_start + 1.5): continue
            all_words.append({
                'text': w['text'],
                'start': w_start,
                'end': w_end
            })

    all_words.sort(key=lambda x: x['start'])
    if not all_words: return []

    # 2. Chunking (Max 8 words for 2 lines)
    chunks = []
    current_chunk = []
    for w in all_words:
        current_chunk.append(w)
        if len(current_chunk) >= 8:
            chunks.append(current_chunk)
            current_chunk = []

    if current_chunk:
        chunks.append(current_chunk)

    # 3. Generate Events
    for chunk in chunks:
        if not chunk: continue

        chunk_start = chunk[0]['start']
        chunk_end = chunk[-1]['end']
        duration = chunk_end - chunk_start
        if duration < 0.1: continue

        words = [w['text'] for w in chunk]
        mid = len(words) // 2

        if len(words) > 4:
            line1 = " ".join(words[:mid])
            line2 = " ".join(words[mid:]).strip()
            full_text = f"{line1}\\N{line2}"
        else:
            full_text = " ".join(words)

        full_text = sanitize_ass_text(full_text)

        # Strong visual: deep shadow + thick outline
        # \shad8 = 8px shadow offset
        # \4c = shadow color (black)
        # \bord = thick black outline
        style_tags = (
            f"\\fnPoppins\\b1"
            f"\\c{color_ass}"
            f"\\bord{stroke_width}\\3c{stroke_ass}"
            f"\\shad8\\4c&H00000000"
        )

        # Static position + fade (no \move — unreliable in FFmpeg burn-in)
        video_size = style_config.get('video_size', (1080, 1920))
        width, height = video_size
        vert_pct = style_config.get('vertical_position', 75)
        pos_x = int(width / 2)
        pos_y = int(height * (vert_pct / 100.0))

        if duration > 0.3:
            anim_tags = f"\\pos({pos_x},{pos_y})\\fad(250,250)"
        else:
            anim_tags = f"\\pos({pos_x},{pos_y})"

        final_text = f"{{{style_tags}{anim_tags}}}{full_text}"

        events.append({
            'start': chunk_start,
            'end': chunk_end,
            'text': final_text
        })

    return events

def generate_boxies_events(timings, clip_start, clip_end, style_config):
    """
    Generate events for 'boxies' style.
    VISUAL: Two distinct lines. Line 1: UPPERCASE white text with black stroke.
    Line 2: Normal case text inside a colored background box (blue #2563EB).
    Line 2 fades in 0.2s after line 1. Max 5 words split 3/2.
    Font: Poppins Bold.
    """
    events = []

    # Config
    white_ass = "&H00FFFFFF"
    bg_color_hex = style_config.get('bg_color', '#2563EB')
    bg_ass = hex_string_to_ass(bg_color_hex)
    stroke_color_hex = style_config.get('stroke_color', '#000000')
    stroke_ass = hex_string_to_ass(stroke_color_hex)
    stroke_width = max(style_config.get('stroke_width', 3), 3)
    base_fontsize = style_config.get('fontsize', 70)

    # 1. Collect all words
    all_words = []
    for phrase in timings:
        if phrase['end'] < (clip_start - 1.5) or phrase['start'] > (clip_end + 1.5):
            continue
        words = realign_words(phrase)
        if not words: continue
        for w in words:
            w_start = w['start'] - clip_start
            w_end = w['end'] - clip_start
            if w_end < -1.5 or w_start > (clip_end - clip_start + 1.5): continue
            all_words.append({
                'text': w['text'],
                'start': w_start,
                'end': w_end
            })

    if not all_words:
        return []

    all_words.sort(key=lambda x: x['start'])

    # 2. Group into chunks (max 5 words)
    chunks = []
    current_chunk = []
    for w in all_words:
        current_chunk.append(w)
        if len(current_chunk) >= 5:
            chunks.append(current_chunk)
            current_chunk = []
    if current_chunk:
        chunks.append(current_chunk)

    # 3. Generate events
    for chunk in chunks:
        if not chunk: continue

        chunk_start = chunk[0]['start']
        chunk_end = chunk[-1]['end']
        duration = chunk_end - chunk_start
        if duration < 0.1: continue

        split = (len(chunk) + 1) // 2
        line1_words = chunk[:split]
        line2_words = chunk[split:]

        # Line 1: UPPERCASE white text with thick black stroke
        line1_text = " ".join(
            sanitize_ass_text(w['text'].upper()) for w in line1_words
        )

        # Line 2: Normal text with colored background box
        line2_text = " ".join(
            sanitize_ass_text(w['text']) for w in line2_words
        )

        font_tag = "\\fnPoppins\\b1"

        if line2_text:
            line1_styled = (
                f"{{\\c{white_ass}{font_tag}"
                f"\\bord{stroke_width}\\3c{stroke_ass}}}"
                f"{line1_text}"
            )
            # Box effect: very thick border in bg color creates visible box
            line2_styled = (
                f"{{\\c{white_ass}{font_tag}"
                f"\\bord12\\3c{bg_ass}\\blur0}}"
                f"{line2_text}"
            )
            full_text = f"{line1_styled}\\N{line2_styled}"
        else:
            full_text = (
                f"{{\\c{white_ass}{font_tag}"
                f"\\bord{stroke_width}\\3c{stroke_ass}}}"
                f"{line1_text}"
            )

        # Animation
        fade_tag = "\\fad(150,150)" if duration > 0.2 else ""
        final_text = f"{{{fade_tag}}}{full_text}"

        events.append({
            'start': chunk_start,
            'end': chunk_end,
            'text': final_text
        })

        # Line 2 delayed fade-in as separate overlay on layer 1
        if line2_text and duration > 0.5:
            line2_start = chunk_start + 0.2
            line2_delayed = (
                f"{{\\fad(200,200)\\c{white_ass}{font_tag}"
                f"\\bord12\\3c{bg_ass}}}"
                f"{line2_text}"
            )
            events.append({
                'start': line2_start,
                'end': chunk_end,
                'text': line2_delayed,
                'Layer': 1
            })

    return events

def generate_ass_file(filepath, phrase_timings, clip_start, clip_end, video_size, style_config=None):
    """
    Main entry point to generate .ass file
    """
    if style_config is None: style_config = {}

    # CRITICAL: copy the dict so we don't mutate the caller's reference.
    # Callers share style_config across multiple clips — mutation causes
    # exponential fontsize growth (48→96→192→384→...).
    style_config = dict(style_config)

    width, height = video_size

    # Scale font size globally for video resolution
    if 'fontsize' in style_config:
        # 1080p typically needs ~2x the pixel value used in web UI
        style_config['fontsize'] = int(style_config['fontsize'] * 2.0)
    
    # Inject video_size into config for styles that need layout (e.g. Karaoke)
    style_config['video_size'] = video_size
    
    # Events - dispatch based on style
    # Normalize: frontend sends 'rapid_fire', backend uses 'rapid'
    style = style_config.get('style', 'rapid')
    if style == 'rapid_fire':
        style = 'rapid'
    style_config['style'] = style

    if style == 'karaoke':
        events = generate_karaoke_events(phrase_timings, clip_start, clip_end, style_config)
    elif style == 'mozi':
        events = generate_mozi_events(phrase_timings, clip_start, clip_end, style_config)
    elif style == 'rapid':
        events = generate_rapid_fire_events(phrase_timings, clip_start, clip_end, style_config)
    elif style == 'rapid_pro':
        events = generate_rapid_pro_events(phrase_timings, clip_start, clip_end, style_config)
    elif style == 'pod_d':
        events = generate_pod_d_events(phrase_timings, clip_start, clip_end, style_config)
    elif style == 'elegant':
        events = generate_elegant_events(phrase_timings, clip_start, clip_end, style_config)
    elif style == 'shadow':
        events = generate_shadow_events(phrase_timings, clip_start, clip_end, style_config)
    elif style == 'boxies':
        events = generate_boxies_events(phrase_timings, clip_start, clip_end, style_config)
    elif style == 'prince':
        events = generate_prince_events(phrase_timings, clip_start, clip_end, style_config)
    else:
        # Fallback for unknown styles
        print(f"⚠️ Unknown subtitle style '{style}', using phrase-level fallback")
        events = generate_phrase_events(phrase_timings, clip_start, clip_end, style_config)

    print(f"  [DEBUG] ASS Generator: {len(events)} events generated for clip ({clip_start:.2f}s - {clip_end:.2f}s) | Style: {style}")

    # ✅ Build lines list first
    header = generate_ass_header("AutoClip", width, height, style_config)
    # Embed fonts directly in ASS file so FFmpeg doesn't need external fontsdir
    fonts_section = _embed_fonts_section(style)
    lines = [header, fonts_section]
    
    for e in events:
        start_str = seconds_to_ass_time(e['start'])
        end_str = seconds_to_ass_time(e['end'])
        
        start_str = seconds_to_ass_time(e['start'])
        end_str = seconds_to_ass_time(e['end'])
        
        # Text is already sanitized at event level, do not double-sanitize here
        # or it breaks the tags!
        text = e.get('text', '')
        
        layer = e.get('Layer', 0)
        style_name = e.get('Style', 'Default')
        
        line = f"Dialogue: {layer},{start_str},{end_str},{style_name},,0,0,0,,{text}\n"
        lines.append(line)
        
    # ✅ Single join operation - O(n)
    content = ''.join(lines)
        
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"Error writing ASS file: {e}")
        return False
