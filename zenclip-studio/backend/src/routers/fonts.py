"""
Font management endpoints.
"""
import os
import shutil
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from typing import List, Optional

router = APIRouter(prefix="/api", tags=["fonts"])

# Font directory - will be replaced with config
def get_fonts_dir() -> str:
    """Get fonts directory with environment override support."""
    fonts_dir = os.environ.get('CLIP_FONTS_DIR')
    if fonts_dir:
        return fonts_dir

    app_data_dir = os.environ.get('CLIP_APP_DATA_DIR')
    if app_data_dir:
        return os.path.join(app_data_dir, 'fonts')

    return 'fonts'


def get_legacy_fonts_dir() -> Optional[str]:
    """Get legacy fonts directory for backward compatibility."""
    return os.environ.get('CLIP_LEGACY_FONTS_DIR')


def get_allowed_font_extensions() -> set:
    """Get allowed font file extensions."""
    return {'.ttf', '.otf', '.woff', '.woff2'}


def scan_fonts() -> List[dict]:
    """Scan fonts directory and return list of available fonts."""
    fonts_dir = get_fonts_dir()
    fonts = []

    if not os.path.exists(fonts_dir):
        return fonts

    for filename in os.listdir(fonts_dir):
        filepath = os.path.join(fonts_dir, filename)
        if os.path.isfile(filepath):
            ext = os.path.splitext(filename)[1].lower()
            if ext in get_allowed_font_extensions():
                fonts.append({
                    "name": os.path.splitext(filename)[0],
                    "filename": filename,
                    "path": filepath,
                    "extension": ext
                })

    return fonts


@router.get("/fonts")
async def list_fonts():
    """Get list of available fonts."""
    fonts = scan_fonts()
    return {"fonts": fonts}


@router.post("/fonts/upload")
async def upload_font(file: UploadFile = File(...)):
    """Upload a new font file."""
    fonts_dir = get_fonts_dir()
    os.makedirs(fonts_dir, exist_ok=True)

    # Validate extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in get_allowed_font_extensions():
        raise HTTPException(
            status_code=400,
            detail=f"Invalid font format. Allowed: {get_allowed_font_extensions()}"
        )

    # Secure filename
    from werkzeug.utils import secure_filename
    safe_filename = secure_filename(file.filename)
    filepath = os.path.join(fonts_dir, safe_filename)

    # Save file
    content = await file.read()
    with open(filepath, 'wb') as f:
        f.write(content)

    return {"status": "success", "filename": safe_filename}


@router.delete("/fonts/{filename}")
async def delete_font(filename: str):
    """Delete a font file."""
    # Security: validate filename
    if '..' in filename or '/' in filename or '\\' in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    fonts_dir = os.path.realpath(get_fonts_dir())
    filepath = os.path.realpath(os.path.join(fonts_dir, filename))

    # Security: ensure path is within fonts_dir
    if not filepath.startswith(fonts_dir):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Font not found")

    os.remove(filepath)
    return {"status": "success", "message": f"Font {filename} deleted"}


@router.get("/fonts/{filename}")
async def get_font(filename: str):
    """Download a font file."""
    # Security: validate filename
    if '..' in filename or '/' in filename or '\\' in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    fonts_dir = os.path.realpath(get_fonts_dir())
    filepath = os.path.realpath(os.path.join(fonts_dir, filename))

    # Security: ensure path is within fonts_dir
    if not filepath.startswith(fonts_dir):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Font not found")

    return FileResponse(filepath)
