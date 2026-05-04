"""
Transcript review endpoints.
"""
import json
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from routers.deps import get_job_commands
from services.core.ports.protocols import JobCommandPort

router = APIRouter(prefix="", tags=["transcript"])


@router.post("/extract_transcript")
async def extract_transcript(
    video: UploadFile = File(...),
    stop_for_review: bool = Form(True),
    commands: JobCommandPort = Depends(get_job_commands),
):
    """Extract transcript from video."""
    upload_path = os.path.join("uploads", video.filename)
    os.makedirs("uploads", exist_ok=True)

    with open(upload_path, "wb") as f:
        f.write(await video.read())

    job_data: Dict[str, Any] = {
        "video_file": True,
        "filepath": upload_path,
        "video_path": upload_path,
        "stop_for_review": stop_for_review,
    }

    job_id = commands.submit_job(job_data)

    if job_id:
        return {"status": "success", "job_id": job_id}
    raise HTTPException(status_code=500, detail="Failed to submit job")


@router.get("/get_transcript/{job_id}")
async def get_transcript(
    job_id: str,
    commands: JobCommandPort = Depends(get_job_commands),
):
    """Get transcript data for a job."""
    job = commands.get_job_metadata(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    jobs_dir = os.environ.get("CLIP_JOBS_DIR", "jobs_data")
    transcript_path = os.path.join(jobs_dir, job_id, "transcript.json")

    if os.path.exists(transcript_path):
        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript = json.load(f)
        return transcript
    return {"status": "pending", "message": "Transcript not ready yet"}


@router.post("/process_with_transcript")
async def process_with_transcript(
    job_id: str = Form(...),
    transcript_data: str = Form(...),
    clips_data: str = Form(...),
    commands: JobCommandPort = Depends(get_job_commands),
):
    """Process video with edited transcript."""
    job = commands.get_job_metadata(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    jobs_dir = os.environ.get("CLIP_JOBS_DIR", "jobs_data")
    job_dir = os.path.join(jobs_dir, job_id)
    os.makedirs(job_dir, exist_ok=True)

    transcript_path = os.path.join(job_dir, "transcript.json")
    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump(json.loads(transcript_data), f, indent=2)

    if clips_data:
        clips_path = os.path.join(job_dir, "analysis.json")
        with open(clips_path, "w", encoding="utf-8") as f:
            json.dump({"clips": json.loads(clips_data)}, f, indent=2)

    commands.resume_pipeline_job(job_id)

    return {"status": "success", "message": "Processing resumed"}


@router.post("/manual_transcript_import")
async def manual_transcript_import(
    video_path: str = Form(...),
    phrase_timings: str = Form(...),
    clips_data: Optional[str] = Form(None),
    commands: JobCommandPort = Depends(get_job_commands),
):
    """Import transcript manually without ASR."""
    timings = json.loads(phrase_timings)
    clips = json.loads(clips_data) if clips_data else None

    job_data: Dict[str, Any] = {
        "video_path": video_path,
        "filepath": video_path,
        "video_file": True,
        "manual_transcript": timings,
        "manual_clips": clips,
        "stop_for_review": clips is None,
    }

    job_id = commands.submit_job(job_data)

    if job_id:
        return {"status": "success", "job_id": job_id}
    raise HTTPException(status_code=500, detail="Failed to submit job")


@router.post("/auto_fix_transcript")
async def auto_fix_transcript(
    transcript: str = Form(...),
):
    """Auto-fix transcript typos using LLM."""
    transcript_data = json.loads(transcript)

    from services.ai.llm import auto_fix_transcript_with_llm

    fixed = await auto_fix_transcript_with_llm(transcript_data)

    return {"status": "success", "transcript": fixed}
