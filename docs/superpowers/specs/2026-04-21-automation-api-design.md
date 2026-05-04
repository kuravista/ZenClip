# Automation API Design Spec

**Date:** 2026-04-21
**Status:** Approved
**Author:** Claude + User collaborative design

## Overview

A streamlined REST API (`/api/v1/`) for ZenClip Studio that enables fully automated video clipping from a single YouTube URL. The system accepts a URL, runs the entire 6-stage pipeline automatically (download, transcribe, analyze, cut, overlay, subtitle), and returns downloadable clip URLs with detailed progress logging.

## Requirements

### Must Have
- Single endpoint to submit YouTube URL and get clips back
- Flexible parameters with sensible defaults (all optional except URL)
- Real-time progress tracking via polling
- Detailed stage-by-stage log collection
- Download URLs for completed clips
- Error codes and structured error responses
- Webhook callback support (optional)
- Job listing and management

### Nice to Have
- SSE support for real-time push (future)
- Batch URL submission (future)
- Preset profiles (future)

## Architecture

### Approach: New Router with Bridge Pattern

Create `routers/automation.py` as a new FastAPI router mounted at `/api/v1/`. It bridges to the existing `JobManager` pipeline without modifying pipeline internals.

### File Structure

```
backend/src/
├── routers/
│   └── automation.py          # NEW - /api/v1/ automation router
├── services/
│   └── automation/
│       ├── __init__.py
│       ├── models.py           # Pydantic models for request/response
│       ├── pipeline_bridge.py  # Converts automation params → JobManager.submit_job()
│       └── log_collector.py    # Collects stage logs via existing callbacks
```

### Data Flow

```
Client POST /api/v1/clip {url, ...}
        │
        ▼
automation.py (router)
  ├── Validate input via Pydantic models
  ├── Merge with defaults from user_settings.json
  ├── Build structured job_data dict (same format as /process)
        │
        ▼
pipeline_bridge.py
  ├── Call JobManager.submit_job(job_data)  ← reuse existing pipeline
  ├── Save automation_meta.json in jobs_data/{job_id}/
        │
        ▼
Existing Pipeline runs normally:
  PREPARING → TRANSCRIBING → ANALYZING → CUTTING → COMPLETE
        │
        ▼
log_collector.py
  ├── Hook into job status update callback
  ├── Collect log per stage
  ├── Save to jobs_data/{job_id}/automation_logs.json
        │
        ▼
GET /api/v1/jobs/{id}
  ├── Read metadata.json (status, progress)
  ├── Read automation_logs.json (detailed log)
  ├── Read clips_result.json (when complete)
  └── Return structured response
```

### Bridge Pattern Detail

`pipeline_bridge.py` converts automation API parameters to the exact format expected by `JobManager.submit_job()`:

| Automation API Field | Pipeline job_data Key | Notes |
|---------------------|----------------------|-------|
| `url` | `url` | Direct mapping |
| `aspect_ratio` | `video_aspect` | Pipeline reads `config.get('video_aspect')`, NOT `aspect_ratio` |
| `subtitle_enabled` | `subtitle_enabled` | Direct mapping |
| `subtitle_style` | `subtitle_style` | Direct mapping |
| `hook_enabled` | — | If false, omit `hook_styles` dict entirely |
| `hook_style` | `hook_styles` | Must construct full dict: `{"hook_style": value}` |
| `max_clips` | `num_clips` | Pipeline reads `num_clips` from config |
| `min_clip_duration` | `min_duration` | Pipeline reads `min_duration` |
| `llm_provider` | `api_provider` | Pipeline reads `api_provider` |
| `api_key` | `api_key` | Direct mapping |
| `transcription_mode` | `transcription_mode` | Values: `fast`, `small`, `accurate` |
| `quality` | `yt_quality` | Direct mapping |
| *(always set)* | `stop_for_review` | Always set to `False` — automation never pauses for review |

**Hook styles dict construction:** When `hook_enabled=true`, the bridge must build a full `hook_styles` dict:
```python
hook_styles = {"hook_style": hook_style_value}
# If hook_style is "preset-2", add preset2_content from user_settings or default
if hook_style == "preset-2":
    hook_styles["preset2_content"] = settings.get("preset2_content", "")
```
All other hook sub-fields (font, color, position, etc.) are populated from `user_settings.json` or use pipeline defaults.

**Default provider resolution:** If `llm_provider` is not specified and `user_settings.json` has no provider, default to `"deepseek"`.

All mappings have defaults. The bridge reads `user_settings.json` for any unspecified provider/key settings.

## API Endpoints

### POST /api/v1/clip — Submit Job

**Request Body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `url` | string | **YES** | — | YouTube video URL |
| `aspect_ratio` | string | no | `"9:16"` | Output aspect ratio (9:16, 16:9, 1:1, 4:5, original) |
| `subtitle_enabled` | bool | no | `true` | Enable subtitle burn-in |
| `subtitle_style` | string | no | `"default"` | Subtitle style preset |
| `hook_enabled` | bool | no | `true` | Enable hook overlay |
| `hook_style` | string | no | `"preset-2"` | Hook preset name |
| `max_clips` | int | no | `5` | Maximum number of clips |
| `min_clip_duration` | int | no | `15` | Minimum clip duration in seconds |
| `max_clip_duration` | int | no | `60` | **Advisory only** — passed to LLM prompt but not enforced by pipeline |
| `llm_provider` | string | no | from settings (default: `deepseek`) | LLM provider for analysis |
| `api_key` | string | no | from settings | LLM API key |
| `transcription_mode` | string | no | `"fast"` | Whisper mode: `fast` (base model), `small`, `accurate` (large-v3) |
| `quality` | string | no | `"720p"` | YouTube download quality (best, 1080p, 720p, 480p) |
| `webhook_url` | string | no | `null` | Callback URL on completion |
| `priority` | int | no | `5` | Queue priority (0=highest, 10=lowest) |

**Response (202 Accepted):**

```json
{
  "success": true,
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "message": "Job queued for processing",
  "status_url": "/api/v1/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

### GET /api/v1/jobs/{job_id} — Job Status

**Response (200 OK):**

```json
{
  "job_id": "uuid",
  "status": "cutting",
  "progress": 85,
  "stage": "cutting",
  "message": "Cutting clip 3 of 5...",
  "submitted_at": "2026-04-21T10:00:00Z",
  "started_at": "2026-04-21T10:00:01Z",
  "updated_at": "2026-04-21T10:05:30Z",
  "source_url": "https://youtube.com/watch?v=xxx",
  "params": {
    "aspect_ratio": "9:16",
    "max_clips": 5
  },
  "priority": 5,
  "logs": [
    {"timestamp": "2026-04-21T10:00:01Z", "stage": "preparing", "level": "info", "message": "Downloading video (720p)..."},
    {"timestamp": "2026-04-21T10:02:30Z", "stage": "preparing", "level": "info", "message": "Download complete: 128MB"},
    {"timestamp": "2026-04-21T10:02:31Z", "stage": "transcribing", "level": "info", "message": "ASR with whisper-base"},
    {"timestamp": "2026-04-21T10:04:00Z", "stage": "transcribing", "level": "info", "message": "ASR done: 142 segments"},
    {"timestamp": "2026-04-21T10:04:05Z", "stage": "analyzing", "level": "info", "message": "Analyzing with deepseek"},
    {"timestamp": "2026-04-21T10:05:00Z", "stage": "analyzing", "level": "info", "message": "Selected 5 clips"},
    {"timestamp": "2026-04-21T10:05:10Z", "stage": "cutting", "level": "info", "message": "Cutting clip 3/5"}
  ],
  "result": null
}
```

When `status` is `"complete"`, the `result` field is populated with clip details (same as `/result` endpoint).

### GET /api/v1/jobs/{job_id}/result — Completed Clips

The router transforms `clips_result.json` entries into the API response format. The raw pipeline output has `path`, `topic`, `reason`, `caption`, `hook_heading`, `hook_subheading`, `duration` (string). The router enriches this with derived fields.

**Response (200 OK, when complete):**

```json
{
  "job_id": "uuid",
  "status": "complete",
  "completed_at": "2026-04-21T10:05:30Z",
  "processing_time_seconds": 330,
  "source_url": "https://youtube.com/watch?v=xxx",
  "clips": [
    {
      "index": 1,
      "filename": "clip_001.mp4",
      "download_url": "/api/v1/download/uuid/clip_001.mp4",
      "duration": 32.5,
      "topic": "Introduction to AI",
      "reason": "Strong hook with engaging opening",
      "caption": "...",
      "hook_heading": "...",
      "hook_subheading": "...",
      "file_size_bytes": 5242880
    }
  ],
  "total_clips": 5,
  "total_duration_seconds": 162.5
}
```

**Transformation rules (clips_result.json → API response):**
- `path` → derive `filename` from basename, construct `download_url` as `/api/v1/download/{job_id}/{filename}`
- `duration` (string) → convert to float
- `file_size_bytes` → read from actual file on disk using `os.path.getsize()`
- `index` → enumerate from 1
- Fields `topic`, `reason`, `caption`, `hook_heading`, `hook_subheading` → pass through directly

**Response (409 Conflict / not ready):**

```json
{
  "success": false,
  "error": {
    "code": "JOB_NOT_COMPLETE",
    "message": "Job is still processing",
    "current_status": "cutting",
    "progress": 85
  }
}
```

### GET /api/v1/jobs — List Jobs

**Query Parameters:** `?status=complete&limit=20&offset=0`

```json
{
  "jobs": [
    {
      "job_id": "uuid",
      "status": "complete",
      "progress": 100,
      "source_url": "https://...",
      "submitted_at": "...",
      "total_clips": 5
    }
  ],
  "total": 42,
  "queue": {
    "pending": 2,
    "processing": 1
  }
}
```

### GET /api/v1/download/{job_id}/{filename} — Download Clip

Streams the clip file as attachment. Resolution logic:
1. Read `jobs_data/{job_id}/clips_result.json` to find clip entries
2. Match `filename` against the basename of each clip's `path` field
3. Resolve the full path using the `path` field from `clips_result.json` (e.g., `clips/{job_id}/clip_001.mp4`)
4. Validate the resolved path is within the allowed clips directory (traversal protection)
5. Stream as `FileResponse` with `media_type="video/mp4"`

### POST /api/v1/jobs/{job_id}/cancel — Cancel Job

```json
{"success": true, "message": "Job cancelled"}
```

### DELETE /api/v1/jobs/{job_id} — Delete Job

Deletes job artifacts (videos, metadata, logs). Returns 200 with confirmation.

### GET /api/v1/pipelines — Pipeline Info

Returns static info about available pipeline stages, default settings, and supported options. Useful for clients to discover capabilities.

## Error Handling

### Error Response Format

All errors return consistent structure:

```json
{
  "success": false,
  "error": {
    "code": "DOWNLOAD_FAILED",
    "message": "Human-readable description",
    "stage": "preparing",
    "job_id": "uuid"
  }
}
```

### Error Codes

| Code | HTTP Status | Stage | Description |
|------|-------------|-------|-------------|
| `INVALID_URL` | 400 | submit | URL is not a valid YouTube link |
| `MISSING_URL` | 400 | submit | No URL provided |
| `DOWNLOAD_FAILED` | 500 | preparing | yt-dlp download error |
| `TRANSCRIBE_FAILED` | 500 | transcribing | Whisper/ASR error |
| `ANALYSIS_FAILED` | 500 | analyzing | LLM call failed (429, invalid key, etc.) |
| `NO_CLIPS_FOUND` | 500 | analyzing | LLM found no viable clips |
| `CUTTING_FAILED` | 500 | cutting | FFmpeg encoding error |
| `JOB_NOT_FOUND` | 404 | status | Job ID does not exist |
| `JOB_NOT_COMPLETE` | 409 | status | Job still processing |
| `JOB_CANCELLED` | 410 | status | Job was cancelled |

## Log Collection

### Log Entry Format

```json
{
  "timestamp": "2026-04-21T10:00:01.234Z",
  "stage": "preparing",
  "level": "info",
  "message": "Description of what happened"
}
```

### Collection Method

`log_collector.py` collects logs by polling `metadata.json` status changes:

- On job submission, save initial log entry to `jobs_data/{job_id}/automation_logs.json`
- `pipeline_bridge.py` provides a status update callback to `JobManager.submit_job()` that:
  1. Receives `(job_id, status, progress, message)` from `JobRunner._job_host.update_job_status()`
  2. Appends a structured log entry to the in-memory log buffer
  3. Periodically flushes to `automation_logs.json`
- On pipeline stage transitions (status changes), capture stage-specific context
- On error, capture error message with `"level": "error"`

**Implementation detail:** The existing `JobRunner` calls `self._job_host.update_job_status()` which updates `metadata.json`. The bridge provides a wrapped callback that both updates metadata AND appends logs. This avoids modifying pipeline internals while capturing all state changes.

### Per-Stage Log Messages

| Stage | Example Messages |
|-------|-----------------|
| preparing | "Downloading video (720p)...", "Download complete: 128MB, 10:23" |
| transcribing | "Starting ASR (whisper-base)", "ASR done: 142 segments, language: en" |
| analyzing | "Analyzing with deepseek, max_clips=5", "Selected 5 clips (2m 15s total)" |
| cutting | "Cutting clip 1/5: 0:12-0:45", "Clip 1/5 done (32s, 5.2MB)", "Cutting clip 3/5..." |
| complete | "All 5 clips ready", "Total processing time: 5m 30s" |

## Webhook Support

When `webhook_url` is provided:

### On Completion

```json
POST {webhook_url}
{
  "event": "job.complete",
  "job_id": "uuid",
  "status": "complete",
  "clips": [
    {"filename": "clip_001.mp4", "download_url": "...", "duration": 32.5}
  ],
  "total_clips": 5,
  "processing_time_seconds": 330
}
```

### On Error

```json
POST {webhook_url}
{
  "event": "job.error",
  "job_id": "uuid",
  "status": "error",
  "error": {
    "code": "ANALYSIS_FAILED",
    "message": "LLM rate limit exceeded"
  }
}
```

### Delivery

- Async delivery via background task (not blocking pipeline)
- 3 retries with exponential backoff (1s, 5s, 15s)
- 10-second timeout per attempt
- Webhook failures are logged but do not affect job status

## Registration in Existing Entry Points

### app.py (Monolith)

```python
from routers.automation import router as automation_router
app.include_router(automation_router, prefix="/api/v1")
```

### app_modular.py (Modular)

```python
from routers.automation import router as automation_router
app.include_router(automation_router, prefix="/api/v1")
```

Both entry points mount the same router, ensuring the automation API is available regardless of which entry is used.

## Testing Strategy

- Unit tests for `models.py` (Pydantic validation)
- Unit tests for `pipeline_bridge.py` (parameter mapping)
- Integration tests for `automation.py` router (using FastAPI TestClient)
- End-to-end test: submit URL → poll status → download clip (requires yt-dlp + FFmpeg)

## Security Considerations

- URL validation: only allow YouTube/supported video platform URLs
- File path traversal protection on download endpoint
- Rate limiting consideration for public-facing deployment
- API key passthrough: never log raw API keys
