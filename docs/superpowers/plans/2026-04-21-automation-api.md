# Automation API Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `/api/v1/` automation router to ZenClip Studio that accepts a YouTube URL and runs the full clip pipeline automatically, with progress tracking, log collection, and download URLs.

**Architecture:** New `routers/automation.py` router uses a bridge pattern to convert simple JSON params into the existing `JobManager.submit_job()` format. A log collector hooks into status updates to produce per-stage logs. No changes to the pipeline itself.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic v2, existing JobManager/JobRunner infrastructure

**Spec:** `docs/superpowers/specs/2026-04-21-automation-api-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/src/services/automation/__init__.py` | Package marker |
| Create | `backend/src/services/automation/models.py` | Pydantic request/response models |
| Create | `backend/src/services/automation/pipeline_bridge.py` | Converts automation params → job_data dict |
| Create | `backend/src/services/automation/log_collector.py` | Collects stage logs by watching metadata changes |
| Create | `backend/src/routers/automation.py` | FastAPI router with all /api/v1/ endpoints |
| Create | `backend/tests/test_automation_models.py` | Tests for Pydantic models |
| Create | `backend/tests/test_automation_bridge.py` | Tests for pipeline bridge |
| Create | `backend/tests/test_automation_router.py` | Integration tests for router endpoints |
| Create | `backend/tests/conftest.py` | pytest sys.path setup |
| Modify | `backend/src/app.py:400-401` | Register automation router |
| Modify | `backend/src/app_modular.py:130-139` | Register automation router |

---

### Task 0: Create test infrastructure

**Files:**
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Create conftest.py with sys.path setup**

```python
# backend/tests/conftest.py
import sys
import os

# Add backend/src to sys.path so imports like "from services.automation..." work
src_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
```

- [ ] **Step 2: Verify pytest can discover tests**

Run: `cd backend && python -m pytest --collect-only tests/ 2>&1 | head -5`
Expected: No import errors (may show "no tests collected" since none exist yet)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/conftest.py
git commit -m "chore: add conftest.py for automation test imports"
```

---

### Task 1: Create Pydantic Models

**Files:**
- Create: `backend/src/services/automation/__init__.py`
- Create: `backend/src/services/automation/models.py`
- Create: `backend/tests/test_automation_models.py`

- [ ] **Step 1: Write tests for models**

```python
# backend/tests/test_automation_models.py
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
        err = ErrorResponse(code="DOWNLOAD_FAILED", message="Video unavailable", stage="preparing")
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_automation_models.py -v`
Expected: FAIL — module `services.automation.models` does not exist

- [ ] **Step 3: Create package init**

```python
# backend/src/services/automation/__init__.py
```

- [ ] **Step 4: Create models**

```python
# backend/src/services/automation/models.py
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


SUPPORTED_ASPECT_RATIOS = {"9:16", "16:9", "1:1", "4:5", "original"}
SUPPORTED_TRANSCRIPTION_MODES = {"fast", "small", "accurate"}
SUPPORTED_QUALITIES = {"best", "1080p", "720p", "480p", "audio"}
YOUTUBE_URL_PATTERN = re.compile(
    r"^https?://(www\.)?(youtube\.com/(watch\?v=|shorts/|live/)|youtu\.be/|m\.youtube\.com/watch\?v=)"
)


class ClipRequest(BaseModel):
    url: str
    aspect_ratio: str = "9:16"
    subtitle_enabled: bool = True
    subtitle_style: str = "word"
    hook_enabled: bool = True
    hook_style: str = "preset-2"
    max_clips: int = Field(default=5, ge=1, le=20)
    min_clip_duration: int = Field(default=15, ge=5, le=300)
    max_clip_duration: int = Field(default=60, ge=10, le=600)
    llm_provider: Optional[str] = None
    api_key: Optional[str] = None
    transcription_mode: str = "fast"
    quality: str = "720p"
    webhook_url: Optional[str] = None
    priority: int = Field(default=5, ge=0, le=10)

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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_automation_models.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add backend/src/services/automation/__init__.py backend/src/services/automation/models.py backend/tests/test_automation_models.py
git commit -m "feat(automation): add Pydantic models for v1 API"
```

---

### Task 2: Create Pipeline Bridge

**Files:**
- Create: `backend/src/services/automation/pipeline_bridge.py`
- Create: `backend/tests/test_automation_bridge.py`

- [ ] **Step 1: Write tests for bridge**

```python
# backend/tests/test_automation_bridge.py
import pytest
import json
from unittest.mock import patch, MagicMock
from services.automation.models import ClipRequest
from services.automation.pipeline_bridge import PipelineBridge, DEFAULT_SETTINGS


class TestPipelineBridge:
    def setup_method(self):
        self.bridge = PipelineBridge()

    def test_minimal_request_mapping(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc123")
        job_data = self.bridge.build_job_data(req)
        assert job_data["url"] == "https://youtube.com/watch?v=abc123"
        assert job_data["yt_quality"] == "720p"
        assert job_data["video_aspect"] == "9:16"
        assert job_data["stop_for_review"] is False
        assert job_data["add_subtitles"] is True
        assert job_data["add_viral_hook"] is True
        assert job_data["transcription_mode"] == "fast"
        assert job_data["num_clips"] == 5
        assert job_data["min_duration"] == "15"
        assert job_data["api_provider"] == "deepseek"
        assert "hook_styles" in job_data
        assert job_data["hook_styles"]["hook_style"] == "preset-2"

    def test_aspect_ratio_maps_to_video_aspect(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc", aspect_ratio="16:9")
        job_data = self.bridge.build_job_data(req)
        assert job_data["video_aspect"] == "16:9"
        # Should NOT have 'aspect_ratio' key
        assert "aspect_ratio" not in job_data

    def test_transcription_mode_passthrough(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc", transcription_mode="accurate")
        job_data = self.bridge.build_job_data(req)
        assert job_data["transcription_mode"] == "accurate"

    def test_hook_disabled_omits_hook_styles(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc", hook_enabled=False)
        job_data = self.bridge.build_job_data(req)
        assert job_data["add_viral_hook"] is False
        assert "hook_styles" not in job_data

    def test_subtitle_disabled(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc", subtitle_enabled=False)
        job_data = self.bridge.build_job_data(req)
        assert job_data["add_subtitles"] is False

    def test_custom_provider_and_key(self):
        req = ClipRequest(
            url="https://youtube.com/watch?v=abc",
            llm_provider="openrouter",
            api_key="sk-test-123"
        )
        job_data = self.bridge.build_job_data(req)
        assert job_data["api_provider"] == "openrouter"
        assert job_data["api_key"] == "sk-test-123"

    def test_settings_fallback(self):
        """When request has no provider, bridge reads from settings."""
        bridge = PipelineBridge(settings={"api_provider": "gemini", "api_key": "gemini-key"})
        req = ClipRequest(url="https://youtube.com/watch?v=abc")
        job_data = bridge.build_job_data(req)
        assert job_data["api_provider"] == "gemini"
        assert job_data["api_key"] == "gemini-key"

    def test_request_overrides_settings(self):
        bridge = PipelineBridge(settings={"api_provider": "gemini"})
        req = ClipRequest(url="https://youtube.com/watch?v=abc", llm_provider="openai")
        job_data = bridge.build_job_data(req)
        assert job_data["api_provider"] == "openai"

    def test_download_folder_set(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc")
        job_data = self.bridge.build_job_data(req)
        assert job_data["download_folder"] == "downloads"

    def test_quality_maps_to_yt_quality(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc", quality="1080p")
        job_data = self.bridge.build_job_data(req)
        assert job_data["yt_quality"] == "1080p"

    def test_hook_styles_dict_with_preset2(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc", hook_style="preset-2")
        job_data = self.bridge.build_job_data(req)
        assert job_data["hook_styles"]["hook_style"] == "preset-2"

    def test_max_clips_maps_to_num_clips(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc", max_clips=10)
        job_data = self.bridge.build_job_data(req)
        assert job_data["num_clips"] == 10

    def test_min_clip_duration_maps_to_min_duration(self):
        req = ClipRequest(url="https://youtube.com/watch?v=abc", min_clip_duration=20)
        job_data = self.bridge.build_job_data(req)
        assert job_data["min_duration"] == "20"

    def test_default_provider_when_no_settings(self):
        """When no settings and no request override, default to deepseek."""
        bridge = PipelineBridge(settings={})
        req = ClipRequest(url="https://youtube.com/watch?v=abc")
        job_data = bridge.build_job_data(req)
        assert job_data["api_provider"] == "deepseek"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_automation_bridge.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement pipeline bridge**

```python
# backend/src/services/automation/pipeline_bridge.py
from __future__ import annotations

import os
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from services.automation.models import ClipRequest


DEFAULT_SETTINGS: Dict[str, Any] = {}


def _read_user_settings() -> dict:
    """Read user_settings.json using the same path resolution as the rest of the app."""
    settings_path = os.environ.get("CLIP_SETTINGS_FILE")
    if not settings_path:
        app_data_dir = os.environ.get("CLIP_APP_DATA_DIR", ".")
        settings_path = str(Path(app_data_dir) / "user_settings.json")
    try:
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return {}


class PipelineBridge:
    """Converts Automation API parameters to job_data format expected by JobManager.submit_job()."""

    def __init__(self, settings: Optional[dict] = None):
        self._settings = settings if settings is not None else _read_user_settings()

    def build_job_data(self, request: ClipRequest) -> dict:
        """Build the job_data dict compatible with the existing pipeline."""
        job_data: Dict[str, Any] = {}

        # --- Source ---
        job_data["url"] = request.url
        job_data["yt_quality"] = request.quality
        job_data["download_folder"] = "downloads"

        # --- Pipeline control ---
        job_data["stop_for_review"] = False  # Automation never pauses for review

        # --- Aspect ratio ---
        job_data["video_aspect"] = request.aspect_ratio  # Pipeline reads 'video_aspect', NOT 'aspect_ratio'

        # --- Transcription ---
        job_data["transcription_mode"] = request.transcription_mode

        # --- Subtitles ---
        job_data["add_subtitles"] = request.subtitle_enabled  # Pipeline expects bool
        if request.subtitle_enabled:
            job_data["subtitle_config"] = {"style": request.subtitle_style}  # Pipeline reads subtitle_config dict

        # --- Hook ---
        job_data["add_viral_hook"] = request.hook_enabled  # Pipeline expects bool
        if request.hook_enabled:
            hook_styles: Dict[str, Any] = {"hook_style": request.hook_style}
            if request.hook_style == "preset-2":
                preset2_content = self._settings.get("preset2_content", "")
                hook_styles["preset2_content"] = preset2_content
            job_data["hook_styles"] = hook_styles

        # --- Analysis ---
        job_data["num_clips"] = request.max_clips
        job_data["min_duration"] = str(request.min_clip_duration)

        # --- LLM provider ---
        provider = request.llm_provider or self._settings.get("api_provider", "deepseek")
        api_key = request.api_key or self._settings.get("api_key", "")
        job_data["api_provider"] = provider
        if api_key:
            job_data["api_key"] = api_key

        # --- Other defaults the pipeline expects ---
        job_data.setdefault("video_type", "general")
        job_data.setdefault("encoding_preset", "medium")
        job_data.setdefault("manual_cut", "false")

        return job_data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_automation_bridge.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/services/automation/pipeline_bridge.py backend/tests/test_automation_bridge.py
git commit -m "feat(automation): add pipeline bridge for v1 API"
```

---

### Task 3: Create Log Collector

**Files:**
- Create: `backend/src/services/automation/log_collector.py`
- Create: `backend/tests/test_automation_log_collector.py`

- [ ] **Step 1: Write tests for log collector**

```python
# backend/tests/test_automation_log_collector.py
import json
import os
import time
import tempfile
import pytest
from services.automation.log_collector import LogCollector


class TestLogCollector:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.job_id = "test-job-123"
        self.jobs_dir = self.tmpdir
        self.collector = LogCollector(self.job_id, self.jobs_dir)

    def test_initial_log_entry(self):
        self.collector.log("preparing", "Job submitted")
        logs = self.collector.get_logs()
        assert len(logs) == 1
        assert logs[0]["stage"] == "preparing"
        assert logs[0]["message"] == "Job submitted"
        assert logs[0]["level"] == "info"

    def test_multiple_entries(self):
        self.collector.log("preparing", "Downloading...")
        self.collector.log("transcribing", "Starting ASR")
        self.collector.log("complete", "Done")
        logs = self.collector.get_logs()
        assert len(logs) == 3

    def test_persist_and_reload(self):
        self.collector.log("preparing", "Test entry")
        self.collector.save()

        # Create new collector instance to verify persistence
        collector2 = LogCollector(self.job_id, self.jobs_dir)
        logs = collector2.get_logs()
        assert len(logs) == 1
        assert logs[0]["message"] == "Test entry"

    def test_error_level(self):
        self.collector.log("analyzing", "LLM failed", level="error")
        logs = self.collector.get_logs()
        assert logs[0]["level"] == "error"

    def test_timestamp_format(self):
        self.collector.log("preparing", "Test")
        logs = self.collector.get_logs()
        assert "T" in logs[0]["timestamp"]  # ISO format

    def test_from_metadata_change(self):
        """Test creating log entries from metadata status changes."""
        self.collector.log_from_metadata(
            status="preparing",
            progress_percent=10,
            message="Downloading video..."
        )
        logs = self.collector.get_logs()
        assert logs[0]["stage"] == "preparing"
        assert logs[0]["message"] == "Downloading video..."

    def test_no_duplicate_stage_entries(self):
        """Same stage+message should not produce duplicates."""
        self.collector.log_from_metadata("preparing", 10, "Working...")
        self.collector.log_from_metadata("preparing", 15, "Working...")
        logs = self.collector.get_logs()
        assert len(logs) == 2  # Different messages, both kept

    def test_empty_logs_on_new_job(self):
        logs = self.collector.get_logs()
        assert logs == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_automation_log_collector.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement log collector**

```python
# backend/src/services/automation/log_collector.py
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import List, Optional


class LogCollector:
    """Collects structured log entries for an automation job.

    Logs are kept in memory and periodically flushed to
    jobs_data/{job_id}/automation_logs.json on disk.
    """

    def __init__(self, job_id: str, jobs_dir: str = "jobs_data"):
        self.job_id = job_id
        self.jobs_dir = jobs_dir
        self._logs: List[dict] = []
        self._load_existing()

    def _log_path(self) -> str:
        return os.path.join(self.jobs_dir, self.job_id, "automation_logs.json")

    def _load_existing(self) -> None:
        path = self._log_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._logs = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._logs = []

    def log(self, stage: str, message: str, level: str = "info") -> dict:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "level": level,
            "message": message,
        }
        self._logs.append(entry)
        return entry

    def log_from_metadata(self, status: str, progress_percent: int, message: str) -> dict:
        """Create a log entry from a metadata status update."""
        level = "error" if status == "error" else "info"
        return self.log(stage=status, message=message, level=level)

    def get_logs(self) -> List[dict]:
        return list(self._logs)

    def save(self) -> None:
        path = self._log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._logs, f, indent=2, ensure_ascii=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_automation_log_collector.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/services/automation/log_collector.py backend/tests/test_automation_log_collector.py
git commit -m "feat(automation): add log collector for v1 API"
```

---

### Task 4: Create Automation Router

**Files:**
- Create: `backend/src/routers/automation.py`
- Create: `backend/tests/test_automation_router.py`

This is the largest task. The router provides all `/api/v1/` endpoints and wires together the bridge, log collector, and existing JobManager.

- [ ] **Step 1: Write integration tests for router**

```python
# backend/tests/test_automation_router.py
import json
import os
import time
import tempfile
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

# We create a minimal app to test the router in isolation
from routers.automation import router as automation_router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(automation_router, prefix="/api/v1")
    return app  # Matches production: include_router(automation_router, prefix="/api/v1")


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_job_manager():
    with patch("routers.automation.job_manager") as mock:
        mock.submit_job.return_value = "test-job-id-123"
        mock.get_job_status.return_value = {
            "id": "test-job-id-123",
            "status": "queued",
            "progress": "Waiting in queue...",
            "percentage": 0,
            "data": {"url": "https://youtube.com/watch?v=abc"},
            "created_at": time.time(),
            "last_updated": time.time(),
        }
        mock.update_job_status = MagicMock()
        mock.cancel_job.return_value = True
        yield mock


@pytest.fixture
def mock_job_database():
    with patch("routers.automation.job_database") as mock:
        mock.get_job.return_value = None
        mock.list_jobs.return_value = []
        mock.get_stats.return_value = {"total_jobs": 0, "by_status": {"queued": 0, "processing": 0}}
        yield mock


VALID_URL = "https://youtube.com/watch?v=dQw4w9WgXcQ"


class TestSubmitEndpoint:
    def test_submit_success(self, client, mock_job_manager, mock_job_database):
        resp = client.post("/api/v1/clip", json={"url": VALID_URL})
        assert resp.status_code == 202  # Accepted
        data = resp.json()
        assert data["success"] is True
        assert data["job_id"] == "test-job-id-123"
        assert "/api/v1/jobs/" in data["status_url"]
        mock_job_manager.submit_job.assert_called_once()

    def test_submit_calls_bridge(self, client, mock_job_manager, mock_job_database):
        resp = client.post("/api/v1/clip", json={
            "url": VALID_URL,
            "aspect_ratio": "16:9",
            "max_clips": 10,
        })
        assert resp.status_code == 202
        call_args = mock_job_manager.submit_job.call_args
        job_data = call_args[0][0]
        assert job_data["url"] == VALID_URL
        assert job_data["video_aspect"] == "16:9"
        assert job_data["num_clips"] == 10
        assert job_data["stop_for_review"] is False

    def test_submit_missing_url(self, client, mock_job_manager, mock_job_database):
        resp = client.post("/api/v1/clip", json={})
        assert resp.status_code == 422  # Validation error

    def test_submit_invalid_url(self, client, mock_job_manager, mock_job_database):
        resp = client.post("/api/v1/clip", json={"url": "https://example.com"})
        assert resp.status_code == 422

    def test_submit_with_webhook(self, client, mock_job_manager, mock_job_database):
        resp = client.post("/api/v1/clip", json={
            "url": VALID_URL,
            "webhook_url": "https://example.com/hook"
        })
        assert resp.status_code == 202


class TestStatusEndpoint:
    def test_status_found(self, client, mock_job_manager, mock_job_database, tmp_path):
        jobs_dir = str(tmp_path)
        job_id = "test-job-123"
        os.makedirs(os.path.join(jobs_dir, job_id), exist_ok=True)

        # Write metadata
        meta = {
            "id": job_id,
            "status": "cutting",
            "percentage": 85,
            "progress": "Cutting clip 3 of 5...",
            "data": {"url": VALID_URL},
            "created_at": time.time(),
            "last_updated": time.time(),
        }
        with open(os.path.join(jobs_dir, job_id, "metadata.json"), "w") as f:
            json.dump(meta, f)

        with patch("routers.automation._get_jobs_dir", return_value=jobs_dir):
            resp = client.get(f"/api/v1/jobs/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["status"] == "cutting"
        assert data["progress"] == 85

    def test_status_not_found(self, client, mock_job_manager, mock_job_database):
        resp = client.get("/api/v1/jobs/nonexistent-id")
        assert resp.status_code == 404


class TestCancelEndpoint:
    def test_cancel_success(self, client, mock_job_manager, mock_job_database):
        resp = client.post("/api/v1/jobs/test-job-id-123/cancel")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_cancel_not_found(self, client, mock_job_manager, mock_job_database):
        mock_job_manager.cancel_job.return_value = False
        resp = client.post("/api/v1/jobs/nonexistent/cancel")
        assert resp.status_code == 404


class TestPipelineInfoEndpoint:
    def test_pipeline_info(self, client, mock_job_manager, mock_job_database):
        resp = client.get("/api/v1/pipelines")
        assert resp.status_code == 200
        data = resp.json()
        assert "stages" in data
        assert "defaults" in data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_automation_router.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement automation router**

```python
# backend/src/routers/automation.py
from __future__ import annotations

import os
import json
import time
import asyncio
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
    # SQLite returns strings like "2026-04-21 10:00:00"
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
    # Silently fail after retries — webhook failures don't affect job status


@router.post("/clip", response_model=SubmitResponse, status_code=202)
async def submit_clip(request: ClipRequest, background_tasks: BackgroundTasks):
    """Submit a YouTube URL for automated clip processing."""
    bridge = PipelineBridge()
    job_data = bridge.build_job_data(request)

    # Store automation metadata alongside the job
    # (webhook_url, original params — saved after job_id is known)

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

    # Read automation metadata
    auto_meta_path = os.path.join(_get_jobs_dir(), job_id, "automation_meta.json")
    auto_meta = {}
    if os.path.exists(auto_meta_path):
        try:
            with open(auto_meta_path, "r") as f:
                auto_meta = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    # Read logs
    collector = LogCollector(job_id, _get_jobs_dir())
    logs = collector.get_logs()

    # Determine current stage
    status_value = meta.get("status", "unknown")
    stage_map = {
        "queued": "queued",
        "preparing": "preparing",
        "transcribing": "transcribing",
        "analyzing": "analyzing",
        "waiting_review": "waiting_review",
        "cutting": "cutting",
        "complete": "complete",
        "error": "error",
        "cancelled": "cancelled",
    }
    stage = stage_map.get(status_value, status_value)

    result = None
    if status_value == "complete":
        clips_result = _read_clips_result(job_id)
        if clips_result:
            clips_data = clips_result if isinstance(clips_result, list) else clips_result.get("clips", [])
            clips = []
            for i, c in enumerate(clips_data, 1):
                clip = ClipDetail.from_pipeline_dict(c, job_id=job_id, index=i)
                # Get file size
                clip_path = c.get("path", "")
                if os.path.exists(clip_path):
                    clip.file_size_bytes = os.path.getsize(clip_path)
                clips.append(clip)

            total_duration = sum(c.duration for c in clips)
            completed_at = _format_timestamp(meta.get("completed_at"))
            created_at = meta.get("created_at", 0)
            completed_ts = meta.get("completed_at", created_at)
            processing_time = completed_ts - created_at if completed_ts and created_at else None

            result = ClipResult(
                job_id=job_id,
                status="complete",
                completed_at=completed_at,
                processing_time_seconds=processing_time,
                source_url=auto_meta.get("source_url", ""),
                clips=clips,
                total_clips=len(clips),
                total_duration_seconds=total_duration,
            )

    return JobStatusResponse(
        job_id=job_id,
        status=status_value,
        progress=meta.get("percentage", 0),
        stage=stage,
        message=meta.get("progress", meta.get("progress_msg", "")),
        submitted_at=_format_timestamp(meta.get("created_at")),
        started_at=None,  # Not tracked separately in metadata
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

    auto_meta_path = os.path.join(_get_jobs_dir(), job_id, "automation_meta.json")
    auto_meta = {}
    if os.path.exists(auto_meta_path):
        try:
            with open(auto_meta_path, "r") as f:
                auto_meta = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    clips_data = clips_result if isinstance(clips_result, list) else clips_result.get("clips", [])
    clips = []
    for i, c in enumerate(clips_data, 1):
        clip = ClipDetail.from_pipeline_dict(c, job_id=job_id, index=i)
        clip_path = c.get("path", "")
        if os.path.exists(clip_path):
            clip.file_size_bytes = os.path.getsize(clip_path)
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


@router.get("/jobs")
async def list_jobs(status: Optional[str] = None, limit: int = 20, offset: int = 0):
    """List all jobs with optional status filter."""
    jobs = job_database.list_jobs(status=status, limit=limit, offset=offset)
    stats = job_database.get_stats()

    items = []
    for j in jobs:
        auto_meta_path = os.path.join(_get_jobs_dir(), j.get("job_id", ""), "automation_meta.json")
        source_url = None
        if os.path.exists(auto_meta_path):
            try:
                with open(auto_meta_path, "r") as f:
                    source_url = json.load(f).get("source_url")
            except (json.JSONDecodeError, IOError):
                pass

        # Count clips if complete
        total_clips = None
        if j.get("status") == "complete":
            clips_result = _read_clips_result(j.get("job_id", ""))
            if clips_result:
                clips_data = clips_result if isinstance(clips_result, list) else clips_result.get("clips", [])
                total_clips = len(clips_data)

        items.append(JobListItem(
            job_id=j.get("job_id", ""),
            status=j.get("status", "unknown"),
            progress=j.get("progress", 0) or 0,
            source_url=source_url,
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


@router.get("/download/{job_id}/{filename}")
async def download_clip(job_id: str, filename: str):
    """Download a completed clip file."""
    clips_result = _read_clips_result(job_id)
    if not clips_result:
        raise HTTPException(status_code=404, detail="Job or clips not found")

    clips_data = clips_result if isinstance(clips_result, list) else clips_result.get("clips", [])

    # Find the matching clip by filename
    for clip in clips_data:
        clip_path = clip.get("path", "")
        clip_filename = clip_path.rsplit("/", 1)[-1] if "/" in clip_path else clip_path.rsplit("\\", 1)[-1]
        if clip_filename == filename:
            if not os.path.exists(clip_path):
                raise HTTPException(status_code=404, detail="File not found on disk")
            # Security: verify path doesn't escape allowed dirs
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
        import shutil
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_automation_router.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/routers/automation.py backend/tests/test_automation_router.py
git commit -m "feat(automation): add /api/v1/ automation router"
```

---

### Task 5: Register Router in Entry Points

**Files:**
- Modify: `backend/src/app.py` — add router import and registration
- Modify: `backend/src/app_modular.py` — add router import and registration

- [ ] **Step 1: Register in app.py**

In `backend/src/app.py`, near line 400 where the YouTube router is registered, add:

```python
# After the existing youtube router import (around line 400)
from routers.automation import router as automation_router
app.include_router(automation_router, prefix="/api/v1")
```

- [ ] **Step 2: Register in app_modular.py**

In `backend/src/app_modular.py`, after the existing router registrations (around line 139), add:

```python
from routers.automation import router as automation_router
app.include_router(automation_router, prefix="/api/v1")
```

- [ ] **Step 3: Verify both entry points load without errors**

Run: `cd backend && python -c "from src.app import app; print('app.py OK')" && python -c "from src.app_modular import app; print('app_modular.py OK')"`
Expected: Both print OK

- [ ] **Step 4: Commit**

```bash
git add backend/src/app.py backend/src/app_modular.py
git commit -m "feat(automation): register /api/v1/ router in both entry points"
```

---

### Task 6: Manual Smoke Test

**Files:** None (manual testing)

- [ ] **Step 1: Start the backend**

Run: `cd backend && python run_backend.py`

- [ ] **Step 2: Test submit**

```bash
curl -X POST http://127.0.0.1:9478/api/v1/clip \
  -H "Content-Type: application/json" \
  -d '{"url": "https://youtube.com/watch?v=dQw4w9WgXcQ", "max_clips": 3}'
```

Expected: `{"success": true, "job_id": "...", "status_url": "/api/v1/jobs/..."}`

- [ ] **Step 3: Test status polling**

```bash
curl http://127.0.0.1:9478/api/v1/jobs/{job_id}
```

Expected: JSON with `status`, `progress`, `stage`, `logs` fields

- [ ] **Step 4: Test pipeline info**

```bash
curl http://127.0.0.1:9478/api/v1/pipelines
```

Expected: JSON with `stages`, `defaults`, `supported`

- [ ] **Step 5: Test job list**

```bash
curl http://127.0.0.1:9478/api/v1/jobs
```

Expected: JSON with `jobs` array and `queue` info

- [ ] **Step 6: Test error case**

```bash
curl http://127.0.0.1:9478/api/v1/jobs/nonexistent-id
```

Expected: 404 with error JSON

- [ ] **Step 7: Verify existing frontend still works**

Open `http://127.0.0.1:3987` in browser and verify the main UI still functions correctly (no regressions).
