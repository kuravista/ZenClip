"""
Video processing endpoints.

Uses JobCommandPort (composition root) for job lifecycle + SQLite mirror.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from routers.deps import get_job_commands
from services.core.ports.context import JobRequestContext
from services.core.ports.protocols import JobCommandPort

router = APIRouter(prefix="", tags=["processing"])

TENANT_HEADER = "X-Tenant-Id"
USER_HEADER = "X-User-Id"


def _ctx_from_request(request: Request) -> Optional[JobRequestContext]:
    tid = request.headers.get(TENANT_HEADER)
    uid = request.headers.get(USER_HEADER)
    if tid or uid:
        return JobRequestContext(tenant_id=tid, user_id=uid)
    return None


@router.post("/process")
async def process_video(
    request: Request,
    video: UploadFile = File(...),
    aspect_ratio: str = Form("9:16"),
    subtitle_style: str = Form("shadow"),
    hook_style: str = Form("preset2"),
    add_subtitles: bool = Form(True),
    add_hook: bool = Form(True),
    add_watermark: bool = Form(False),
    commands: JobCommandPort = Depends(get_job_commands),
):
    """Process a video file."""
    upload_path = os.path.join("uploads", video.filename)
    os.makedirs("uploads", exist_ok=True)

    with open(upload_path, "wb") as f:
        f.write(await video.read())

    job_data = {
        "video_file": True,
        "filepath": upload_path,
        "video_path": upload_path,
        "aspect_ratio": aspect_ratio,
        "subtitle_style": subtitle_style,
        "hook_style": hook_style,
        "add_subtitles": add_subtitles,
        "add_hook": add_hook,
        "add_watermark": add_watermark,
    }

    ctx = _ctx_from_request(request)
    job_id = commands.submit_job(job_data, priority=5, ctx=ctx)

    if job_id:
        return {"status": "success", "job_id": job_id}
    raise HTTPException(status_code=500, detail="Failed to submit job")


@router.get("/status/{job_id}")
async def get_job_status(
    job_id: str,
    commands: JobCommandPort = Depends(get_job_commands),
):
    """Get job status and progress."""
    rec = commands.get_job_record(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return rec.to_status_api_dict()


@router.post("/cancel_job/{job_id}")
async def cancel_job(
    job_id: str,
    commands: JobCommandPort = Depends(get_job_commands),
):
    """Cancel a running job."""
    rec = commands.get_job_record(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    success = commands.cancel_job(job_id)
    if success:
        return {"status": "success", "message": "Job cancellation requested"}
    raise HTTPException(
        status_code=400,
        detail="Failed to cancel job (it might already be complete)",
    )


@router.get("/jobs")
async def list_jobs(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    commands: JobCommandPort = Depends(get_job_commands),
):
    """List all jobs with optional filtering."""
    return commands.list_jobs(status=status, limit=limit, offset=offset)


@router.get("/jobs/stats")
async def get_job_stats(commands: JobCommandPort = Depends(get_job_commands)):
    """Get job database statistics."""
    return commands.get_job_stats()


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str,
    commands: JobCommandPort = Depends(get_job_commands),
):
    """Delete a job and its artifacts."""
    deleted = commands.delete_job_record(job_id)
    if deleted:
        return {"status": "success", "message": f"Job {job_id} deleted"}
    raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
