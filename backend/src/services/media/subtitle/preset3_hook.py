import os
import tempfile
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from services.media.subtitle.utils.fonts import get_font_path

def _render_preset3_hook(config, hook_styles, video_width, video_height, duration):
    """
    Render Preset 3 hook: Viral Stack.
    Line 1: BIG COLORED TEXT (e.g. VIRAL)
    Line 2: BIG WHITE TEXT (e.g. MARKETING)
    Line 3: Badge style (White text on Colored Box) (e.g. psychology)
    """
    
    # 1. Extract Settings
    # Map 'top_text' -> Line 1
    # Map 'headline' -> Line 2
    # Map 'subheading' -> Line 3
    line1_text = hook_styles.get('top_text', '').strip()
    line2_text = hook_styles.get('headline', '').strip()
    line3_text = hook_styles.get('subheading', '').strip()
    
    if not line1_text and not line2_text and not line3_text:
        return None

    # Colors
    # Heading Color controls the Blue parts (Line 1 text, Line 3 BG)
    highlight_color_hex = hook_styles.get('color', '#2F54EB') 
    white_hex = '#FFFFFF'
    stroke_color_hex = hook_styles.get('stroke_color', '#000000')
    
    # Support both 'hook_font_size' (frontend) and 'font_size' (internal)
    font_name = hook_styles.get('font', 'Impact')
    raw_font_size = hook_styles.get('hook_font_size') or hook_styles.get('font_size', 100)
    
    # CSS (Frontend) vs PIL (Backend) sizing discrepancy
    # Frontend Preview looks ~30% larger. Applying multiplier to align.
    # ALSO: Scaling relative to video width to support 4K etc.
    # Base Reference: 1080p
    try:
        scale_ratio = video_width / 1080.0
        # Multiplier matched to Frontend Preview (Preview.tsx uses 1.3x)
        # Previous "too small" was due to missing font. "Too big" was due to 2.5x/1.6x.
        # 1.3x is the mathematically correct value to match the visual preview.
        base_font_size = int(float(raw_font_size) * 1.3 * scale_ratio)
    except (ValueError, TypeError):
        base_font_size = int(130 * (video_width / 1080.0))
        
    print(f"  [DEBUG] Preset3 Hook: BaseSize={base_font_size} (Raw={raw_font_size}, W={video_width})")
    
    # Scale sizes
    # Line 1 & 2 use main font size
    # Line 1 (Top Text) - Specific Size
    top_size_param = hook_styles.get('hook_top_font_size') or hook_styles.get('top_font_size')
    if top_size_param:
        l1_size = int(float(top_size_param) * 1.3 * scale_ratio)
    else:
        l1_size = base_font_size

    # Line 2 (Headline) - Main Size
    l2_size = base_font_size
    # Line 3 is smaller badge
    # Support 'hook_sub_font_size'
    sub_size_param = hook_styles.get('hook_sub_font_size') or hook_styles.get('sub_font_size')
    if sub_size_param:
        l3_size = int(float(sub_size_param) * 1.3 * scale_ratio)
    else:
        l3_size = int(base_font_size * 0.4)
    
    stroke_width = hook_styles.get('stroke_width', 2)

    top_gap = hook_styles.get('top_gap', 10)
    bottom_gap = hook_styles.get('bottom_gap', 20)

    # RGB Conversion
    def hex_to_rgb(hex_str):
        hex_str = hex_str.lstrip('#')
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    
    highlight_rgb = hex_to_rgb(highlight_color_hex)
    white_rgb = hex_to_rgb(white_hex)
    stroke_rgb = hex_to_rgb(stroke_color_hex)
    
    # Font Loading Helper (Centralized)
    def load_font(name, size):
        try:
            # Use the robust centralized font manager
            # This handles 'Poppins' -> 'Poppins-Bold.ttf' mapping if cached,
            # checks static/fonts, fonts_custom, etc.
            path = get_font_path(name)
            
            print(f"  [DEBUG] Hook Font Request: '{name}' -> Resolved: '{path}'")
            
            if path and os.path.exists(path):
                return ImageFont.truetype(path, size)
                
            # If path returned is just a name like "Arial" (system fallback logic in get_font_path)
            if path and not os.path.exists(path):
                 # Try blind load (system font)
                 try: 
                     return ImageFont.truetype(path, size)
                 except: pass
                 
            # Fallback hard to Impact or Arial system
            # Try absolute path for Windows standard
            win_impact = "C:/Windows/Fonts/Impact.ttf"
            if os.path.exists(win_impact):
                 return ImageFont.truetype(win_impact, size)
                 
            return ImageFont.truetype("Arial", size)
            
        except Exception as e:
             print(f"  [WARN] Font Load Failed ({name}): {e}. Using Default.")
             return ImageFont.load_default()

    # Canvas Setup
    padding = 40
    # Create large canvas to draw components then crop/resize
    canvas_w = video_width
    canvas_h = int(video_height * 0.5) 
    
    canvas = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    
    current_y = padding
    
    # Helper to draw text with stroke
    def draw_stroked_text(draw_obj, xy, text, font, text_color, stroke_rgb, stroke_w):
        x, y = xy
        if stroke_w > 0:
            for dx in range(-stroke_w, stroke_w + 1):
                for dy in range(-stroke_w, stroke_w + 1):
                    if dx!=0 or dy!=0:
                        draw_obj.text((x+dx, y+dy), text, font=font, fill=(*stroke_rgb, 255))
        draw_obj.text((x, y), text, font=font, fill=(*text_color, 255))

    # --- AUTO-FIT LOGIC ---
    max_w = canvas_w - (padding * 2)
    min_size = 40
    
    # 1. Fit Line 1 (Top Text)
    font_l1 = None
    if line1_text:
        text = line1_text.upper()
        curr_size = l1_size
        while curr_size >= min_size:
            font_l1 = load_font(font_name, curr_size)
            bbox = draw.textbbox((0, 0), text, font=font_l1)
            if (bbox[2] - bbox[0]) <= max_w: break
            curr_size -= 5
        print(f"  [DEBUG] Line 1 Fit: {curr_size}px")
            
    # 2. Fit Line 2 (Headline)
    font_l2 = None
    if line2_text:
        text = line2_text.upper()
        curr_size = l2_size
        while curr_size >= min_size:
            font_l2 = load_font(font_name, curr_size)
            bbox = draw.textbbox((0, 0), text, font=font_l2)
            if (bbox[2] - bbox[0]) <= max_w: break
            curr_size -= 5
        print(f"  [DEBUG] Line 2 Fit: {curr_size}px")

    # --- DRAWING ---
    
    # Draw Line 1
    if line1_text and font_l1:
        text = line1_text.upper()
        bbox = draw.textbbox((0, 0), text, font=font_l1)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (canvas_w - w) // 2
        
        draw_stroked_text(draw, (x, current_y), text, font_l1, highlight_rgb, stroke_rgb, stroke_width)
        
        # Advance Y: Height + TopGap + Stroke Padding
        # Important: textbbox does NOT include stroke. We must add stroke_width to avoid overlap.
        current_y += h + top_gap + (stroke_width * 2)

    # Draw Line 2
    if line2_text and font_l2:
        text = line2_text.upper()
        bbox = draw.textbbox((0, 0), text, font=font_l2)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (canvas_w - w) // 2
        
        draw_stroked_text(draw, (x, current_y), text, font_l2, white_rgb, stroke_rgb, stroke_width)
        
        # Advance Y: Height + BottomGap + Stroke Padding
        # Increased gap to 60px (User feedback: Box background makes it look tight)
        current_y += h + 60 + (stroke_width * 2)

    # Draw Line 3 (Badge)
    font_badge = load_font(font_name, l3_size) 
    
    # --- LINE 3: psychology (Badge) ---
    if line3_text:
        text = line3_text 
        
        # Badge Padding (Increased for better fit)
        badge_pad_x = 10
        badge_pad_y = 8
        
        bbox = draw.textbbox((0, 0), text, font=font_badge)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        box_w = text_w + badge_pad_x * 2
        box_h = text_h + badge_pad_y * 2
        
        # Draw Box
        box_x = (canvas_w - box_w) // 2
        box_y = current_y
        
        # Sharp rectangle (no radius)
        draw.rectangle(
            (box_x, box_y, box_x + box_w, box_y + box_h),
            fill=(*highlight_rgb, 255)
        )
        
        # Draw Text (Centered in box using anchor 'mm' -> Middle Middle)
        center_x = box_x + box_w // 2
        center_y = box_y + box_h // 2
        # 'mm' anchor centers the text both horizontally and vertically at the given coordinate
        draw.text((center_x, center_y), text, font=font_badge, anchor='mm', fill=(*white_rgb, 255))
        
        current_y += box_h
        
    # Crop to content
    # Find actual bounding box of content
    bbox = canvas.getbbox()
    if bbox:
        # Add some padding to the crop so shadows/strokes aren't cut
        crop_box = (0, max(0, bbox[1]-10), canvas_w, min(canvas_h, bbox[3]+10))
        final_img = canvas.crop(crop_box)
    else:
        final_img = canvas # empty?
        
    # Save as PNG and return path + position for FFmpeg pipeline
    tmp_dir = tempfile.mkdtemp(prefix='zenclip_hook_')
    tmp_path = os.path.join(tmp_dir, 'hook_preset3.png')
    final_img.save(tmp_path, 'PNG')

    # Position
    user_pos_percent = hook_styles.get('position', 80)
    try:
        user_pos_percent = float(user_pos_percent)
    except:
        user_pos_percent = 80.0

    pos_y = int(video_height * (user_pos_percent / 100.0))

    return (tmp_path, ('center', pos_y))
