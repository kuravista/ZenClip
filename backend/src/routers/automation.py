from __future__ import annotations

import os
import json
import time
import asyncio
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

import httpx
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse

from services.automation.models import (
    ClipRequest, SubmitResponse, JobStatusResponse,
    ClipResult, ClipDetail, JobListItem, JobListResponse,
    AutomationLogEntry, ErrorResponse, WebhookPayload,
)
from services.automation.pipeline_bridge import PipelineBridge
from services.automation.log_collector import LogCollector
from services.automation.r2_uploader import upload_job_clips
from services.core.job_manager import job_manager, JobStatus
from services.core.job_database import job_database


router = APIRouter(tags=["automation"])  # Prefix "/api/v1" added at registration time


def _get_jobs_dir() -> str:
    """Get jobs directory from the singleton JobManager to avoid path divergence."""
    return getattr(job_manager, 'jobs_dir', os.environ.get("CLIP_JOBS_DIR", "jobs_data"))


def _read_metadata(job_id: str) -> Optional[dict]:
    """Read metadata.json for a job."""
    path = os.path.join(_get_jobs_dir(), job_id, "metadata.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _read_clips_result(job_id: str) -> Optional[dict]:
    """Read clips_result.json for a job."""
    path = os.path.join(_get_jobs_dir(), job_id, "clips_result.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _format_timestamp(ts) -> Optional[str]:
    """Format a timestamp that may be a Unix float or a SQLite datetime string."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts).isoformat()
        except ValueError:
            return ts
    return str(ts)


async def _send_webhook(webhook_url: str, payload: WebhookPayload) -> None:
    """Send webhook with retry logic."""
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(webhook_url, json=payload.model_dump())
                return
        except (httpx.HTTPError, Exception):
            if attempt < 2:
                await asyncio.sleep([1, 5][attempt])


def _build_clip_results(job_id: str, auto_meta: dict, meta: dict) -> ClipResult:
    """Build ClipResult from pipeline artifacts."""
    clips_result = _read_clips_result(job_id)
    clips_data = clips_result if isinstance(clips_result, list) else (clips_result or {}).get("clips", [])

    # Load R2 upload URLs if available
    r2_uploads = {}
    r2_list = auto_meta.get("r2_uploads", [])
    if r2_list:
        for r in r2_list:
            fn = r.get("filename", "")
            if r.get("r2_url"):
                r2_uploads[fn] = r["r2_url"]

    clips = []
    for i, c in enumerate(clips_data, 1):
        clip = ClipDetail.from_pipeline_dict(c, job_id=job_id, index=i)
        clip_path = c.get("path", "")
        filename = clip_path.rsplit("/", 1)[-1] if "/" in clip_path else clip_path.rsplit("\\", 1)[-1]
        if os.path.exists(clip_path):
            clip.file_size_bytes = os.path.getsize(clip_path)
        # Attach R2 URL if auto-uploaded
        if filename in r2_uploads:
            clip.r2_url = r2_uploads[filename]
        clips.append(clip)

    total_duration = sum(c.duration for c in clips)
    created_at = meta.get("created_at", 0)
    completed_ts = meta.get("completed_at", created_at)
    processing_time = completed_ts - created_at if completed_ts and created_at else None

    return ClipResult(
        job_id=job_id,
        status="complete",
        completed_at=_format_timestamp(meta.get("completed_at")),
        processing_time_seconds=processing_time,
        source_url=auto_meta.get("source_url", ""),
        clips=clips,
        total_clips=len(clips),
        total_duration_seconds=total_duration,
    )


def _read_auto_meta(job_id: str) -> dict:
    """Read automation_meta.json for a job."""
    path = os.path.join(_get_jobs_dir(), job_id, "automation_meta.json")
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


# --- Endpoints ---


@router.post("/clip", response_model=SubmitResponse, status_code=202)
async def submit_clip(request: ClipRequest, background_tasks: BackgroundTasks):
    """Submit a YouTube URL for automated clip processing."""
    bridge = PipelineBridge()
    job_data = bridge.build_job_data(request)

    job_id = job_manager.submit_job(job_data, priority=request.priority)

    # Save automation-specific metadata
    job_dir = os.path.join(_get_jobs_dir(), job_id)
    os.makedirs(job_dir, exist_ok=True)
    auto_meta = {
        "source_url": request.url,
        "webhook_url": request.webhook_url,
        "submitted_at": time.time(),
        "params": request.model_dump(exclude={"api_key", "webhook_url"}),
    }
    with open(os.path.join(job_dir, "automation_meta.json"), "w") as f:
        json.dump(auto_meta, f, indent=2)

    # Log initial entry
    collector = LogCollector(job_id, _get_jobs_dir())
    collector.log("queued", f"Job submitted: {request.url}")
    collector.save()

    status_url = f"/api/v1/jobs/{job_id}"

    return SubmitResponse(
        job_id=job_id,
        status_url=status_url,
    )


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get detailed job status with logs."""
    meta = _read_metadata(job_id)
    if not meta:
        raise HTTPException(status_code=404, detail={
            "success": False,
            "error": {"code": "JOB_NOT_FOUND", "message": f"Job {job_id} not found"}
        })

    auto_meta = _read_auto_meta(job_id)

    # Read logs
    collector = LogCollector(job_id, _get_jobs_dir())
    logs = collector.get_logs()

    status_value = meta.get("status", "unknown")

    result = None
    if status_value == "complete":
        clips_result = _read_clips_result(job_id)
        if clips_result:
            result = _build_clip_results(job_id, auto_meta, meta)

    return JobStatusResponse(
        job_id=job_id,
        status=status_value,
        progress=meta.get("percentage", 0),
        stage=status_value,
        message=meta.get("progress", meta.get("progress_msg", "")),
        submitted_at=_format_timestamp(meta.get("created_at")),
        started_at=None,
        updated_at=_format_timestamp(meta.get("last_updated")),
        source_url=auto_meta.get("source_url"),
        params=auto_meta.get("params"),
        priority=meta.get("priority"),
        logs=[AutomationLogEntry(**l) for l in logs],
        result=result,
    )


@router.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    """Get completed clip results with download URLs."""
    meta = _read_metadata(job_id)
    if not meta:
        raise HTTPException(status_code=404, detail={
            "success": False,
            "error": {"code": "JOB_NOT_FOUND", "message": f"Job {job_id} not found"}
        })

    status_value = meta.get("status", "")
    if status_value != "complete":
        raise HTTPException(status_code=409, detail={
            "success": False,
            "error": {
                "code": "JOB_NOT_COMPLETE",
                "message": "Job is still processing",
                "current_status": status_value,
                "progress": meta.get("percentage", 0),
            }
        })

    clips_result = _read_clips_result(job_id)
    if not clips_result:
        raise HTTPException(status_code=404, detail={
            "success": False,
            "error": {"code": "NO_RESULT", "message": "No clip results found"}
        })

    auto_meta = _read_auto_meta(job_id)
    return _build_clip_results(job_id, auto_meta, meta)


@router.get("/jobs")
async def list_jobs(status: Optional[str] = None, limit: int = 20, offset: int = 0):
    """List all jobs with optional status filter."""
    jobs = job_database.list_jobs(status=status, limit=limit, offset=offset)
    stats = job_database.get_stats()

    items = []
    for j in jobs:
        jid = j.get("job_id", "")
        auto_meta = _read_auto_meta(jid)

        total_clips = None
        if j.get("status") == "complete":
            clips_result = _read_clips_result(jid)
            if clips_result:
                clips_data = clips_result if isinstance(clips_result, list) else clips_result.get("clips", [])
                total_clips = len(clips_data)

        items.append(JobListItem(
            job_id=jid,
            status=j.get("status", "unknown"),
            progress=j.get("progress", 0) or 0,
            source_url=auto_meta.get("source_url"),
            submitted_at=_format_timestamp(j.get("created_at")),
            total_clips=total_clips,
        ))

    return JobListResponse(
        jobs=items,
        total=stats.get("total_jobs", len(items)),
        queue={
            "pending": stats.get("by_status", {}).get("queued", 0),
            "processing": stats.get("by_status", {}).get("processing", 0),
        },
    )


@router.post("/jobs/{job_id}/upload-r2")
async def upload_clips_to_r2(job_id: str, folder: str = "clips"):
    """Upload completed job clips to Cloudflare R2.

    Returns list of uploaded clips with their public R2 URLs.
    Requires job to be in 'complete' status.
    """
    meta = _read_metadata(job_id)
    if not meta:
        raise HTTPException(status_code=404, detail={
            "success": False,
            "error": {"code": "JOB_NOT_FOUND", "message": f"Job {job_id} not found"}
        })

    status_value = meta.get("status", "")
    if status_value != "complete":
        raise HTTPException(status_code=409, detail={
            "success": False,
            "error": {
                "code": "JOB_NOT_COMPLETE",
                "message": "Job must be complete before uploading to R2",
                "current_status": status_value,
            }
        })

    clips_result = _read_clips_result(job_id)
    if not clips_result:
        raise HTTPException(status_code=404, detail={
            "success": False,
            "error": {"code": "NO_RESULT", "message": "No clip results found"}
        })

    clips_data = clips_result if isinstance(clips_result, list) else clips_result.get("clips", [])

    # Upload all clips
    upload_results = upload_job_clips(job_id, clips_data, folder=folder)

    uploaded_count = sum(1 for r in upload_results if r["status"] == "uploaded")
    error_count = sum(1 for r in upload_results if r["status"] == "error")
    skipped_count = sum(1 for r in upload_results if r["status"] == "skipped")

    return {
        "success": True,
        "job_id": job_id,
        "folder": folder,
        "total_clips": len(clips_data),
        "uploaded": uploaded_count,
        "errors": error_count,
        "skipped": skipped_count,
        "clips": upload_results,
    }


@router.get("/download/{job_id}/{filename}")
async def download_clip(job_id: str, filename: str):
    """Download a completed clip file."""
    clips_result = _read_clips_result(job_id)
    if not clips_result:
        raise HTTPException(status_code=404, detail="Job or clips not found")

    clips_data = clips_result if isinstance(clips_result, list) else clips_result.get("clips", [])

    for clip in clips_data:
        clip_path = clip.get("path", "")
        clip_filename = clip_path.rsplit("/", 1)[-1] if "/" in clip_path else clip_path.rsplit("\\", 1)[-1]
        if clip_filename == filename:
            if not os.path.exists(clip_path):
                raise HTTPException(status_code=404, detail="File not found on disk")
            abs_path = os.path.abspath(clip_path)
            return FileResponse(abs_path, media_type="video/mp4", filename=filename)

    raise HTTPException(status_code=404, detail="Clip file not found")


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running or queued job."""
    result = job_manager.cancel_job(job_id)
    if not result:
        raise HTTPException(status_code=404, detail={
            "success": False,
            "error": {"code": "JOB_NOT_FOUND", "message": f"Job {job_id} not found or cannot be cancelled"}
        })
    return {"success": True, "message": "Job cancelled"}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job and its artifacts."""
    meta = _read_metadata(job_id)
    if not meta:
        raise HTTPException(status_code=404, detail={
            "success": False,
            "error": {"code": "JOB_NOT_FOUND", "message": f"Job {job_id} not found"}
        })

    # Cancel first if still running
    job_manager.cancel_job(job_id)

    # Delete from database
    job_database.delete_job(job_id)

    # Delete job artifacts directory
    job_dir = os.path.join(_get_jobs_dir(), job_id)
    if os.path.exists(job_dir):
        shutil.rmtree(job_dir, ignore_errors=True)

    return {"success": True, "message": f"Job {job_id} deleted"}


@router.get("/pipelines")
async def pipeline_info():
    """Return pipeline stages and default settings."""
    return {
        "stages": [
            {"name": "preparing", "description": "Download video from YouTube"},
            {"name": "transcribing", "description": "Extract transcript via ASR"},
            {"name": "analyzing", "description": "LLM selects viral clips"},
            {"name": "cutting", "description": "Cut, crop, overlay, burn subtitles"},
            {"name": "complete", "description": "Clips ready for download"},
        ],
        "defaults": {
            "aspect_ratio": "9:16",
            "subtitle_enabled": True,
            "hook_enabled": True,
            "max_clips": 5,
            "min_clip_duration": 15,
            "transcription_mode": "fast",
            "quality": "720p",
            "priority": 5,
        },
        "supported": {
            "aspect_ratios": ["9:16", "16:9", "1:1", "4:5", "original"],
            "transcription_modes": ["fast", "small", "accurate"],
            "qualities": ["best", "1080p", "720p", "480p", "audio"],
            "hook_styles": ["preset-1", "preset-2", "preset-3", "preset-4"],
        },
    }
