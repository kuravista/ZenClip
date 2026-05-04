"""
Routers module for ZenClip backend.

Each router handles a specific domain:
- health: Health check endpoints
- settings: User settings CRUD
- fonts: Font management
- processing: Video processing jobs
- transcript: Transcript review flow
- gallery: Video gallery management
- debug: Debug endpoints (gated by DEBUG_MODE)
"""
from .health import router as health_router
from .settings import router as settings_router
from .fonts import router as fonts_router
from .processing import router as processing_router
from .transcript import router as transcript_router
from .gallery import router as gallery_router
from .debug import router as debug_router

__all__ = [
    'health_router',
    'settings_router',
    'fonts_router',
    'processing_router',
    'transcript_router',
    'gallery_router',
    'debug_router',
]
