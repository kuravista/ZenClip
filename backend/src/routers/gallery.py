"""
Gallery endpoints for video management.

Uses gallery_cache for optimized scanning.
"""
import os
import glob
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse

# Import gallery cache
from services.core.gallery_cache import gallery_cache

router = APIRouter(prefix="/api", tags=["gallery"])


def get_clips_dir() -> str:
    """Get clips directory with environment override support."""
    clips_dir = os.environ.get('CLIP_CLIPS_DIR')
    if clips_dir:
        return clips_dir

    app_data_dir = os.environ.get('CLIP_APP_DATA_DIR')
    if app_data_dir:
        return os.path.join(app_data_dir, 'clips')

    return 'clips'


def get_thumbnails_dir() -> str:
    """Get thumbnails directory."""
    thumbnails_dir = os.environ.get('CLIP_THUMBNAILS_DIR')
    if thumbnails_dir:
        return thumbnails_dir

    app_data_dir = os.environ.get('CLIP_APP_DATA_DIR')
    if app_data_dir:
        return os.path.join(app_data_dir, 'thumbnails')

    return 'thumbnails'


def scan_videos() -> List[dict]:
    """Scan clips directory for videos."""
    clips_dir = get_clips_dir()
    videos = []

    if not os.path.exists(clips_dir):
        return videos

    # Common video extensions
    video_extensions = ['*.mp4', '*.mov', '*.avi', '*.mkv', '*.webm']

    for ext in video_extensions:
        for filepath in glob.glob(os.path.join(clips_dir, '**', ext), recursive=True):
            if os.path.isfile(filepath):
                stat = os.stat(filepath)
                rel_path = os.path.relpath(filepath, clips_dir)
                videos.append({
                    "path": filepath,
                    "relative_path": rel_path,
                    "filename": os.path.basename(filepath),
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "thumbnail": get_thumbnail_path(filepath)
                })

    return videos


def get_thumbnail_path(video_path: str) -> Optional[str]:
    """Get thumbnail path for a video."""
    thumbnails_dir = get_thumbnails_dir()
    filename = os.path.basename(video_path)
    name_without_ext = os.path.splitext(filename)[0]
    thumbnail_path = os.path.join(thumbnails_dir, f"{name_without_ext}.jpg")

    if os.path.exists(thumbnail_path):
        return thumbnail_path
    return None


@router.get("/videos")
async def list_videos(refresh: bool = Query(False, description="Force refresh cache")):
    """Get list of all videos in gallery.

    Uses cache with TTL to avoid blocking scans.
    Set refresh=true to force cache invalidation.
    """
    clips_dir = get_clips_dir()

    # Check cache first
    if not refresh:
        cached = gallery_cache.get_videos(clips_dir)
        if cached:
            return {"videos": cached, "count": len(cached), "cached": True}

    # Scan if cache miss or refresh requested
    videos = scan_videos()

    # Update cache
    gallery_cache.update_videos(clips_dir, videos)

    return {"videos": videos, "count": len(videos), "cached": False}


@router.get("/video/{path:path}")
async def get_video(path: str):
    """Stream a specific video file."""
    clips_dir = os.path.realpath(get_clips_dir())
    video_path = os.path.realpath(os.path.join(clips_dir, path))

    # Security: ensure path is within clips_dir
    if not video_path.startswith(clips_dir):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video not found")

    return FileResponse(video_path)


@router.delete("/videos")
async def delete_videos(paths: List[str]):
    """Delete multiple videos."""
    clips_dir = os.path.realpath(get_clips_dir())
    deleted = []
    failed = []

    for path in paths:
        video_path = os.path.realpath(os.path.join(clips_dir, path))

        # Security check
        if not video_path.startswith(clips_dir):
            failed.append({"path": path, "reason": "Access denied"})
            continue

        if not os.path.exists(video_path):
            failed.append({"path": path, "reason": "Not found"})
            continue

        try:
            os.remove(video_path)
            deleted.append(path)
        except Exception as e:
            failed.append({"path": path, "reason": str(e)})

    # Invalidate cache after deletion
    if deleted:
        gallery_cache.invalidate(get_clips_dir())

    return {"deleted": deleted, "failed": failed}


@router.get("/thumbnails/{filename}")
async def get_thumbnail(filename: str):
    """Get a thumbnail image."""
    # Security: validate filename
    if '..' in filename or '/' in filename or '\\' in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    thumbnails_dir = os.path.realpath(get_thumbnails_dir())
    thumbnail_path = os.path.realpath(os.path.join(thumbnails_dir, filename))

    # Security: ensure path is within thumbnails_dir
    if not thumbnail_path.startswith(thumbnails_dir):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(thumbnail_path):
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    return FileResponse(thumbnail_path)


@router.get("/gallery/cache/stats")
async def get_cache_stats():
    """Get gallery cache statistics."""
    return gallery_cache.get_stats()


@router.post("/gallery/cache/clear")
async def clear_cache():
    """Clear gallery cache."""
    gallery_cache.clear_all()
    return {"status": "success", "message": "Cache cleared"}
