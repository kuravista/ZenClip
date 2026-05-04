from PIL import Image, ImageDraw, ImageFont
from moviepy.video.VideoClip import ImageClip
import numpy as np
import os

from services.media.subtitle.utils.fonts import get_font_path

def _render_preset4_hook(config, hook_styles, video_width, video_height, duration):
    """
    Render Preset 4 hook: Simple Box Design.
    All text elements (top, heading, subheading) contained in a single rounded box.
    Clean, minimalist aesthetic with colored background and white text.
    """
    
    # 1. Extract Settings
    line1_text = hook_styles.get('top_text', '').strip()
    line2_text = hook_styles.get('headline', '').strip()
    line3_text = hook_styles.get('subheading', '').strip()
    
    if not line1_text and not line2_text and not line3_text:
        return None

    # Colors
    heading_color_hex = hook_styles.get('color', '#2F54EB')
    white_hex = '#FFFFFF'
    stroke_color_hex = hook_styles.get('stroke_color', '#000000')
    
    # Font settings
    font_name = hook_styles.get('font', 'Impact')
    raw_font_size = hook_styles.get('hook_font_size') or hook_styles.get('font_size', 100)
    
    # Scale based on video width
    try:
        scale_ratio = video_width / 1080.0
        base_font_size = int(float(raw_font_size) * 1.3 * scale_ratio)
    except (ValueError, TypeError):
        base_font_size = int(130 * (video_width / 1080.0))
        
    print(f"  [DEBUG] Preset4 Hook: BaseSize={base_font_size} (Raw={raw_font_size}, W={video_width})")
    
    # Calculate individual font sizes
    top_size_param = hook_styles.get('hook_top_font_size') or hook_styles.get('top_font_size')
    if top_size_param:
        l1_size = int(float(top_size_param) * 1.3 * scale_ratio)
    else:
        l1_size = int(base_font_size * 0.3)
    
    l2_size = base_font_size
    
    sub_size_param = hook_styles.get('hook_sub_font_size') or hook_styles.get('sub_font_size')
    if sub_size_param:
        l3_size = int(float(sub_size_param) * 1.3 * scale_ratio)
    else:
        l3_size = int(base_font_size * 0.4)
    
    stroke_width = hook_styles.get('stroke_width', 2)
    top_gap = hook_styles.get('top_gap', 15)
    bottom_gap = hook_styles.get('bottom_gap', 15)

    # RGB Conversion
    def hex_to_rgb(hex_str):
        hex_str = hex_str.lstrip('#')
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    
    heading_rgb = hex_to_rgb(heading_color_hex)
    white_rgb = hex_to_rgb(white_hex)
    stroke_rgb = hex_to_rgb(stroke_color_hex)
    
    # Font Loading Helper
    def load_font(name, size):
        try:
            path = get_font_path(name)
            print(f"  [DEBUG] Hook Font Request: '{name}' -> Resolved: '{path}'")
            
            if path and os.path.exists(path):
                return ImageFont.truetype(path, size)
                
            if path and not os.path.exists(path):
                try: 
                    return ImageFont.truetype(path, size)
                except: 
                    pass
                  
            # System fallbacks
            win_impact = "C:/Windows/Fonts/Impact.ttf"
            if os.path.exists(win_impact):
                return ImageFont.truetype(win_impact, size)
                  
            return ImageFont.truetype("Arial", size)
            
        except Exception as e:
            print(f"  [WARN] Font Load Failed ({name}): {e}. Using Default.")
            return ImageFont.load_default()

    # Canvas Setup
    padding_x = 60  # Increased padding for safety
    padding_y = 40
    box_radius = 20
    
    # Helper to draw text with stroke
    def draw_stroked_text(draw_obj, xy, text, font, text_color, stroke_rgb, stroke_w):
        x, y = xy
        if stroke_w > 0:
            for dx in range(-stroke_w, stroke_w + 1):
                for dy in range(-stroke_w, stroke_w + 1):
                    if dx != 0 or dy != 0:
                        draw_obj.text((x + dx, y + dy), text, font=font, fill=(*stroke_rgb, 255))
        draw_obj.text((x, y), text, font=font, fill=(*text_color, 255))
    
    # Text Processing Helper: Wrap text if it exceeds a certain width ratio
    def wrap_text_line(text, font, max_w):
        """Rudimentary wrapping based on approximate char width"""
        if not text: return [text]
        
        # Check total width first based on simpler test
        bbox = font.getbbox(text)
        if not bbox: return [text]
        
        total_w = bbox[2] - bbox[0]
        if total_w < max_w:
            return [text]
            
        # Needs wrapping
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = font.getbbox(test_line)
            w = bbox[2] - bbox[0]
            if w <= max_w:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                else:
                    lines.append(word) # Word itself is too long, force break
                    current_line = []
                    
        if current_line:
            lines.append(' '.join(current_line))
            
        return lines

    # Constraint constants
    max_box_width_limit = int(video_width * 0.90) 
    visual_max_w = max_box_width_limit - (padding_x * 2)

    # 1. Process text inputs (Wrap if necessary)
    processed_blocks = [] # List of {text, font_size_key, original_text}
    
    # Wrap Line 2 (Headline) primarily as it tends to be longest
    # We estimate wrapping width based on Base Font Size
    font_l2_base = load_font(font_name, l2_size)
    wrapped_l2 = wrap_text_line(line2_text.upper(), font_l2_base, visual_max_w * 1.5) 
    # * 1.5 because we can scale down later, we don't want to wrap too aggressively
    
    # Line 1 and 3 usually short, but let's wrap just in case
    font_l1_base = load_font(font_name, l1_size)
    wrapped_l1 = wrap_text_line(line1_text.upper(), font_l1_base, visual_max_w * 1.2)
    
    font_l3_base = load_font(font_name, l3_size)
    wrapped_l3 = wrap_text_line(line3_text, font_l3_base, visual_max_w * 1.2)

    # 2. Measure all blocks
    text_blocks = []
    
    def measure_text_block(text, font_obj):
        # Create temp canvas to render and measure
        # Use a wide canvas to prevent clipping of unwrapped/unscaled text
        temp_w, temp_h = int(video_width * 2.5), 1000
        temp_img = Image.new('RGBA', (temp_w, temp_h), (0, 0, 0, 0))
        temp_draw = ImageDraw.Draw(temp_img)
        
        origin_x, origin_y = 100, 100
        draw_stroked_text(temp_draw, (origin_x, origin_y), text, font_obj, white_rgb, stroke_rgb, stroke_width)
        
        bbox = temp_img.getbbox()
        if bbox:
            actual_w = bbox[2] - bbox[0]
            actual_h = bbox[3] - bbox[1]
            offset_x = bbox[0] - origin_x
            offset_y = bbox[1] - origin_y
            return {
                'text': text,
                'font': font_obj,
                'width': actual_w,
                'height': actual_h,
                'offset_x': offset_x,
                'offset_y': offset_y
            }
        return None

    # Add blocks in order
    for line in wrapped_l1:
        if line:
            block = measure_text_block(line, font_l1_base)
            if block: text_blocks.append(block)
            
    for line in wrapped_l2:
        if line:
            block = measure_text_block(line, font_l2_base)
            if block: text_blocks.append(block)
            
    for line in wrapped_l3:
        if line:
            block = measure_text_block(line, font_l3_base)
            if block: text_blocks.append(block)
    
    if not text_blocks:
        return None

    # Calculate total dimensions from text blocks
    max_text_width = max(block['width'] for block in text_blocks)
    
    # Calculate vertical spacing logic
    # We need to determine "where" we are (Top, Middle, Bottom) to apply correct gaps
    # Since we wrapped, we count indices
    
    l1_len = len([l for l in wrapped_l1 if l])
    l2_len = len([l for l in wrapped_l2 if l])
    l3_len = len([l for l in wrapped_l3 if l])
    
    # Retrieve line_spacing from config (default to 20 if not set, 10 was too tight)
    line_gap = hook_styles.get('line_spacing', 20) 
    
    # Respect user inputs directly but ensure defaults are safe
    # If user provides 0, we use defaults. If user provides value, we use it directly or with slight buffer.
    # The previous *2.0 multiplier might be confusing if user sets precise value.
    # Let's switch to additive safety or just trust the user if > 0.
    
    in_top_gap = hook_styles.get('top_gap', 0)
    in_bottom_gap = hook_styles.get('bottom_gap', 0)
    
    safe_top_gap = in_top_gap if in_top_gap > 0 else 30
    safe_bottom_gap = in_bottom_gap if in_bottom_gap > 0 else 25
    
    current_height_map = []
    current_y_offset = 0
    
    # Logic:
    # Top lines (between themselves): line_gap
    # Top -> Headline: safe_top_gap
    # Headline lines (between themselves): line_gap
    # Headline -> Subheading: safe_bottom_gap
    # Subheading lines (between themselves): line_gap
    
    block_idx = 0
    
    # 1. Top Lines
    for i in range(l1_len):
        block = text_blocks[block_idx]
        current_y_offset += block['height']
        block_idx += 1
        
        if i < l1_len - 1:
            current_y_offset += line_gap
        elif (l2_len > 0 or l3_len > 0): # Transition to next section
            current_y_offset += safe_top_gap

    # 2. Headline Lines
    for i in range(l2_len):
        block = text_blocks[block_idx]
        current_y_offset += block['height']
        block_idx += 1
        
        if i < l2_len - 1:
            current_y_offset += line_gap
        elif l3_len > 0: # Transition to next section
            current_y_offset += safe_bottom_gap

    # 3. Subheading Lines
    for i in range(l3_len):
        block = text_blocks[block_idx]
        current_y_offset += block['height']
        block_idx += 1
        if i < l3_len - 1:
            current_y_offset += line_gap
            
    total_text_height = current_y_offset
    
    # Calculate box dimensions
    box_width = int(max_text_width + padding_x * 2)
    box_height = int(total_text_height + padding_y * 2)
    
    content_scale = 1.0
    
    # Check if we need to scale down content to fit
    if box_width > max_box_width_limit:
        available_width = max_box_width_limit - (padding_x * 2)
        content_scale = available_width / max_text_width
        
        # Calculate scaled dimensions
        box_width = max_box_width_limit
        total_text_height = total_text_height * content_scale
        box_height = int(total_text_height + padding_y * 2)
        
        print(f"  [INFO] Text too wide ({max_text_width}px). Scaling by {content_scale:.2f} to fit {available_width}px.")

    # Define shadow constants
    shadow_offset = 8
    shadow_alpha = 60
    box_alpha = 230

    # Create final canvas
    # CRITICAL: box_width includes the visual box. The shadow adds width to the right.
    # To ensure the image is centered, we must add equal 'transparent' padding to the left.
    # Canvas Width = LeftPad + BoxWidth + RightShadowExt
    # LeftPad = shadow_offset
    # RightShadowExt = shadow_offset
    # Total W = box_width + shadow_offset * 2
    
    canvas_w = box_width + shadow_offset * 2
    canvas_h = box_height + shadow_offset * 2
    
    canvas = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    
    # Global offset ensures we have 'shadow_offset' padding on the left/top
    global_off_x = shadow_offset
    global_off_y = shadow_offset
    
    # Draw shadow (Shifted by shadow_offset relative to Box)
    draw.rounded_rectangle(
        (
            global_off_x + shadow_offset, 
            global_off_y + shadow_offset, 
            global_off_x + shadow_offset + box_width, 
            global_off_y + shadow_offset + box_height
        ),
        radius=box_radius,
        fill=(0, 0, 0, shadow_alpha)
    )
    
    # Draw main box (At Global Offset)
    draw.rounded_rectangle(
        (global_off_x, global_off_y, global_off_x + box_width, global_off_y + box_height),
        radius=box_radius,
        fill=(*heading_rgb, box_alpha)
    )

    # Re-define text layer variables (accidentally removed)
    text_content_w = int(max(1, max_text_width))
    text_content_h = int(max(1, current_y_offset)) # Original unscaled height
    layer_margin = 20
    text_layer = Image.new('RGBA', (text_content_w + layer_margin*2, text_content_h + layer_margin*2), (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(text_layer)
    
    current_y_text = 0
    block_idx = 0
    
    # Re-loop to draw using the same logic for spacing
    def draw_section(count, gap_after, intra_gap):
        nonlocal current_y_text, block_idx
        for i in range(count):
            block = text_blocks[block_idx]
            text = block['text']
            font = block['font']
            width = block['width']
            height = block['height']
            offset_x = block['offset_x']
            offset_y = block['offset_y']
            
            # Center horizontally
            visible_start_x = (text_content_w - width) // 2
            draw_x = visible_start_x - offset_x + layer_margin
            draw_y = current_y_text - offset_y + layer_margin
            
            draw_stroked_text(text_draw, (draw_x, draw_y), text, font, white_rgb, stroke_rgb, stroke_width)
            
            current_y_text += height
            block_idx += 1
            
            if i < count - 1:
                current_y_text += intra_gap
            elif gap_after > 0:
                current_y_text += gap_after

    draw_section(l1_len, safe_top_gap if (l2_len + l3_len) > 0 else 0, line_gap)
    draw_section(l2_len, safe_bottom_gap if l3_len > 0 else 0, line_gap)
    draw_section(l3_len, 0, line_gap)
    
    # If we need to scale
    if content_scale < 1.0:
        new_w = int((text_content_w + layer_margin*2) * content_scale)
        new_h = int((text_content_h + layer_margin*2) * content_scale)
        text_layer = text_layer.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)
    
    # Paste text layer onto main canvas
    # Center relative to the Box (which starts at global_off_x, global_off_y)
    layer_w, layer_h = text_layer.size
    paste_x = global_off_x + (box_width - layer_w) // 2
    paste_y = global_off_y + (box_height - layer_h) // 2
    
    canvas.paste(text_layer, (paste_x, paste_y), text_layer)
    
    # DO NOT CROP!
    # Cropping removes the transparent padding we just added for symmetry.
    final_img = canvas
    
    # Create Clip
    hook_clip = ImageClip(np.array(final_img)).with_duration(duration)
    
    # Position
    user_pos_percent = hook_styles.get('position', 80)
    try:
        user_pos_percent = float(user_pos_percent)
    except:
        user_pos_percent = 80.0
    
    pos_y = video_height * (user_pos_percent / 100.0)
    hook_clip = hook_clip.with_position(('center', pos_y))
    
    return hook_clip
