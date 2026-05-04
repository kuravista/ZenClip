import os
import sys
import warnings
# Suppress urllib3 NotOpenSSLWarning — must be set BEFORE importing requests
# (binary_manager is imported first, so this is the correct place)
warnings.filterwarnings("ignore", message=".*NotOpenSSLWarning.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="urllib3")

import shutil
import platform
import subprocess
import requests
import tarfile
import stat
import imageio_ffmpeg

from utils.logger import log

# Configure paths
# In frozen mode: sys._MEIPASS/bin or AppData location?
# We want to download to a writable location, usually AppData (Documents/SnipieAI/bin)

def _get_default_app_data_dir():
    override_app_data_dir = os.environ.get('CLIP_APP_DATA_DIR')
    if override_app_data_dir:
        return override_app_data_dir

    default_app_data_dir = os.environ.get('CLIP_DEFAULT_APP_DATA_DIR')
    if default_app_data_dir:
        return default_app_data_dir

    user_home = os.path.expanduser("~")
    return os.path.join(user_home, 'Documents', 'SnipieAI')

def _get_bundled_ffmpeg():
    """Get bundled ffmpeg path safely (avoid circular import by lazy-importing)"""
    explicit_ffmpeg = os.environ.get('CLIP_FFMPEG_PATH')
    if explicit_ffmpeg and os.path.exists(explicit_ffmpeg):
        return explicit_ffmpeg
    try:
        sidecar_dir = os.environ.get('CLIP_SIDECAR_DIR')
        if sidecar_dir:
            bin_name = 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'
            return os.path.join(sidecar_dir, 'ffmpeg', bin_name)
    except Exception:
        pass
    return 'ffmpeg'  # last-resort system fallback


def check_amd_gpu():
    """Check for AMD GPU with AMF support using bundled FFmpeg"""
    try:
        import subprocess
        ffmpeg_exe = _get_bundled_ffmpeg()
        result = subprocess.run([ffmpeg_exe, '-encoders'], capture_output=True, text=True)
        return 'h264_amf' in result.stdout
    except:
        return False

def get_app_data_dir():
    """Get the persistent app data directory"""
    if getattr(sys, 'frozen', False):
        return _get_default_app_data_dir()
    else:
        if os.environ.get('CLIP_APP_DATA_DIR'):
            return os.environ['CLIP_APP_DATA_DIR']
        if os.environ.get('CLIP_DEFAULT_APP_DATA_DIR'):
            return os.environ['CLIP_DEFAULT_APP_DATA_DIR']
        # Dev mode: use project root/bin
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return base_dir

BIN_DIR = os.path.join(get_app_data_dir(), 'bin')
os.makedirs(BIN_DIR, exist_ok=True)

def get_ffmpeg_path():
    """Get the path to the bundled FFmpeg binary"""
    explicit_ffmpeg = os.environ.get('CLIP_FFMPEG_PATH')
    if explicit_ffmpeg and os.path.exists(explicit_ffmpeg):
        log.success(f"Using overridden FFmpeg at: {explicit_ffmpeg}", module="BinaryManager")
        return explicit_ffmpeg

    # 1. Check if running in frozen mode (PyInstaller)
    # 1. Sidecar Logic (Preferred)
    sidecar_dir = os.environ.get('CLIP_SIDECAR_DIR')
    if sidecar_dir:
        # Prod/Sidecar Path
        bin_name = 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'
        sidecar_ffmpeg = os.path.join(sidecar_dir, 'ffmpeg', bin_name)
        
        if os.path.exists(sidecar_ffmpeg):
            log.success(f"Found sidecar FFmpeg at: {sidecar_ffmpeg}", module="BinaryManager")
            try:
                st = os.stat(sidecar_ffmpeg)
                os.chmod(sidecar_ffmpeg, st.st_mode | stat.S_IEXEC)
            except: pass
            return sidecar_ffmpeg

    # 2. Check if running in frozen mode (Legacy PyInstaller support, just in case)
    if getattr(sys, 'frozen', False):
        pass 

    # 3. Fallback to imageio_ffmpeg (Dev mode ONLY)
    try:
        path = imageio_ffmpeg.get_ffmpeg_exe()
        log.success(f"FFmpeg (imageio) found at: {path}", module="BinaryManager")
        return path
    except Exception as e:
        log.error(f"Failed to get FFmpeg path: {e}", module="BinaryManager")
        return "ffmpeg" # Fallback to system path


def setup_environment():
    """Configure environment variables for dependencies"""
    log.info("Setting up binary environment", module="BinaryManager")

    # 1. Setup FFmpeg
    ffmpeg_path = get_ffmpeg_path()
    os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg_path
    
    # 2. ImageMagick is no longer required for main pipeline (using FFmpeg ASS + PIL)
    # If legacy code (MoviePy TextClip) is used, it might fail, but we assume it's clean.

# Run setup on import
setup_environment()
