from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


SUPPORTED_ASPECT_RATIOS = {"9:16", "16:9", "1:1", "4:5", "original"}
SUPPORTED_TRANSCRIPTION_MODES = {"fast", "small", "accurate"}
SUPPORTED_QUALITIES = {"best", "1080p", "720p", "480p", "audio"}
SUPPORTED_WATERMARK_TYPES = {"text", "image"}
SUPPORTED_WATERMARK_POSITIONS = {
    "top_left", "top_right", "top_center",
    "bottom_left", "bottom_right", "bottom_center",
    "center",
}
SUPPORTED_CTA_TYPES = {"image", "video"}
YOUTUBE_URL_PATTERN = re.compile(
    r"^https?://(www\.)?(youtube\.com/(watch\?v=|shorts/|live/)|youtu\.be/|m\.youtube\.com/watch\?v=)"
)


class ClipRequest(BaseModel):
    url: str
    aspect_ratio: str = "9:16"
    subtitle_enabled: Optional[bool] = None
    subtitle_style: Optional[str] = None
    hook_enabled: Optional[bool] = None
    hook_style: Optional[str] = None
    max_clips: int = Field(default=5, ge=1, le=20)
    min_clip_duration: int = Field(default=15, ge=5, le=300)
    max_clip_duration: int = Field(default=60, ge=10, le=600)
    llm_provider: Optional[str] = None
    api_key: Optional[str] = None
    transcription_mode: str = "fast"
    quality: str = "720p"
    webhook_url: Optional[str] = None
    priority: int = Field(default=5, ge=0, le=10)

    # Watermark
    watermark_enabled: bool = False
    watermark_type: str = "text"
    watermark_text: str = ""
    watermark_image_path: Optional[str] = None
    watermark_opacity: float = Field(default=0.5, ge=0.0, le=1.0)
    watermark_position: str = "bottom_right"
    watermark_size: float = Field(default=0.3, ge=0.01, le=1.0)
    watermark_font: str = "Arial-Bold"

    # CTA (Call-to-Action) appended at end of each clip
    cta_enabled: Optional[bool] = None
    cta_type: Optional[str] = None
    cta_path: Optional[str] = None  # File path OR directory path (directory = random pick per clip)
    cta_duration: Optional[float] = None

    # Auto-upload to Cloudflare R2 after completion
    upload_r2: bool = False
    r2_folder: str = "clips"

    # Metadata randomization
    randomize_metadata: bool = False

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not YOUTUBE_URL_PATTERN.match(v):
            raise ValueError(
                "URL must be a valid YouTube link "
                "(youtube.com/watch?v=, youtu.be/, youtube.com/shorts/)"
            )
        return v

    @field_validator("aspect_ratio")
    @classmethod
    def validate_aspect_ratio(cls, v: str) -> str:
        if v not in SUPPORTED_ASPECT_RATIOS:
            raise ValueError(f"aspect_ratio must be one of {SUPPORTED_ASPECT_RATIOS}")
        return v

    @field_validator("transcription_mode")
    @classmethod
    def validate_transcription_mode(cls, v: str) -> str:
        if v not in SUPPORTED_TRANSCRIPTION_MODES:
            raise ValueError(f"transcription_mode must be one of {SUPPORTED_TRANSCRIPTION_MODES}")
        return v

    @field_validator("quality")
    @classmethod
    def validate_quality(cls, v: str) -> str:
        if v not in SUPPORTED_QUALITIES:
            raise ValueError(f"quality must be one of {SUPPORTED_QUALITIES}")
        return v

    @field_validator("watermark_type")
    @classmethod
    def validate_watermark_type(cls, v: str) -> str:
        if v not in SUPPORTED_WATERMARK_TYPES:
            raise ValueError(f"watermark_type must be one of {SUPPORTED_WATERMARK_TYPES}")
        return v

    @field_validator("watermark_position")
    @classmethod
    def validate_watermark_position(cls, v: str) -> str:
        if v not in SUPPORTED_WATERMARK_POSITIONS:
            raise ValueError(f"watermark_position must be one of {SUPPORTED_WATERMARK_POSITIONS}")
        return v

    @field_validator("cta_type")
    @classmethod
    def validate_cta_type(cls, v: str) -> str:
        if v not in SUPPORTED_CTA_TYPES:
            raise ValueError(f"cta_type must be one of {SUPPORTED_CTA_TYPES}")
        return v


class SubmitResponse(BaseModel):
    success: bool = True
    job_id: str
    message: str = "Job queued for processing"
    status_url: str


class AutomationLogEntry(BaseModel):
    timestamp: str
    stage: str
    level: str = "info"
    message: str


class ClipDetail(BaseModel):
    index: int
    filename: str
    download_url: str
    duration: float
    topic: str
    reason: str
    caption: str = ""
    hook_heading: str = ""
    hook_subheading: str = ""
    file_size_bytes: Optional[int] = None
    r2_url: Optional[str] = None

    @classmethod
    def from_pipeline_dict(cls, d: dict, job_id: str, index: int) -> "ClipDetail":
        path = d.get("path", "")
        filename = path.rsplit("/", 1)[-1] if "/" in path else path.rsplit("\\", 1)[-1]
        try:
            duration = float(d.get("duration", "0"))
        except (ValueError, TypeError):
            duration = 0.0
        return cls(
            index=index,
            filename=filename,
            download_url=f"/api/v1/download/{job_id}/{filename}",
            duration=duration,
            topic=d.get("topic", ""),
            reason=d.get("reason", ""),
            caption=d.get("caption", ""),
            hook_heading=d.get("hook_heading", ""),
            hook_subheading=d.get("hook_subheading", ""),
        )


class ClipResult(BaseModel):
    job_id: str
    status: str
    completed_at: Optional[str] = None
    processing_time_seconds: Optional[float] = None
    source_url: str
    clips: List[ClipDetail]
    total_clips: int
    total_duration_seconds: float = 0.0


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    stage: str
    message: str
    submitted_at: Optional[str] = None
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    source_url: Optional[str] = None
    params: Optional[dict] = None
    priority: Optional[int] = None
    logs: List[AutomationLogEntry] = []
    result: Optional[ClipResult] = None


class JobListItem(BaseModel):
    job_id: str
    status: str
    progress: int
    source_url: Optional[str] = None
    submitted_at: Optional[str] = None
    total_clips: Optional[int] = None


class JobListResponse(BaseModel):
    jobs: List[JobListItem]
    total: int
    queue: dict


class ErrorResponse(BaseModel):
    success: bool = False
    error: dict


class WebhookPayload(BaseModel):
    event: str
    job_id: str
    status: str
    clips: Optional[List[dict]] = None
    total_clips: Optional[int] = None
    processing_time_seconds: Optional[float] = None
    error: Optional[dict] = None
