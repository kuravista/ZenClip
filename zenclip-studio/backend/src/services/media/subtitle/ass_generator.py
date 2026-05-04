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
    Replicates the 'strict timing / cut back' logic from rapid_fire.py
    """
    events = []
    
    highlight_map = style_config.get("highlight_map", {})
    smart_enabled = style_config.get("smart_subtitles", False)
    if highlight_map: smart_enabled = True
    
    # 1. Collect all words
    all_words = []
    for phrase in timings:
        if phrase['end'] < (clip_start - 1.5) or phrase['start'] > (clip_end + 1.5):
            continue
            
        # Use realign_words to respect user edits
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
                'orig_end': w_end
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
        if duration < 0.05: duration = 0.05 # Minimum 50ms
        
        # Recalculate end based on duration
        real_end = start + duration
        
        # 3. Formatting
        text = word['text']
        clean_word = re.sub(r'[^\w\s]', '', text).lower().strip()
        
        # Highlights
        color_tag = ""
        if smart_enabled and clean_word in highlight_map:
            h_color_hex = highlight_map[clean_word]
            ass_h_color = hex_string_to_ass(h_color_hex)
            color_tag = f"{{\\c{ass_h_color}}}"
            
        # Animation (Fade)
        # rapid_fire.py: if dur > 0.2, fade 0.1 or 30%
        anim_tag = ""
        if duration > 0.2:
            fade_ms = int(min(100, duration * 300)) # 0.1s = 100ms
            # \fad(fadeIn, fadeOut)
            anim_tag = f"{{\\fad({fade_ms},0)}}"
            
        final_text = f"{anim_tag}{color_tag}{sanitize_ass_text(text)}"
        
        events.append({
            'start': start,
            'end': real_end,
            'text': final_text
        })
        
    return events

def generate_karaoke_events(timings, clip_start, clip_end, style_config):
    """
    Generate events for 'karaoke' style (multi-line with word highlighting).
    Uses ASS karaoke tags for per-word timing.
    """
    # Placeholder - existing implementation was empty/incomplete
    return []

def generate_mozi_events(timings, clip_start, clip_end, style_config):
    """
    Generate events for 'mozi' style (5-word chunks with size animations).
    Active word gets larger using ASS \\fs tag.
    """
    events = []
    
    # Collect all words
    all_words = []
    for phrase in timings:
        if phrase['end'] < (clip_start - 1.5) or phrase['start'] > (clip_end + 1.5):
            continue
            
        # Use realign_words to respect user edits
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
    
    # Group into chunks smart (max 3 words or ~20 chars)
    chunks = []
    current_chunk = []
    current_char_count = 0
    
    for w in all_words:
        word_len = len(w['text'])
        
        if len(current_chunk) >= 3 or (current_char_count + word_len) > 20:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_char_count = 0
        
        current_chunk.append(w)
        current_char_count += word_len
        
    if current_chunk:
        chunks.append(current_chunk)
    
    base_fontsize = style_config.get('fontsize', 70)
    highlight_fontsize = int(base_fontsize * 1.3)
    
    for chunk in chunks:
        if not chunk:
            continue
        
        chunk_start = chunk[0]['start']
        chunk_end = chunk[-1]['end']
        chunk_duration = chunk_end - chunk_start
        
        if chunk_duration < 0.1:
            continue
        
        # For each word in chunk, create an event showing when it's active
        for word_idx, word in enumerate(chunk):
            # Build text with current word enlarged
            chunk_text = ""
            
            # Colors
            green_ass = "&H0000FF00" 
            white_ass = "&H00FFFFFF"
            
            for i, w in enumerate(chunk):
                if i == word_idx:
                    # Active word - larger and green
                    chunk_text += f"{{\\fs{highlight_fontsize}\\c{green_ass}\\bord3}}{sanitize_ass_text(w['text'])}{{\\fs{base_fontsize}\\c{white_ass}\\bord2}} "
                else:
                    chunk_text += f"{w['text']} "
            
            chunk_text = chunk_text.strip()
            
            # Timing for this word's highlight
            word_start = max(chunk_start, word['start'])
            word_end = min(chunk_end, word['end'])
            
            # Add fade in on first word
            if word_idx == 0:
                chunk_text = f"{{\\fad(120,0)}}{chunk_text}"
            
            events.append({
                'start': word_start,
                'end': word_end,
                'text': chunk_text
            })
    
    return events

def generate_rapid_pro_events(timings, clip_start, clip_end, style_config):
    """
    Generate events for 'rapid_pro' style with glow effect.
    
    Chunking: Max 3 words per chunk
    
    Color Rules:
    - 1 word: White
    - 2 words: Both Yellow (highlight)
    - 3+ words: 1st White, rest Yellow
    
    Layers:
    - Layer 0: Glow effect (soft blur)
    - Layer 1: Text face (sharp)
    
    Args:
        timings: List of phrase timing dicts
        clip_start: Clip start time in seconds
        clip_end: Clip end time in seconds
        style_config: Style configuration dict
        
    Returns:
        list: ASS event dicts with 'start', 'end', 'text', 'Layer'
    """
    events = []
    
    # Colors
    white_ass = "&H00FFFFFF"
    
    # Highlight color (default Yellow)
    h_color_hex = style_config.get('highlight_color', '#FFD700')
    highlight_ass = hex_string_to_ass(h_color_hex)
    
    def get_word_color(chunk_size, word_index):
        if chunk_size == 1:
            return white_ass
        elif chunk_size == 2:
            return highlight_ass
        else: # 3+
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
        
        # Build text parts
        glow_parts = []
        front_parts = []
        
        for i, w in enumerate(chunk):
            color = get_word_color(chunk_size, i)
            # Use Sanitized text
            w_text = sanitize_ass_text(w['text'])
            
            # Glow Layer: Color both face (\c) and border (\3c) to match
            glow_parts.append(f"{{\\c{color}\\3c{color}}}{w_text}")
            
            # Front Layer: Color the text face
            front_parts.append(f"{{\\c{color}}}{w_text}")
             
        glow_text_content = ' '.join(glow_parts)
        front_text_content = ' '.join(front_parts)
        
        # Calculate fixed position
        video_size = style_config.get('video_size', (1080, 1920))
        width, height = video_size
        vertical_pos_percent = style_config.get('vertical_position', 75)
        
        pos_x = int(width / 2)
        pos_y = int(height * (vertical_pos_percent / 100.0))
        pos_tag = f"\\pos({pos_x},{pos_y})"

        if duration > 0.2:
            fade_tag = "\\fad(100,100)"
        else:
            fade_tag = ""

        # --- Layer 0: Glow (Back) ---
        # \bord4\blur20 for soft diffuse glow
        glow_text = f"{{\\bord4\\blur20{fade_tag}{pos_tag}}}{glow_text_content}"
        events.append({
            'start': chunk_start,
            'end': chunk_end,
            'text': glow_text,
            'Layer': 0
        })

        # --- Layer 1: Text (Front) ---
        # \bord0 for clean text face
        front_text = f"{{\\bord0\\blur0{fade_tag}{pos_tag}}}{front_text_content}" 
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
    Based on Rapid Pro but with Pink default, Stroke, and NO Glow (Layer 0).
    
    Chunking: Max 3 words
    
    Color Rules:
    - 1 word: Pastel Pink (#FFB6C1)
    - 2 words: Both Highlight (Yellow)
    - 3+ words: 1st Pink, rest Highlight
    """
    events = []
    
    # Colors
    # Pink #FFB6C1 -> BGR H00C1B6FF
    pink_ass = "&H00C1B6FF"
    
    h_color_hex = style_config.get('highlight_color', '#FFD700')
    highlight_ass = hex_string_to_ass(h_color_hex)
    
    stroke_color_hex = style_config.get('stroke_color', '#000000')
    stroke_ass = hex_string_to_ass(stroke_color_hex)
    
    stroke_width = style_config.get('stroke_width', 2)
    # Ensure visible stroke
    if stroke_width < 1: stroke_width = 2
    
    def get_word_color(chunk_size, word_index):
        if chunk_size == 1:
            return pink_ass
        elif chunk_size == 2:
            return highlight_ass
        else: # 3+
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
            
            # Simple text face with color
            parts.append(f"{{\\c{color}}}{w_text}")
             
        full_text = ' '.join(parts)
        
        # Positioning
        video_size = style_config.get('video_size', (1080, 1920))
        width, height = video_size
        vertical_pos_percent = style_config.get('vertical_position', 75)
        
        pos_x = int(width / 2)
        pos_y = int(height * (vertical_pos_percent / 100.0))
        pos_tag = f"\\pos({pos_x},{pos_y})"
        
        # Stroke config (\bord)
        # We explicitly set \bord argument
        border_tag = f"\\bord{stroke_width}\\3c{stroke_ass}\\blur0"

        if duration > 0.2:
            fade_tag = "\\fad(100,100)"
        else:
            fade_tag = ""

        # Single Layer (Standard)
        final_text = f"{{ {border_tag}{fade_tag}{pos_tag} }}{full_text}"
        
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
    Style: Max 3 words. Mixed fonts (Poppins + Playfair Display Italic). Mixed colors.
    """
    events = []
    
    # Config
    highlight_color_hex = style_config.get('highlight_color', '#ADF91D')
    highlight_ass = hex_string_to_ass(highlight_color_hex)
    white_ass = "&H00FFFFFF"
    
    # Fonts - We need font FAMILY names for ASS \fn tag
    # Assuming fonts are installed or accessible to ffmpeg/worker
    # Use Poppins for normal, Playfair Display for highlighted
    font_normal = "Poppins" 
    font_highlight = "Playfair Display" # Italic handled by \i1
    
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
        
        # Build Text Line
        # Format: {\fnPoppins\c&HFFFFFF}Word {\fnPlayfair Display\i1\c&H00FF00}Word ...
        
        line_parts = []
        
        for i, w in enumerate(chunk):
            w_text = sanitize_ass_text(w['text'])
            
            # Logic: 
            # If 2 words: ALL Highlight
            # If 3+ words: All except first Highlight
            
            is_highlight = False
            if chunk_size == 2:
                is_highlight = True
            elif chunk_size >= 3 and i > 0:
                is_highlight = True
                
            if is_highlight:
                # Playfair Display, Italic, Highlight Color
                # \i1 = Italic on
                part = f"{{\\fn{font_highlight}\\i1\\c{highlight_ass}\\b1}}{w_text}{{\\i0\\b0}}" # Reset italic/bold after? Or explicit set
            else:
                # Poppins, Normal, White
                # \i0 = Italic off
                part = f"{{\\fn{font_normal}\\i0\\c{white_ass}\\b1}}{w_text}"
            
            line_parts.append(part)
            
        final_text = " ".join(line_parts)
        
        # Add position (optional, defaults to style margin)
        # But Elegant usually sits at 70% height
        # Alignment 2 (Bottom Center) with MarginV handles this in Header.
        # But if we want per-line positioning:
        # pos_y = height * 0.7 
        # But let's stick to Styles default for consistency first.
        
        # Add Elegant Animation (Blur + Scale + Fade)
        if duration > 0.2:
            # \fad(150,150): Soft fade in/out
            # \blur5\fscx110\fscy110: Initial state (Blurry, slightly zoomed in)
            # \t(0,250,...): Transition over 250ms to Clear (blur0), Normal Size (100%)
            # This creates a "coming into focus" cinematic effect.
            anim_tags = r"{\fad(150,150)\blur5\fscx110\fscy110\t(0,250,\blur0\fscx100\fscy100)}"
            final_text = f"{anim_tags}{final_text}"
            
        events.append({
            'start': chunk_start,
            'end': chunk_end,
            'text': final_text
        })
        
    return events


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
    Style: 2 lines centered.
    Fonts: Poppins Black (Normal), Playfair Display (Italic/Important).
    Animation: Smooth fade in/out.
    """
    events = []
    
    # Config
    white_ass = "&H00FFFFFF"
    
    # Fonts
    # Assuming fonts are installed/accessible
    # index.html added: JetBrains Mono, Playfair Display, Poppins
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
        
        # Split into 2 lines
        line1_words = chunk[:3]
        line2_words = chunk[3:]
        
        lines = [line1_words, line2_words]
        final_lines_text = []
        
        for line_words in lines:
            if not line_words: continue
            
            line_parts = []
            for w in line_words:
                w_text = sanitize_ass_text(w['text'])
                
                # Importance Heuristic: Length > 4
                is_important = len(w['text']) > 4
                
                if is_important:
                    # Playfair Display, Italic, Bold
                    part = f"{{\\fn{font_accent}\\i1\\b1\\c{white_ass}}}{w_text}{{\\i0\\b0}}"
                else:
                    # Poppins, Black (Heavy weight ~900)
                    part = f"{{\\fn{font_main}\\b1\\c{white_ass}}}{w_text}{{\\b0}}"
                
                line_parts.append(part)
            
            final_lines_text.append(" ".join(line_parts))
            
        # Join lines with \N (newline)
        full_text = "\\N".join(final_lines_text)
        
        # Add Animation (Fade)
        # \fad(150,150)
        anim_tags = r"{\fad(150,150)}"
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
    Style: 2 lines centered.
    Appearance: Drop shadow, simple font (Arial/active font).
    Animation: Fade in/out.
    """
    events = []
    
    # Config
    color_hex = style_config.get('color', '#FFFFFF')
    color_ass = hex_string_to_ass(color_hex)
    
    stroke_color_hex = style_config.get('stroke_color', '#000000')
    stroke_ass = hex_string_to_ass(stroke_color_hex)
    stroke_width = style_config.get('stroke_width', 2)
    
    shadow_color_hex = style_config.get('shadow_color', '#000000')
    shadow_ass = hex_string_to_ass(shadow_color_hex)
    shadow_offset = style_config.get('shadow_offset', 5)
    
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
        
        # Format text
        # Split into 2 lines if long enough?
        # Let's just join them and let ASS wrap or use \N if we want forced split.
        # Simple forced split at midpoint:
        words = [w['text'] for w in chunk]
        mid = len(words) // 2
        
        if len(words) > 4:
            line1 = " ".join(words[:mid])
            line2 = " ".join(words[mid:])
            line2 = line2.strip()
            full_text = f"{line1}\\N{line2}"
        else:
            full_text = " ".join(words)
            
        full_text = sanitize_ass_text(full_text)
        
        # Tags:
        # \shad5 : Shadow offset
        # \4c&H... : Shadow color
        # \bord... : Border width
        # \3c&H... : Border color
        # \fad(200,200) : Fade
        
        anim_tags = ""
        if duration > 0.4:
            anim_tags = "\\fad(300,300)"
            
        style_tags = f"\\shad0\\bord{stroke_width}\\3c{stroke_ass}\\c{color_ass}"
        
        # Pos: Center-Bottom (handled by style usually, but can enforce)
        # Standard style alignment is 2 (Bottom Center).
        
        final_text = f"{{{style_tags}{anim_tags}}}{full_text}"
            
        events.append({
            'start': chunk_start,
            'end': chunk_end,
            'text': final_text
        })
        
    return events

def generate_ass_file(filepath, phrase_timings, clip_start, clip_end, video_size, style_config=None):
    """
    Main entry point to generate .ass file
    """
    if style_config is None: style_config = {}
    
    width, height = video_size
    
    # Scale font size globally for video resolution
    if 'fontsize' in style_config:
        # 1080p typically needs ~2x the pixel value used in web UI
        style_config['fontsize'] = int(style_config['fontsize'] * 2.0)
    
    # Inject video_size into config for styles that need layout (e.g. Karaoke)
    style_config['video_size'] = video_size
    
    # Events - dispatch based on style
    style = style_config.get('style', 'rapid')
    
    if style == 'mozi':
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
    else:
        # Fallback for unknown styles
        print(f"⚠️ Unknown subtitle style '{style}', using phrase-level fallback")
        events = generate_phrase_events(phrase_timings, clip_start, clip_end, style_config)

    print(f"  [DEBUG] ASS Generator: {len(events)} events generated for clip ({clip_start:.2f}s - {clip_end:.2f}s) | Style: {style}")

    # ✅ Build lines list first
    header = generate_ass_header("AutoClip", width, height, style_config)
    lines = [header]
    
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
