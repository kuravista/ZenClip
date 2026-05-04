"""
ZenClip Configuration Module

Centralizes all path configuration and environment variables.
This module provides a single source of truth for all runtime paths.

Environment Variables:
    CLIP_DEBUG          - Enable debug mode (default: 0)
    CLIP_SIDECAR_DIR    - Sidecar base directory
    CLIP_APP_DATA_DIR   - Override app data directory
    CLIP_BACKEND_PORT   - Backend server port (default: 9479)

    CLIP_STATIC_DIR     - Override static files directory
    CLIP_TEMPLATES_DIR  - Override templates directory
    CLIP_CLIPS_DIR      - Override clips output directory
    CLIP_FONTS_DIR      - Override fonts directory
    CLIP_BACKGROUND_DIR - Override backgrounds directory
    CLIP_THUMBNAILS_DIR - Override thumbnails directory
    CLIP_JOBS_DIR       - Override jobs data directory

    CLIP_FFMPEG_PATH    - Override FFmpeg binary path
    CLIP_CUDA_DIR       - CUDA DLLs directory
    CLIP_DLL_DIR        - Additional DLL search path
"""
import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class AppConfig:
    """Application configuration with environment-driven overrides."""

    # Runtime mode detection
    mode: str = field(default_factory=lambda: AppConfig._detect_mode())

    # Server configuration
    backend_port: int = field(default_factory=lambda: int(os.environ.get('CLIP_BACKEND_PORT', '9479')))
    debug_mode: bool = field(default_factory=lambda: os.environ.get('CLIP_DEBUG', '0') == '1')

    # Directory paths
    sidecar_dir: Optional[Path] = field(default_factory=lambda: AppConfig._get_sidecar_dir())
    app_data_dir: Path = field(default_factory=lambda: AppConfig._get_app_data_dir())

    # Static/template paths
    static_dir: Path = field(default_factory=lambda: AppConfig._get_path('CLIP_STATIC_DIR', 'static'))
    templates_dir: Path = field(default_factory=lambda: AppConfig._get_path('CLIP_TEMPLATES_DIR', 'templates'))

    # Output directories
    clips_dir: Path = field(default_factory=lambda: AppConfig._get_path('CLIP_CLIPS_DIR', None, 'clips'))
    fonts_dir: Path = field(default_factory=lambda: AppConfig._get_path('CLIP_FONTS_DIR', None, 'fonts'))
    background_dir: Path = field(default_factory=lambda: AppConfig._get_path('CLIP_BACKGROUND_DIR', None, 'backgrounds'))
    thumbnails_dir: Path = field(default_factory=lambda: AppConfig._get_path('CLIP_THUMBNAILS_DIR', None, 'thumbnails'))
    jobs_dir: Path = field(default_factory=lambda: AppConfig._get_path('CLIP_JOBS_DIR', None, 'jobs_data'))

    # Binary paths
    ffmpeg_path: Optional[Path] = field(default_factory=lambda: AppConfig._get_ffmpeg_path())
    cuda_dir: Optional[Path] = field(default_factory=lambda: AppConfig._get_cuda_dir())
    dll_dir: Optional[Path] = field(default_factory=lambda: AppConfig._get_optional_path('CLIP_DLL_DIR'))

    # Upload/download staging
    upload_folder: str = 'uploads'
    download_folder: str = 'downloads'

    # Allowed file extensions
    allowed_extensions: set = field(default_factory=lambda: {'mp4', 'mov', 'avi', 'mkv', 'webm'})

    @staticmethod
    def _detect_mode() -> str:
        """Detect runtime mode: frozen, sidecar, or dev."""
        if getattr(sys, 'frozen', False):
            return 'frozen'
        elif os.environ.get('CLIP_SIDECAR_DIR'):
            return 'sidecar'
        else:
            return 'dev'

    @staticmethod
    def _get_sidecar_dir() -> Optional[Path]:
        """Get sidecar directory from environment."""
        path = os.environ.get('CLIP_SIDECAR_DIR')
        return Path(path) if path else None

    @staticmethod
    def _get_app_data_dir() -> Path:
        """Get app data directory with fallback chain."""
        # 1. Explicit override
        if os.environ.get('CLIP_APP_DATA_DIR'):
            return Path(os.environ['CLIP_APP_DATA_DIR'])

        # 2. Default based on mode
        mode = AppConfig._detect_mode()
        if mode == 'frozen':
            # Production: Documents/SnipieAI
            documents = Path.home() / 'Documents' / 'SnipieAI'
        elif mode == 'sidecar':
            # Sidecar: relative to sidecar dir
            sidecar = os.environ.get('CLIP_SIDECAR_DIR', '')
            documents = Path(sidecar) / '..' / 'SnipieAI' if sidecar else Path.home() / 'Documents' / 'SnipieAI'
        else:
            # Dev: current directory
            documents = Path.cwd() / 'app-data'

        documents.mkdir(parents=True, exist_ok=True)
        return documents

    @staticmethod
    def _get_path(env_var: str, relative_default: Optional[str] = None,
                  app_data_subdir: Optional[str] = None) -> Path:
        """Get path with environment override support."""
        # 1. Explicit environment override
        if os.environ.get(env_var):
            return Path(os.environ[env_var])

        # 2. Relative to app data if specified
        if app_data_subdir:
            path = AppConfig._get_app_data_dir() / app_data_subdir
            path.mkdir(parents=True, exist_ok=True)
            return path

        # 3. Relative to sidecar or current directory
        sidecar = os.environ.get('CLIP_SIDECAR_DIR')
        if sidecar and relative_default:
            return Path(sidecar) / relative_default
        elif relative_default:
            return Path(relative_default)

        return Path.cwd()

    @staticmethod
    def _get_ffmpeg_path() -> Optional[Path]:
        """Get FFmpeg binary path with fallback chain."""
        # 1. Explicit override
        if os.environ.get('CLIP_FFMPEG_PATH'):
            return Path(os.environ['CLIP_FFMPEG_PATH'])

        # 2. Sidecar bundled FFmpeg
        sidecar = os.environ.get('CLIP_SIDECAR_DIR')
        if sidecar:
            ffmpeg_sidecar = Path(sidecar) / 'ffmpeg' / 'ffmpeg.exe'
            if ffmpeg_sidecar.exists():
                return ffmpeg_sidecar

        # 3. System FFmpeg (let imageio-ffmpeg handle it)
        return None

    @staticmethod
    def _get_cuda_dir() -> Optional[Path]:
        """Get CUDA directory."""
        # 1. Explicit CUDA override
        if os.environ.get('CLIP_CUDA_DIR'):
            return Path(os.environ['CLIP_CUDA_DIR'])

        # 2. Sidecar bundled CUDA
        sidecar = os.environ.get('CLIP_SIDECAR_DIR')
        if sidecar:
            cuda_dir = Path(sidecar) / 'cuda'
            if cuda_dir.exists():
                return cuda_dir

        return None

    @staticmethod
    def _get_optional_path(env_var: str) -> Optional[Path]:
        """Get optional path from environment."""
        path = os.environ.get(env_var)
        return Path(path) if path else None

    def ensure_directories(self) -> None:
        """Create all required directories."""
        dirs = [
            self.app_data_dir,
            self.clips_dir,
            self.fonts_dir,
            self.background_dir,
            self.thumbnails_dir,
            self.jobs_dir,
            Path(self.upload_folder),
            Path(self.download_folder),
        ]

        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def get_settings_file(self) -> Path:
        """Get settings file path."""
        return self.app_data_dir / 'user_settings.json'

    def get_cache_dir(self) -> Path:
        """Get cache directory path."""
        cache_dir = self.app_data_dir / 'cache'
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def get_logs_dir(self) -> Path:
        """Get logs directory path."""
        logs_dir = self.app_data_dir / 'logs'
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir

    def to_dict(self) -> dict:
        """Export configuration as dictionary for debugging."""
        return {
            'mode': self.mode,
            'backend_port': self.backend_port,
            'debug_mode': self.debug_mode,
            'sidecar_dir': str(self.sidecar_dir) if self.sidecar_dir else None,
            'app_data_dir': str(self.app_data_dir),
            'static_dir': str(self.static_dir),
            'templates_dir': str(self.templates_dir),
            'clips_dir': str(self.clips_dir),
            'fonts_dir': str(self.fonts_dir),
            'background_dir': str(self.background_dir),
            'thumbnails_dir': str(self.thumbnails_dir),
            'jobs_dir': str(self.jobs_dir),
            'ffmpeg_path': str(self.ffmpeg_path) if self.ffmpeg_path else None,
            'cuda_dir': str(self.cuda_dir) if self.cuda_dir else None,
        }


# Global configuration instance
config = AppConfig()


# Convenience exports for backward compatibility
def get_upload_folder() -> str:
    return config.upload_folder

def get_clips_dir() -> Path:
    return config.clips_dir

def get_static_dir() -> Path:
    return config.static_dir

def get_templates_dir() -> Path:
    return config.templates_dir

def get_fonts_dir() -> Path:
    return config.fonts_dir

def get_background_dir() -> Path:
    return config.background_dir

def get_thumbnails_dir() -> Path:
    return config.thumbnails_dir

def get_jobs_dir() -> Path:
    return config.jobs_dir

def get_settings_file() -> Path:
    return config.get_settings_file()

def get_cache_dir() -> Path:
    return config.get_cache_dir()

def get_logs_dir() -> Path:
    return config.get_logs_dir()

def get_ffmpeg_path() -> Optional[Path]:
    return config.ffmpeg_path

def is_debug_mode() -> bool:
    return config.debug_mode
