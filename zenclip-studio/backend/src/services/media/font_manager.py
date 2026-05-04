import threading
import os
import platform
from PIL import ImageFont
from services.media.subtitle.utils.fonts import get_font_path
from utils.logger import log

class FontManager:
    """Centralized font loading with caching"""
    
    _cache = {}
    _model_lock = threading.Lock()
    _font_dir = "static/fonts"
    
    # Map common font names to actual font files in static/fonts
    _font_mapping = {
        "Impact": "Montserrat-Black.otf",  # Use Montserrat Black as Impact replacement
        "Arial": "Montserrat-Regular.otf",
        "Arial-Bold": "Montserrat-Bold.otf",
        "Montserrat": "Montserrat-Regular.otf",
        "Poppins": "Poppins-Regular.otf",
        "Nokora": "Nokora-Regular.ttf",
    }
    
    _default_font_paths = [
        "Montserrat-Bold.otf",  # First fallback from static/fonts (bundled)
        "Poppins-Bold.ttf",     # Second fallback from static/fonts (bundled)
        # Windows system fonts
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        # macOS system fonts
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        # Linux system fonts
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    
    @classmethod
    def load_font(cls, font_name, font_size):
        """Load font with caching and intelligent fallback"""
        cache_key = f"{font_name}_{font_size}"
        
        with cls._model_lock:
            if cache_key in cls._cache:
                return cls._cache[cache_key]
            
            # Use centralized font path resolution
            font_path = get_font_path(font_name)
            
            font = None
            if font_path:
                try:
                    font = ImageFont.truetype(font_path, font_size)
                except Exception as e:
                    print(f"  [WARN] Failed to load font from path {font_path}: {e}")
            
            if font is not None:
                cls._cache[cache_key] = font
                return font
        
            # Last resort: PIL default font
            log.warn(f"All fonts failed for '{font_name}', using PIL default", module="FontManager")
            font = ImageFont.load_default()
            cls._cache[cache_key] = font
            return font

    @staticmethod
    def _try_load_font(font_path, font_size):
        """Try to load a single font"""
        try:
            # Check if file exists properly if it's a path
            if os.path.exists(font_path):
                 return ImageFont.truetype(font_path, font_size)
            # Otherwise try loading by name (system fonts)
            return ImageFont.truetype(font_path, font_size)
        except Exception:
            return None
