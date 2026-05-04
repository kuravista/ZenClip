"""
Health check endpoints.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health():
    """Basic health check endpoint."""
    return {"status": "ok"}


@router.get("/api/health")
async def api_health():
    """API health check endpoint (alias)."""
    return {"status": "ok"}
