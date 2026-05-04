"""
YouTube preview endpoints.

Provides metadata extraction without downloading, so the frontend
can show title, duration, thumbnail, and quality options before
the user commits to downloading.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from services.media.yt_downloader import preview_metadata, YtDownloaderError, YtDownloader

router = APIRouter(prefix="", tags=["youtube"])


class YtPreviewRequest(BaseModel):
    url: str


@router.post("/api/yt-preview")
async def yt_preview(request: YtPreviewRequest):
    """Extract video metadata from a URL without downloading."""
    url = request.url.strip()
    if not url:
        return JSONResponse(status_code=400, content={"error": "URL is required"})

    try:
        meta = preview_metadata(url)
        return {"status": "success", "metadata": meta}
    except YtDownloaderError as e:
        return JSONResponse(
            status_code=422,
            content={"error": "Failed to extract video metadata", "details": str(e)},
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "Unexpected error", "details": str(e)},
        )


@router.get("/api/yt-supported")
async def yt_check_supported(url: str = ""):
    """Quick check if a URL looks downloadable."""
    return {"supported": YtDownloader.is_supported_url(url)}
