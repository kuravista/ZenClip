import re
import os
import tempfile
from PIL import Image, ImageDraw, ImageFont

def _parse_preset2_text(text):
    """
    Parse markdown-style text into styled segments.
    **text** = bold + highlighted
    *text* = italic
    regular = normal
    
    Returns list of dicts: [{'text': 'word', 'style': 'bold'/'italic'/'regular', 'highlight': bool}, ...]
    """
    segments = []
    
    # Pattern to match **bold**, *italic*, or ++regular++
    # We need to be careful about order - check ** / ++ before *
    pattern = r'(\*\*[^*]+?\*\*|\+\+[^+]+?\+\+|\*[^*]+?\*)'
    
    parts = re.split(pattern, text)
    
    for part in parts:
        if not part:
            continue
            
        if part.startswith('**') and part.endswith('**'):
            # Bold + highlighted
            clean_text = part[2:-2]
            segments.append({
                'text': clean_text,
                'style': 'bold',
                'highlight': True
            })
        elif part.startswith('++') and part.endswith('++'):
            # Regular (Explicitly valid for Line 3 non-highlighted)
            clean_text = part[2:-2]
            segments.append({
                'text': clean_text,
                'style': 'regular', # or 'bold' if we want it bold white? Regular uses Poppins-Black which is bold enough.
                'highlight': False
            })
        elif part.startswith('*') and part.endswith('*'):
            # Italic
            clean_text = part[1:-1]
            segments.append({
                'text': clean_text,
                'style': 'italic',
                'highlight': False
            })
        else:
            # Regular text
            segments.append({
                'text': part,
                'style': 'regular',
                'highlight': False
            })
    
    return segments


def _render_preset2_hook(config, hook_styles, video_width, video_height, duration):
    """
    Render Preset 2 hook: sentence-style with word highlighting.
    Similar to TikTok/Instagram captions with mixed styles.
    """
    # Import here to avoid circular dependency issues
    import os
    from PIL import ImageFilter
    
    
    preset2_text = hook_styles.get('preset2_content', '').strip()
    if not preset2_text:
        return None
    
    # Colors and styling
    highlight_color = hook_styles.get('highlight_color', '#CBFF00')
    # Use explicit base_color or default to White. Do NOT use 'color' as it might be subtitle color (Lime)
    base_color = hook_styles.get('base_color', '#FFFFFF') 
    
    font_name = hook_styles.get('font', 'Impact')
    font_size = hook_styles.get('font_size', 80)
    top_size = hook_styles.get('top_font_size', int(font_size * 0.5))
    sub_size = hook_styles.get('sub_font_size', int(font_size * 0.5))
    top_gap = hook_styles.get('top_gap', 10)
    bottom_gap = hook_styles.get('bottom_gap', 20)
    
    stroke_width = hook_styles.get('stroke_width', 2)
    stroke_color_hex = hook_styles.get('stroke_color', '#000000')
    
    # Convert hex colors to RGB
    def hex_to_rgb(hex_str):
        hex_str = hex_str.lstrip('#')
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    
    highlight_rgb = hex_to_rgb(highlight_color)
    base_rgb = hex_to_rgb(base_color)
    stroke_rgb = hex_to_rgb(stroke_color_hex)
    
    # Parse text into segments
    segments = _parse_preset2_text(preset2_text)
    
    # Helper to load fonts at specific size
    def get_fonts_at_size(size):
        # Resolve font paths
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
        fonts_dir = os.path.join(project_root, 'static', 'fonts')
        
        poppins_path = os.path.join(fonts_dir, 'Poppins-Black.ttf')
        playfair_path = os.path.join(fonts_dir, 'PlayfairDisplay-Italic.ttf')
        impact_path = os.path.join(fonts_dir, 'Impact.ttf') 
        
        f_reg = None
        f_ital = None
        f_bold = None

        try:
            # 1. Try FontManager (Best case)
            from services.media.font_manager import FontManager
            f_reg = FontManager.load_font('Poppins-Black', size)
            f_ital = FontManager.load_font('PlayfairDisplay-Italic', size)
            f_bold = FontManager.load_font(font_name, size)
        except Exception as e:
            print(f"[WARN] Failed to load fonts via manager in preset2: {e}")
            pass
            
        # Fallbacks if FontManager failed or returned None
        if not f_reg:
            try:
                if os.path.exists(poppins_path):
                    f_reg = ImageFont.truetype(poppins_path, size)
                else:
                    f_reg = ImageFont.truetype("arialbd.ttf", size) # System fallback
            except:
                try:
                    f_reg = ImageFont.truetype("arial.ttf", size)
                except:
                    # Last resort
                    f_reg = ImageFont.load_default()

        if not f_ital:
            try:
                if os.path.exists(playfair_path):
                    f_ital = ImageFont.truetype(playfair_path, size)
                else:
                    f_ital = f_reg 
            except:
                f_ital = f_reg

        if not f_bold:
            try:
                # Try system impact
                f_bold = ImageFont.truetype("impact.ttf", size)
            except:
                f_bold = f_reg 

        return f_reg, f_ital, f_bold

    # Word wrapping: target 3 words per line
    # Build words from segments (preserve segment info with each word)
    words_data = []
    for seg in segments:
        words = seg['text'].split()
        for word in words:
            words_data.append({
                'word': word,
                'style': seg['style'],
                'highlight': seg['highlight']
            })
    
    # Layout algorithm: 3 words per line (flexible for last line)
    lines = []
    words_per_line = 3
    
    for i in range(0, len(words_data), words_per_line):
        line_words = words_data[i:i+words_per_line]
        lines.append(line_words)

    # Pre-calculate line heights and specific fonts for each line
    line_configs = []
    total_height = 0
    
    for i, line in enumerate(lines):
        # Determine scale based on line index
        gap_after = 0
        
        if i == 0: # Top Label (Line 1)
            current_size = top_size
            gap_after = top_gap
        elif i == 1: # Headline (Line 2)
            current_size = font_size
            gap_after = bottom_gap
        else: # Subheading (Line 3+)
            current_size = sub_size
            gap_after = 0 # No extra gap between sub lines
            
        f_reg, f_ital, f_bold = get_fonts_at_size(current_size)
        
        # Calculate line height for this specific line
        current_line_height = int(current_size * 1.3)
        
        line_configs.append({
            'size': current_size,
            'height': current_line_height,
            'gap_after': gap_after,
            'fonts': (f_reg, f_ital, f_bold)
        })
        
        total_height += current_line_height + gap_after

    # Create canvas layers
    padding = 40
    canvas_width = video_width
    canvas_height = total_height + padding * 2
    
    # Layer for the final output
    canvas = Image.new('RGBA', (canvas_width, canvas_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    
    # Layer specifically for the glow (highlighted words)
    glow_canvas = Image.new('RGBA', (canvas_width, canvas_height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_canvas)
    
    # Create dummy draw for text measurement
    dummy_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
    
    # Render lines
    current_y = padding
    
    for i, line in enumerate(lines):
        config = line_configs[i]
        font_regular, font_italic, font_bold = config['fonts']
        line_height = config['height']
        
        # Calculate line width for centering
        line_width = 0
        for word_data in line:
            word = word_data['word'] + ' '
            style = word_data['style']
            
            if style == 'bold':
                font = font_bold
            elif style == 'italic':
                font = font_italic
            else:
                font = font_regular
            
            bbox = dummy_draw.textbbox((0, 0), word, font=font)
            line_width += bbox[2] - bbox[0]
        
        # Center the line
        current_x = (canvas_width - line_width) // 2
        
        # Draw each word
        for word_data in line:
            word = word_data['word']
            style = word_data['style']
            highlight = word_data['highlight']
            
            if style == 'bold':
                font = font_bold
            elif style == 'italic':
                font = font_italic
            else:
                font = font_regular
            
            # Choose color
            if highlight:
                text_color = highlight_rgb
            else:
                text_color = base_rgb
            
            # 1. Add to glow layer if highlighted
            if highlight:
                # Draw simply on the glow layer
                glow_draw.text((current_x, current_y), word, font=font, fill=(*highlight_rgb, 255))
            
            # 2. Draw stroke on main canvas
            if stroke_width > 0:
                for dx in range(-stroke_width, stroke_width + 1):
                    for dy in range(-stroke_width, stroke_width + 1):
                        if dx != 0 or dy != 0:
                            draw.text((current_x + dx, current_y + dy), word, font=font, fill=(*stroke_rgb, 255))
            
            # 3. Draw text on main canvas
            draw.text((current_x, current_y), word, font=font, fill=(*text_color, 255))
            
            # Advance x position
            bbox = dummy_draw.textbbox((0, 0), word + ' ', font=font)
            current_x += bbox[2] - bbox[0]
        
        # Next line
        current_y += line_height + config['gap_after']
    
    # Apply Blur to the glow layer
    # Radius 15-20 gives a nice strong "neon" glow
    glow_layer = glow_canvas.filter(ImageFilter.GaussianBlur(15))
    
    # Enhance glow by pasting it multiple times or modifying alpha? 
    # Usually one pass of Gaussian is soft. For "Rapid Pro" intensity, maybe composite it twice or boost opacity.
    # Let's just composite it behind the main text.
    
    # Final composite: Glow behind -> Main Canvas (Stroke + Text) on top
    
    final_image = Image.new('RGBA', (canvas_width, canvas_height), (0, 0, 0, 0))
    
    # Boost Glow Intensity (Composite multiple times for neon effect)
    final_image = Image.alpha_composite(final_image, glow_layer)
    final_image = Image.alpha_composite(final_image, glow_layer) 
    final_image = Image.alpha_composite(final_image, glow_layer) # 3x Intensity
    
    final_image = Image.alpha_composite(final_image, canvas)
    
    # Convert to ImageClip
    # Save as PNG and return path + position for FFmpeg pipeline
    tmp_dir = tempfile.mkdtemp(prefix='zenclip_hook_')
    tmp_path = os.path.join(tmp_dir, 'hook_preset2.png')
    final_image.save(tmp_path, 'PNG')

    # Position at center-bottom (similar to Preset 1)
    pos_y = int(video_height * 0.65)

    return (tmp_path, ('center', pos_y))
