# ZenClip API Reference

Complete reference for all API endpoints.

---

## Base URL

```
http://127.0.0.1:8011
```

---

## Health Endpoints

### GET /health
Basic health check.

**Response:**
```json
{
  "status": "ok"
}
```

---

### GET /api/health
Alias for health check.

---

## Settings Endpoints

### GET /api/settings
Get current user settings.

**Response:**
```json
{
  "aspectRatio": "9:16",
  "subtitleStyle": "shadow",
  "addSubtitles": true,
  ...
}
```

---

### PUT /api/settings
Update user settings (merge).

**Request Body:**
```json
{
  "key": "value"
}
```

**Response:**
```json
{
  "status": "success",
  "settings": { ... }
}
```

---

### POST /api/settings/reset
Reset settings to defaults.

**Response:**
```json
{
  "status": "success",
  "settings": { ... }
}
```

---

## Font Endpoints

### GET /api/fonts
List available fonts.

**Response:**
```json
{
  "fonts": [
    {
      "name": "Arial",
      "filename": "Arial.ttf",
      "path": "/fonts/Arial.ttf",
      "extension": ".ttf"
    }
  ]
}
```

---

### POST /api/fonts/upload
Upload a new font.

**Request:**
- Content-Type: multipart/form-data
- file: font file (.ttf, .otf, .woff, .woff2)

**Response:**
```json
{
  "status": "success",
  "filename": "FontName.ttf"
}
```

---

### DELETE /api/fonts/{filename}
Delete a font.

**Response:**
```json
{
  "status": "success",
  "message": "Font {filename} deleted"
}
```

---

## Processing Endpoints

### POST /process
Process a video file.

**Request:**
- Content-Type: multipart/form-data
- video: video file
- aspect_ratio: string (default: "9:16")
- subtitle_style: string (default: "shadow")
- hook_style: string (default: "preset2")
- add_subtitles: boolean (default: true)
- add_hook: boolean (default: true)
- add_watermark: boolean (default: false)

**Response:**
```json
{
  "status": "success",
  "job_id": "uuid-string"
}
```

---

### GET /status/{job_id}
Get job status.

**Response:**
```json
{
  "job_id": "uuid",
  "status": "processing",
  "progress": 45,
  "current_step": "transcribing"
}
```

**Status Values:**
- `queued` - Job is waiting to be processed
- `preparing` - Preparing video
- `transcribing` - Transcribing audio
- `analyzing` - Analyzing transcript
- `cutting` - Cutting clips
- `complete` - Job completed
- `error` - Job failed
- `cancelled` - Job was cancelled
- `waiting_review` - Waiting for transcript review

---

### POST /api/cancel_job/{job_id}
Cancel a running job.

**Response:**
```json
{
  "status": "success",
  "message": "Job cancellation requested"
}
```

---

## Transcript Endpoints

### POST /extract_transcript
Extract transcript from video.

**Request:**
- Content-Type: multipart/form-data
- video: video file
- stop_for_review: boolean (default: false)

**Response:**
```json
{
  "status": "success",
  "job_id": "uuid-string"
}
```

---

### GET /get_transcript/{job_id}
Get transcript for a job.

**Response:**
```json
{
  "job_id": "uuid",
  "transcript": [
    {
      "text": "Hello world",
      "start": 0.0,
      "end": 2.0,
      "words": [...]
    }
  ],
  "language": "en"
}
```

---

### POST /process_with_transcript
Resume job with edited transcript.

**Request Body:**
```json
{
  "job_id": "uuid",
  "edited_transcript": [...],
  "edited_clips": [...]
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Job resumed"
}
```

---

### POST /manual_transcript_import
Import transcript manually (bypass ASR).

**Request Body:**
```json
{
  "video_path": "/path/to/video.mp4",
  "phrase_timings": [...],
  "clips_data": [...]
}
```

**Response:**
```json
{
  "status": "success",
  "job_id": "uuid-string"
}
```

---

### POST /auto_fix_transcript
Auto-fix transcript typos using LLM.

**Request Body:**
```json
{
  "transcript": [...]
}
```

**Response:**
```json
{
  "status": "success",
  "transcript": [...]
}
```

---

## Gallery Endpoints

### GET /api/videos
Get gallery videos.

**Response:**
```json
{
  "videos": [
    {
      "name": "video1.mp4",
      "path": "/clips/video1.mp4",
      "duration": 30,
      "thumbnail": "/thumbnails/video1.jpg"
    }
  ]
}
```

---

### DELETE /api/videos
Delete selected videos.

**Request Body:**
```json
{
  "paths": ["/clips/video1.mp4", "/clips/video2.mp4"]
}
```

**Response:**
```json
{
  "status": "success",
  "deleted": 2
}
```

---

### GET /api/thumbnails/{filename}
Get thumbnail image.

**Response:** Image file (binary)

---

## Debug Endpoints (Requires CLIP_DEBUG=1)

### GET /api/debug/config
Get backend configuration.

**Response:**
```json
{
  "frozen": false,
  "paths": {
    "upload_folder": "uploads",
    "clips_dir": "/path/to/clips",
    ...
  }
}
```

---

### GET /api/settings/debug
Get settings debug info.

**Response:**
```json
{
  "settings_file_path": "/path/to/settings.json",
  "file_exists": true,
  "file_size": 1024,
  ...
}
```

---

## System Endpoints

### GET /api/system-check
Get system information.

**Response:**
```json
{
  "success": true,
  "os": "Windows",
  "cpu": "Intel i7",
  "ram": "16GB",
  "disk": "500GB free"
}
```

---

### GET /api/runtime-probe
Probe ASR runtime status.

**Response:**
```json
{
  "status": "ready",
  "summary": "Whisper runtime available"
}
```

**Status Values:**
- `ready` - ASR available
- `unavailable` - ASR not available
- `unknown` - Could not determine

---

## Error Responses

All errors follow this format:

```json
{
  "error": "Error message",
  "detail": "Additional details (optional)"
}
```

### Common HTTP Status Codes
- `400` - Bad Request (invalid input)
- `403` - Forbidden (not authorized)
- `404` - Not Found
- `500` - Internal Server Error

---

## Rate Limiting

- Max upload size: 500MB
- Max request time: 300 seconds
- Max concurrent jobs: 1

---

## Authentication

Currently no authentication required (localhost only).

API keys are stored in `user_settings.json` (plaintext - security issue).

---

*Last updated: 2026-04-04*
