from PIL import Image, ImageDraw, ImageFilter, ImageFont
import numpy as np
from moviepy import ImageClip
import platform
from services.media.subtitle.utils.color import hex_to_rgb
from utils.logger import log

def create_rounded_rect_clip(size, color, radius):
    """Helper to create a rounded rectangle clip using PIL"""
    w, h = size
    
    # Create a transparent image
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Convert color to tuple if it's not already
    # Ensure color is RGB tuple
    if isinstance(color, str):
         # Basic color name mapping or hex support could be added here
         # but we typically expect tuples or hex strings which hex_to_rgb handles?
         # No, create_rounded_rect_clip caller typically passes tuple or compatible.
         # But let's be safe.
         pass
        
    # Draw rounded rectangle
    draw.rounded_rectangle([(0, 0), (w, h)], radius=radius, fill=color)
    
    # Convert to numpy array for MoviePy
    return ImageClip(np.array(img))

def apply_glow_effect(img, glow_color, glow_radius=12, glow_intensity=2):
    """
    Apply neon glow effect to a PIL RGBA image.
    
    Args:
        img: PIL RGBA image with transparent background
        glow_color: RGB tuple or hex string for glow color
        glow_radius: Blur radius for glow (higher = more spread)
        glow_intensity: Number of glow layers (1-3, higher = stronger)
    
    Returns:
        PIL RGBA image with glow effect applied
    """
    # Convert hex to RGB if needed
    if isinstance(glow_color, str):
        glow_color = hex_to_rgb(glow_color)
    
    # Create glow layer from alpha channel
    alpha = img.split()[3]
    
    # Create solid color image with same alpha
    glow_layer = Image.new('RGBA', img.size, (*glow_color, 255))
    glow_layer.putalpha(alpha)
    
    # Blur the glow layer
    glow_blurred = glow_layer.filter(ImageFilter.GaussianBlur(radius=glow_radius))
    
    # Create result canvas
    result = Image.new('RGBA', img.size, (0, 0, 0, 0))
    
    # Stack multiple glow layers for intensity
    for _ in range(glow_intensity):
        result = Image.alpha_composite(result, glow_blurred)
    
    # Add original text on top
    result = Image.alpha_composite(result, img)
    
    return result

def create_emoji_clip(emoji_char, size=100):
    """
    Create a clip containing an emoji rendered as an image.
    Uses PIL to render text, which works for system emoji fonts.
    """
    try:
        # Create a transparent image
        # Emojis are roughly square
        img_size = int(size * 1.5) # Buffer
        img = Image.new('RGBA', (img_size, img_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Font selection for Emojis
        system = platform.system()
        
        emoji_font = None
        font_size = int(size)
        
        try:
            if system == "Darwin": # macOS
                try:
                    emoji_font = ImageFont.truetype("/System/Library/Fonts/Apple Color Emoji.ttc", font_size)
                except:
                    try:
                        emoji_font = ImageFont.truetype("/System/Library/Fonts/Apple Color Emoji.ttc", font_size, index=0)
                    except:
                        emoji_font = ImageFont.truetype("Apple Color Emoji", font_size)

            elif system == "Windows":
                # Try absolute path first (reliable), then loose name as fallback
                win_emoji_paths = [
                    r"C:\Windows\Fonts\seguiemj.ttf",  # Segoe UI Emoji (Win 10+)
                    r"C:\Windows\Fonts\seguisym.ttf",  # Segoe UI Symbol (fallback)
                ]
                for ep in win_emoji_paths:
                    try:
                        import os as _os
                        if _os.path.exists(ep):
                            emoji_font = ImageFont.truetype(ep, font_size)
                            break
                    except:
                        continue
                if emoji_font is None:
                    emoji_font = ImageFont.truetype("seguiemj.ttf", font_size)
            else:  # Linux
                emoji_font = ImageFont.truetype("NotoColorEmoji.ttf", font_size)
        except Exception as e:
            emoji_font = ImageFont.load_default()

        if emoji_font is None:
            log.warn("Emoji font is None, using PIL default", module="Image")
            emoji_font = ImageFont.load_default()

        # Center text
        # draw.text((x, y), ...)
        # We use sb feature of PIL 10+ if available, else simple
        try:
             draw.text((img_size/2, img_size/2), emoji_char, font=emoji_font, fill="white", anchor="mm", embedded_color=True)
        except:
             # Fallback for older PIL/Pillow versions
             w, h = draw.textsize(emoji_char, font=emoji_font)
             draw.text(((img_size-w)/2, (img_size-h)/2), emoji_char, font=emoji_font, fill="white")
        
        # Convert to MoviePy ImageClip
        return ImageClip(np.array(img))
        
    except Exception as e:
        log.error(f"Error creating emoji clip: {e}", module="Image")
        return None
