"""
Settings endpoints for user preferences and API keys.
"""
import os
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any

router = APIRouter(prefix="/api", tags=["settings"])

# These will be replaced with config imports
SETTINGS_FILE = os.environ.get('CLIP_SETTINGS_FILE', 'user_settings.json')

DEBUG_MODE = os.environ.get('CLIP_DEBUG', '0') == '1'


class SettingsUpdate(BaseModel):
    """Model for settings update."""
    pass  # Flexible - accepts any key-value pairs


def get_settings_file_path() -> str:
    """Get settings file path with environment override support."""
    app_data_dir = os.environ.get('CLIP_APP_DATA_DIR')
    if app_data_dir:
        return os.path.join(app_data_dir, 'user_settings.json')
    return SETTINGS_FILE


def read_settings() -> dict:
    """Read settings from file."""
    settings_path = get_settings_file_path()
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def write_settings(settings: dict) -> None:
    """Write settings to file atomically."""
    settings_path = get_settings_file_path()

    # Ensure directory exists
    os.makedirs(os.path.dirname(settings_path) if os.path.dirname(settings_path) else '.', exist_ok=True)

    # Atomic write via temp file
    temp_path = settings_path + ".tmp"
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    os.replace(temp_path, settings_path)


@router.get("/settings")
async def get_settings():
    """Get current user settings."""
    settings = read_settings()
    return settings


@router.put("/settings")
@router.post("/settings")
async def update_settings(settings: Dict[str, Any]):
    """Update user settings (merge with existing)."""
    existing = read_settings()
    updated = {**existing, **settings}
    write_settings(updated)
    return {"status": "success", "settings": updated}


@router.post("/settings/reset")
async def reset_settings():
    """Reset settings to defaults."""
    default_settings = {
        "aspectRatio": "9:16",
        "subtitleStyle": "shadow",
        "addSubtitles": True,
        "addHook": True,
        "addWatermark": False,
    }
    write_settings(default_settings)
    return {"status": "success", "settings": default_settings}


@router.get("/settings/debug")
async def debug_settings():
    """Diagnostic endpoint to troubleshoot settings persistence."""
    if not DEBUG_MODE:
        raise HTTPException(
            status_code=403,
            detail="Debug endpoints disabled. Set CLIP_DEBUG=1 to enable."
        )

    import stat
    from datetime import datetime

    settings_path = get_settings_file_path()
    debug_info = {
        "settings_file_path": settings_path,
        "file_exists": os.path.exists(settings_path),
        "debug_mode": DEBUG_MODE,
    }

    if os.path.exists(settings_path):
        file_stat = os.stat(settings_path)
        debug_info["file_size"] = file_stat.st_size
        debug_info["last_modified"] = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
        debug_info["permissions"] = oct(stat.S_IMODE(file_stat.st_mode))

        try:
            with open(settings_path, 'r') as f:
                contents = json.load(f)
            debug_info["num_keys"] = len(contents)
            debug_info["keys"] = list(contents.keys())
            debug_info["contents_preview"] = {
                k: str(v)[:50] for k, v in list(contents.items())[:5]
            }
        except Exception as read_err:
            debug_info["read_error"] = str(read_err)

    return debug_info
