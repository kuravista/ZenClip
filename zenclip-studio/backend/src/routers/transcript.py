"""
Transcript review endpoints.
"""
import os
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any

router = APIRouter(prefix="", tags=["transcript"])


@router.post("/extract_transcript")
async def extract_transcript(
    video: UploadFile = File(...),
    stop_for_review: bool = Form(True),
):
    """Extract transcript from video."""
    # Save uploaded file
    upload_path = os.path.join('uploads', video.filename)
    os.makedirs('uploads', exist_ok=True)

    with open(upload_path, 'wb') as f:
        f.write(await video.read())

    # Import services - will be replaced
    from services.core.job_manager import job_manager

    # Prepare job data for transcript extraction
    job_data = {
        'video_path': upload_path,
        'stop_for_review': stop_for_review,
    }

    job_id = job_manager.submit_job(job_data)

    if job_id:
        return {"status": "success", "job_id": job_id}
    else:
        raise HTTPException(status_code=500, detail="Failed to submit job")


@router.get("/get_transcript/{job_id}")
async def get_transcript(job_id: str):
    """Get transcript data for a job."""
    from services.core.job_manager import job_manager

    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    # Read transcript file if exists
    jobs_dir = os.environ.get('CLIP_JOBS_DIR', 'jobs_data')
    transcript_path = os.path.join(jobs_dir, job_id, 'transcript.json')

    if os.path.exists(transcript_path):
        import json
        with open(transcript_path, 'r') as f:
            transcript = json.load(f)
        return transcript
    else:
        return {"status": "pending", "message": "Transcript not ready yet"}


@router.post("/process_with_transcript")
async def process_with_transcript(
    job_id: str = Form(...),
    transcript_data: str = Form(...),
    clips_data: str = Form(...),
):
    """Process video with edited transcript."""
    from services.core.job_manager import job_manager

    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    # Save edited transcript and clips
    import json

    jobs_dir = os.environ.get('CLIP_JOBS_DIR', 'jobs_data')
    job_dir = os.path.join(jobs_dir, job_id)
    os.makedirs(job_dir, exist_ok=True)

    # Save transcript
    transcript_path = os.path.join(job_dir, 'transcript.json')
    with open(transcript_path, 'w') as f:
        json.dump(json.loads(transcript_data), f, indent=2)

    # Save clips if provided
    if clips_data:
        clips_path = os.path.join(job_dir, 'analysis.json')
        with open(clips_path, 'w') as f:
            json.dump({"clips": json.loads(clips_data)}, f, indent=2)

    # Resume job
    job_manager.resume_job(job_id)

    return {"status": "success", "message": "Processing resumed"}


@router.post("/manual_transcript_import")
async def manual_transcript_import(
    video_path: str = Form(...),
    phrase_timings: str = Form(...),
    clips_data: Optional[str] = Form(None),
):
    """Import transcript manually without ASR."""
    import json

    from services.core.job_manager import job_manager

    # Parse input data
    timings = json.loads(phrase_timings)
    clips = json.loads(clips_data) if clips_data else None

    # Create job
    job_data = {
        'video_path': video_path,
        'manual_transcript': timings,
        'manual_clips': clips,
        'stop_for_review': clips is None,
    }

    job_id = job_manager.submit_job(job_data)

    if job_id:
        return {"status": "success", "job_id": job_id}
    else:
        raise HTTPException(status_code=500, detail="Failed to submit job")


@router.post("/auto_fix_transcript")
async def auto_fix_transcript(
    transcript: str = Form(...),
):
    """Auto-fix transcript typos using LLM."""
    import json

    transcript_data = json.loads(transcript)

    # Import LLM service - will be replaced
    from services.ai.llm import auto_fix_transcript_with_llm

    fixed = await auto_fix_transcript_with_llm(transcript_data)

    return {"status": "success", "transcript": fixed}
