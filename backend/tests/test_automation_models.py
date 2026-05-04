import pytest
from pydantic import ValidationError
from services.automation.models import (
    ClipRequest, JobStatusResponse, ClipResult,
    ClipDetail, JobListItem, AutomationLogEntry,
    ErrorResponse, WebhookPayload
)


class TestClipRequest:
    def test_url_only(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc123")
        assert req.url == "https://youtube.com/watch?v=abc123"
        assert req.aspect_ratio == "9:16"
        assert req.subtitle_enabled is True
        assert req.hook_enabled is True
        assert req.max_clips == 5
        assert req.transcription_mode == "fast"
        assert req.quality == "720p"
        assert req.webhook_url is None
        assert req.priority == 5

    def test_custom_params(self):
        req = ClipRequest(
            url="https://youtube.com/watch?v=abc",
            aspect_ratio="16:9",
            subtitle_enabled=False,
            max_clips=10,
            transcription_mode="accurate",
            quality="1080p",
            llm_provider="openrouter",
            webhook_url="https://example.com/hook",
            priority=1
        )
        assert req.aspect_ratio == "16:9"
        assert req.subtitle_enabled is False
        assert req.max_clips == 10
        assert req.transcription_mode == "accurate"
        assert req.webhook_url == "https://example.com/hook"
        assert req.priority == 1

    def test_missing_url_fails(self):
        with pytest.raises(ValidationError):
            ClipRequest()

    def test_invalid_url_fails(self):
        with pytest.raises(ValidationError):
            ClipRequest(url="not-a-url")

    def test_invalid_transcription_mode_fails(self):
        with pytest.raises(ValidationError):
            ClipRequest(url="https://youtube.com/watch?v=abc", transcription_mode="ultra")

    def test_invalid_aspect_ratio_fails(self):
        with pytest.raises(ValidationError):
            ClipRequest(url="https://youtube.com/watch?v=abc", aspect_ratio="3:2")

    def test_priority_bounds(self):
        with pytest.raises(ValidationError):
            ClipRequest(url="https://youtube.com/watch?v=abc", priority=-1)
        with pytest.raises(ValidationError):
            ClipRequest(url="https://youtube.com/watch?v=abc", priority=11)

    def test_youtube_short_url(self):
        req = ClipRequest(url="https://youtu.be/abc123")
        assert req.url == "https://youtu.be/abc123"

    def test_youtube_mobile_url(self):
        req = ClipRequest(url="https://m.youtube.com/watch?v=abc")
        assert req.url == "https://m.youtube.com/watch?v=abc"


class TestClipDetail:
    def test_from_dict(self):
        d = {
            "path": "clips/uuid/clip_001.mp4",
            "topic": "Intro",
            "reason": "Strong hook",
            "caption": "This is the intro",
            "hook_heading": "WOW",
            "hook_subheading": "Amazing",
            "duration": "32.5"
        }
        clip = ClipDetail.from_pipeline_dict(d, job_id="uuid", index=1)
        assert clip.index == 1
        assert clip.filename == "clip_001.mp4"
        assert clip.download_url == "/api/v1/download/uuid/clip_001.mp4"
        assert clip.duration == 32.5
        assert clip.topic == "Intro"


class TestErrorResponse:
    def test_error_response(self):
        err = ErrorResponse(error={"code": "DOWNLOAD_FAILED", "message": "Video unavailable", "stage": "preparing"})
        d = err.model_dump()
        assert d["success"] is False
        assert d["error"]["code"] == "DOWNLOAD_FAILED"


class TestWebhookPayload:
    def test_complete_payload(self):
        payload = WebhookPayload(
            event="job.complete",
            job_id="uuid",
            status="complete",
            clips=[],
            total_clips=0,
            processing_time_seconds=100
        )
        assert payload.event == "job.complete"
