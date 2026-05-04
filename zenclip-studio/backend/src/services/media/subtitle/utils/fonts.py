"""
Centralized font management - utils/fonts.py
"""
import os
import sys
import glob
from pathlib import Path
from utils.logger import log

class FontManager:
    """Singleton font manager"""
    _instance = None
    _fonts_cache = None
    _font_dirs = []
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize_fonts()
        return cls._instance
    
    def _initialize_fonts(self):
        """Scan fonts directory once"""
        self._font_dirs = []
        
        # 1. Check strict PyInstaller path
        default_app_data_dir = os.environ.get('CLIP_DEFAULT_APP_DATA_DIR')
        has_override_font_sources = bool(
            os.environ.get('CLIP_FONTS_DIR') or
            os.environ.get('CLIP_STATIC_DIR') or
            os.environ.get('CLIP_APP_DATA_DIR') or
            default_app_data_dir
        )
        if getattr(sys, 'frozen', False):
            bundle_dir = sys._MEIPASS
            self._font_dirs.append(Path(bundle_dir) / 'static' / 'fonts')
        
        # 1. Standard Prod Check: sys.frozen
        if getattr(sys, 'frozen', False):
            # PyInstaller creates a temp folder in _MEIPASS
            base_dir = Path(sys._MEIPASS)
            
            # Critical paths for frozen app
            prod_paths = [
                base_dir / 'static' / 'fonts',
                base_dir / 'Backend' / 'static' / 'fonts', # In case structure is preserved
                base_dir / 'backend_sidecar' / 'static' / 'fonts',
                Path(sys.executable).parent / 'static' / 'fonts' # Next to EXE
            ]
            
            if not has_override_font_sources:
                for p in prod_paths:
                    if p.exists() and p not in self._font_dirs:
                        self._font_dirs.append(p)
            
            # Also scan user custom fonts directory (writable, from Documents/SnipieAI/fonts)
            user_custom_fonts_root = Path(default_app_data_dir) if default_app_data_dir else (Path.home() / 'Documents' / 'SnipieAI')
            user_custom_fonts = user_custom_fonts_root / 'fonts'
            if user_custom_fonts.exists() and user_custom_fonts not in self._font_dirs:
                self._font_dirs.append(user_custom_fonts)

        # 1.5 Sidecar Check (Prod but not frozen)
        sidecar_dir = os.environ.get('CLIP_SIDECAR_DIR')
        override_static_dir = os.environ.get('CLIP_STATIC_DIR')
        override_fonts_dir = os.environ.get('CLIP_FONTS_DIR')
        override_app_data_dir = os.environ.get('CLIP_APP_DATA_DIR')
        if override_fonts_dir:
            override_fonts_path = Path(override_fonts_dir)
            if override_fonts_path.exists() and override_fonts_path not in self._font_dirs:
                self._font_dirs.append(override_fonts_path)
        if override_static_dir:
            override_static_fonts = Path(override_static_dir) / 'fonts'
            if override_static_fonts.exists() and override_static_fonts not in self._font_dirs:
                self._font_dirs.append(override_static_fonts)
        if sidecar_dir and not has_override_font_sources:
            sidecar_path = Path(sidecar_dir)
            sidecar_paths = [
                sidecar_path / 'static' / 'fonts',
                sidecar_path / 'src' / 'static' / 'fonts', 
            ]
            for p in sidecar_paths:
                 if p.exists() and p not in self._font_dirs:
                    self._font_dirs.append(p)
            
            # Also scan user custom fonts directory (writable, from Documents/SnipieAI/fonts)
            user_custom_fonts_root = Path(override_app_data_dir) if override_app_data_dir else (Path(default_app_data_dir) if default_app_data_dir else (Path.home() / 'Documents' / 'SnipieAI'))
            user_custom_fonts = user_custom_fonts_root / 'fonts'
            if user_custom_fonts.exists() and user_custom_fonts not in self._font_dirs:
                self._font_dirs.append(user_custom_fonts)

        # 2. Check Development paths
        current_file = Path(__file__).resolve()
        
        # Robust search for static/fonts
        # Structure: .../Backend/src/services/media/subtitle/utils/fonts.py
        # Target:    .../Backend/static/fonts
        
        potential_roots = [
            current_file.parents[5], # Backend/
            current_file.parents[4], # src/ (just in case)
            Path.cwd(),
            Path.cwd() / 'Backend'
        ]
        
        for root in potential_roots:
            # Check static/fonts
            p1 = root / 'static' / 'fonts'
            if p1.exists() and p1 not in self._font_dirs:
                self._font_dirs.append(p1)
                
            # Check fonts/ (root level)
            p2 = root / 'fonts'
            if p2.exists() and p2 not in self._font_dirs:
                self._font_dirs.append(p2)
                
        # Also check hardcoded relative path from this file as backup
        # .../Backend/src/services/media/subtitle/utils/fonts.py -> .../Backend/static/fonts
        # parents[5] is 'Backend'
        direct_backend_static = current_file.parents[5] / 'static' / 'fonts'
        if direct_backend_static.exists() and direct_backend_static not in self._font_dirs:
            self._font_dirs.append(direct_backend_static)
        
        self._fonts_cache = {}
        
        found_fonts = False
        for fonts_dir in self._font_dirs:
            if not fonts_dir.exists():
                continue
            
            found_fonts = True
            # Scan all font files
            for ext in ['*.ttf', '*.otf', '*.TTF', '*.OTF']:
                for font_path in fonts_dir.glob(ext):
                    name_stem = font_path.stem  # Filename without extension
                    name_full = font_path.name   # Filename with extension
                    
                    # Store multiple keys for flexibility
                    # 1. Exact stem check ("Poppins-Bold")
                    if name_stem not in self._fonts_cache:
                        self._fonts_cache[name_stem] = str(font_path)
                    
                    # 2. Exact filename check ("Poppins-Bold.ttf")
                    if name_full not in self._fonts_cache:
                        self._fonts_cache[name_full] = str(font_path)
                    
                    # 3. Lowercase check
                    self._fonts_cache[name_stem.lower()] = str(font_path)
                    self._fonts_cache[name_full.lower()] = str(font_path)
                    
                    # 4. Normalized check (spaces to hyphens)
                    # "Poppins Bold" -> "Poppins-Bold"
                    normalized = name_stem.replace(' ', '-')
                    if normalized != name_stem:
                         if normalized not in self._fonts_cache:
                            self._fonts_cache[normalized] = str(font_path)
                         self._fonts_cache[normalized.lower()] = str(font_path)

        if found_fonts:
            log.success(f"Font Manager: loaded {len(self._fonts_cache)} keys from {len([d for d in self._font_dirs if d.exists()])} dir(s)", module="FontManager")
        else:
            log.warn(f"Font Manager: no font directories found. Checked: {[str(d) for d in self._font_dirs]}", module="FontManager")
            
    def get_font_path(self, font_name, fallbacks=None):
        """
        Get font path with smart fallback chain.
        """
        # print(f"  [DEBUG] FontManager lookup: '{font_name}'")
        if not font_name:
            return self._get_fallback(fallbacks)

        # 0. Check if absolute path
        if os.path.isabs(font_name) and os.path.exists(font_name):
            return font_name

        # 1. Try exact match
        if font_name in self._fonts_cache:
            return self._fonts_cache[font_name]
        
        # 2. Try with common extensions
        for ext in ['.ttf', '.otf']:
            if f"{font_name}{ext}" in self._fonts_cache:
                return self._fonts_cache[f"{font_name}{ext}"]
        
        # 3. Try case-insensitive
        if font_name.lower() in self._fonts_cache:
            return self._fonts_cache[font_name.lower()]
            
        # 4. Try normalized (spaces -> dashes)
        normalized = font_name.replace(' ', '-')
        if normalized in self._fonts_cache:
            return self._fonts_cache[normalized]
        if normalized.lower() in self._fonts_cache:
             return self._fonts_cache[normalized.lower()]

        # 5. Try fallbacks
        log.debug(f"Font '{font_name}' not found in cache, trying fallbacks", module="FontManager")
        return self._get_fallback(fallbacks)

    def _get_fallback(self, fallbacks):
        if fallbacks is None:
            fallbacks = ["Montserrat-Bold", "Poppins-Bold", "Arial-Bold", "Arial"]
            
        for fb in fallbacks:
            if fb in self._fonts_cache:
                log.debug(f"Using fallback font: {fb}", module="FontManager")
                return self._fonts_cache[fb]
            if fb.lower() in self._fonts_cache:
                log.debug(f"Using fallback font: {fb} (matched lower)", module="FontManager")
                return self._fonts_cache[fb.lower()]
        
        # Last resort: try system fonts by platform
        import platform
        system = platform.system()
        system_fallbacks = []
        if system == "Windows":
            system_fallbacks = [
                r"C:\Windows\Fonts\arial.ttf",
                r"C:\Windows\Fonts\calibri.ttf",
                r"C:\Windows\Fonts\segoeui.ttf",
            ]
        elif system == "Darwin":
            system_fallbacks = [
                "/System/Library/Fonts/Helvetica.ttc",
                "/System/Library/Fonts/Supplemental/Arial.ttf",
            ]
        else:  # Linux
            system_fallbacks = [
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            ]
        
        for sys_font in system_fallbacks:
            if os.path.exists(sys_font):
                log.debug(f"Using system font fallback: {sys_font}", module="FontManager")
                return sys_font
        
        # Absolute last resort: let MoviePy/PIL use system font by name
        log.warn("No custom or system font found, falling back to 'Arial'", module="FontManager")
        return "Arial"

# Global instance
_font_manager = FontManager()

def get_font_path(font_name, fallbacks=None):
    """Convenience function"""
    return _font_manager.get_font_path(font_name, fallbacks)
