"""
Debug endpoints - gated by DEBUG_MODE environment variable.

WARNING: These endpoints expose sensitive information.
Only enable in development with CLIP_DEBUG=1.
"""
import os
import sys
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api", tags=["debug"])

# Debug mode gate
DEBUG_MODE = os.environ.get('CLIP_DEBUG', '0') == '1'


@router.get("/debug/config")
async def debug_config():
    """Debug endpoint to check backend configuration and paths."""
    if not DEBUG_MODE:
        raise HTTPException(
            status_code=403,
            detail="Debug endpoints disabled. Set CLIP_DEBUG=1 to enable."
        )

    # Import paths from app (these will be replaced with config imports)
    from app import UPLOAD_FOLDER, CLIPS_DIR, BACKGROUND_DIR, FONTS_DIR, STATIC_DIR

    return {
        "frozen": getattr(sys, 'frozen', False),
        "paths": {
            "upload_folder": UPLOAD_FOLDER,
            "clips_dir": CLIPS_DIR,
            "background_dir": BACKGROUND_DIR,
            "fonts_dir": FONTS_DIR,
            "static_dir": STATIC_DIR,
            "cwd": os.getcwd()
        },
        "exists": {
            "clips_dir": os.path.exists(CLIPS_DIR),
            "fonts_dir": os.path.exists(FONTS_DIR),
            "static_dir": os.path.exists(STATIC_DIR)
        },
        "contents": {
            "fonts_dir": os.listdir(FONTS_DIR) if os.path.exists(FONTS_DIR) else [],
            "static_fonts": os.listdir(os.path.join(STATIC_DIR, 'fonts')) if os.path.exists(os.path.join(STATIC_DIR, 'fonts')) else []
        }
    }
