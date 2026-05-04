"""
Video processing endpoints.

Uses job_database for persistent job metadata.
"""
import os
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import Optional, List

# Import job manager and database
from services.core.job_manager import job_manager
from services.core.job_database import job_database

router = APIRouter(prefix="", tags=["processing"])


@router.post("/process")
async def process_video(
    video: UploadFile = File(...),
    aspect_ratio: str = Form("9:16"),
    subtitle_style: str = Form("shadow"),
    hook_style: str = Form("preset2"),
    add_subtitles: bool = Form(True),
    add_hook: bool = Form(True),
    add_watermark: bool = Form(False),
):
    """Process a video file."""
    # Save uploaded file
    upload_path = os.path.join('uploads', video.filename)
    os.makedirs('uploads', exist_ok=True)

    with open(upload_path, 'wb') as f:
        f.write(await video.read())

    # Prepare job data
    job_data = {
        'video_path': upload_path,
        'aspect_ratio': aspect_ratio,
        'subtitle_style': subtitle_style,
        'hook_style': hook_style,
        'add_subtitles': add_subtitles,
        'add_hook': add_hook,
        'add_watermark': add_watermark,
    }

    # Submit job to manager
    job_id = job_manager.submit_job(job_data)

    if job_id:
        # Also save to database for persistence
        try:
            job_database.create_job(job_id, job_data)
        except Exception as e:
            pass  # Database is optional fallback

        return {"status": "success", "job_id": job_id}
    else:
        raise HTTPException(status_code=500, detail="Failed to submit job")


@router.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """Get job status and progress."""
    # Try memory first
    job = job_manager.get_job(job_id)

    # Fallback to database
    if not job:
        job = job_database.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return {
        "job_id": job_id,
        "status": job.get('status', 'unknown'),
        "progress": job.get('progress', 0),
        "message": job.get('message', ''),
    }


@router.post("/cancel_job/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a running job."""
    from services.core.job_manager import job_manager

    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    success = job_manager.cancel_job(job_id)
    if success:
        # Update database status
        job_database.update_job_status(job_id, 'cancelled')
        return {"status": "success", "message": "Job cancellation requested"}
    else:
        raise HTTPException(
            status_code=400,
            detail="Failed to cancel job (it might already be complete)"
        )


@router.get("/jobs")
async def list_jobs(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """List all jobs with optional filtering."""
    jobs = job_database.list_jobs(status=status, limit=limit, offset=offset)
    return {
        "jobs": jobs,
        "count": len(jobs),
        "filters": {"status": status, "limit": limit, "offset": offset}
    }


@router.get("/jobs/stats")
async def get_job_stats():
    """Get job database statistics."""
    return job_database.get_stats()


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job and its artifacts."""
    # Cancel if running
    if job_manager.get_job(job_id):
        job_manager.cancel_job(job_id)

    # Delete from database
    deleted = job_database.delete_job(job_id)

    if deleted:
        return {"status": "success", "message": f"Job {job_id} deleted"}
    else:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
