# Automation API v1 — ZenClip Studio

REST API untuk automated video clipping. Kirim URL YouTube, sistem otomatis: download → transcribe → LLM analysis → cut → hook overlay → subtitle burn-in → output clips.

**Base URL:** `http://127.0.0.1:9478/api/v1`

---

## Daftar Isi

- [Quick Start](#quick-start)
- [Endpoints](#endpoints)
  - [POST /clip](#post-clip)
  - [GET /jobs/{id}](#get-jobsid)
  - [GET /jobs/{id}/result](#get-jobsidresult)
  - [GET /jobs](#get-jobs)
  - [GET /download/{id}/{file}](#get-downloadidfile)
  - [POST /jobs/{id}/upload-r2](#post-jobsidupload-r2)
  - [POST /jobs/{id}/cancel](#post-jobsidcancel)
  - [DELETE /jobs/{id}](#delete-jobsid)
  - [GET /pipelines](#get-pipelines)
- [Pipeline Stages](#pipeline-stages)
- [Konfigurasi Visual](#konfigurasi-visual)
  - [Hook Defaults](#hook-defaults)
  - [Subtitle Defaults](#subtitle-defaults)
- [Webhook Callbacks](#webhook-callbacks)
- [Font Management](#font-management)
- [Cloudflare R2 Upload](#cloudflare-r2-upload)
- [Watermark & CTA](#watermark--cta)
- [Error Response](#error-response)
- [Contoh Workflow Lengkap](#contoh-workflow-lengkap)

---

## Quick Start

```powershell
# 1. Submit job
curl.exe -X POST http://127.0.0.1:9478/api/v1/clip ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://www.youtube.com/watch?v=dQw4w9WgXcQ\"}"

# Response:
# {"success":true,"job_id":"abc-123","message":"Job queued for processing","status_url":"/api/v1/jobs/abc-123"}

# 2. Poll status (ulangi sampai status = "complete")
curl.exe http://127.0.0.1:9478/api/v1/jobs/abc-123

# 3. Download clip
curl.exe -o clip.mp4 http://127.0.0.1:9478/api/v1/download/abc-123/clip_0_Topic.mp4
```

---

## Endpoints

### POST /clip

Submit YouTube URL untuk automated processing.

**Request Body (JSON):**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | string | **required** | YouTube URL. Format: `youtube.com/watch?v=`, `youtu.be/`, `youtube.com/shorts/`, `youtube.com/live/` |
| `aspect_ratio` | string | `"9:16"` | Output aspect ratio. Options: `9:16`, `16:9`, `1:1`, `4:5`, `original` |
| `subtitle_enabled` | bool | `true` | Burn-in subtitles ke clip |
| `subtitle_style` | string | `"word"` | Subtitle style. Options: `shadow`, `elegant`, `boxies`, `mozi`, `pod_d`, `rapid_fire`, `rapid_pro`, `karaoke`, `prince` |
| `hook_enabled` | bool | `true` | Tambah viral hook overlay di awal clip |
| `hook_style` | string | `"preset-2"` | Hook preset. Options: `preset-1` (Classic Box), `preset-2` (Glow Text), `preset-3` (Viral Stack), `preset-4` (Simple Box) |
| `max_clips` | int | `5` | Maksimal clips yang di-generate (1-20) |
| `min_clip_duration` | int | `15` | Durasi minimum per clip dalam detik (5-300) |
| `max_clip_duration` | int | `60` | Durasi maksimum per clip dalam detik (10-600) |
| `llm_provider` | string | dari settings | LLM provider untuk analysis. Options: `openrouter`, `gemini`, `deepseek`, `openai`, `anthropic`, `local` |
| `api_key` | string | dari settings | API key (override dari settings) |
| `transcription_mode` | string | `"fast"` | ASR mode. Options: `fast`, `small`, `accurate` |
| `quality` | string | `"720p"` | Download quality. Options: `best`, `1080p`, `720p`, `480p`, `audio` |
| `webhook_url` | string | `null` | URL untuk callback saat job selesai |
| `priority` | int | `5` | Job priority (0-10, lebih tinggi = lebih diprioritaskan) |
| `watermark_enabled` | bool | `false` | Tambah watermark ke clip |
| `watermark_type` | string | `"text"` | Watermark type: `text`, `image` |
| `watermark_text` | string | `""` | Teks watermark (jika type=text) |
| `watermark_image_path` | string | `null` | Path ke gambar watermark (jika type=image) |
| `watermark_opacity` | float | `0.5` | Opacity watermark (0.0-1.0) |
| `watermark_position` | string | `"bottom_right"` | Posisi: `top_left`, `top_right`, `top_center`, `bottom_left`, `bottom_right`, `bottom_center`, `center` |
| `watermark_size` | float | `0.3` | Ukuran watermark (scale factor 0.01-1.0) |
| `watermark_font` | string | `"Arial-Bold"` | Font watermark teks |
| `cta_enabled` | bool | `false` | Tambah CTA di akhir setiap clip |
| `cta_type` | string | `"image"` | CTA media type: `image` (statis), `video` |
| `cta_path` | string | `null` | Path ke file CTA **atau folder** CTA. Jika folder, sistem random pick satu file per clip. Default: `backend/static/cta-media/` |
| `cta_duration` | float | `5.0` | Durasi CTA dalam detik (1-30) |
| `upload_r2` | bool | `false` | Auto-upload clips ke Cloudflare R2 setelah selesai |
| `r2_folder` | string | `"clips"` | Folder prefix di R2 bucket saat auto-upload |
| `randomize_metadata` | bool | `false` | Randomize video metadata (title, comment, description) untuk menghindari duplikasi di platform |

**Minimal request (hanya URL):**

```powershell
curl.exe -X POST http://127.0.0.1:9478/api/v1/clip ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://www.youtube.com/watch?v=dQw4w9WgXcQ\"}"
```

**Custom parameters:**

```powershell
curl.exe -X POST http://127.0.0.1:9478/api/v1/clip ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://www.youtube.com/watch?v=dQw4w9WgXcQ\",\"max_clips\":3,\"aspect_ratio\":\"16:9\",\"llm_provider\":\"openrouter\",\"subtitle_style\":\"mozi\",\"hook_enabled\":false}"
```

**Explicit API key:**

```powershell
curl.exe -X POST http://127.0.0.1:9478/api/v1/clip ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://www.youtube.com/watch?v=abc\",\"llm_provider\":\"gemini\",\"api_key\":\"AIza...your-key\"}"
```

**With watermark + CTA:**

```powershell
curl.exe -X POST http://127.0.0.1:9478/api/v1/clip ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://www.youtube.com/watch?v=abc\",\"watermark_enabled\":true,\"watermark_text\":\"MYBRAND\",\"watermark_position\":\"bottom_right\",\"watermark_opacity\":0.5,\"cta_enabled\":true,\"cta_type\":\"image\",\"cta_path\":\"C:/cta/subscribe.png\",\"cta_duration\":5.0}"
```

**Response (202 Accepted):**

```json
{
  "success": true,
  "job_id": "49d2da6d-ec7c-4767-8a3b-f3c6a94d9622",
  "message": "Job queued for processing",
  "status_url": "/api/v1/jobs/49d2da6d-ec7c-4767-8a3b-f3c6a94d9622"
}
```

---

### GET /jobs/{id}

Cek status dan progress job.

```powershell
curl.exe http://127.0.0.1:9478/api/v1/jobs/49d2da6d-ec7c-4767-8a3b-f3c6a94d9622
```

**Response (200 OK):**

```json
{
  "job_id": "49d2da6d-ec7c-4767-8a3b-f3c6a94d9622",
  "status": "complete",
  "progress": 100,
  "stage": "complete",
  "message": "Completed! 2 clips in 1m 22s",
  "submitted_at": "2026-04-21T07:11:14.227565+00:00",
  "started_at": null,
  "updated_at": "2026-04-21T07:12:41.127097+00:00",
  "source_url": "https://www.youtube.com/watch?v=lplwONPDUHI",
  "params": {
    "url": "https://www.youtube.com/watch?v=lplwONPDUHI",
    "aspect_ratio": "9:16",
    "subtitle_enabled": true,
    "subtitle_style": "word",
    "hook_enabled": true,
    "hook_style": "preset-2",
    "max_clips": 5,
    "min_clip_duration": 15,
    "max_clip_duration": 60,
    "llm_provider": "openrouter",
    "transcription_mode": "fast",
    "quality": "720p",
    "priority": 5
  },
  "priority": 5,
  "logs": [
    {"timestamp": "2026-04-21T07:11:14.430391+00:00", "stage": "queued", "level": "info", "message": "Job submitted: https://..."}
  ],
  "result": {
    "job_id": "49d2da6d-ec7c-4767-8a3b-f3c6a94d9622",
    "status": "complete",
    "completed_at": "2026-04-21T07:12:41.127097+00:00",
    "processing_time_seconds": 86.9,
    "source_url": "https://www.youtube.com/watch?v=lplwONPDUHI",
    "clips": [
      {
        "index": 1,
        "filename": "clip_0_Criticism_of_Education.mp4",
        "download_url": "/api/v1/download/49d2da6d/clip_0_Criticism_of_Education.mp4",
        "duration": 20.2,
        "topic": "Criticism of Education System",
        "reason": "Relatable criticism of education system",
        "caption": "Pendidikan kita bukan untuk memajukan",
        "hook_heading": "TRUTH ABOUT",
        "hook_subheading": "Pendidikan Kita",
        "file_size_bytes": 7428144
      },
      {
        "index": 2,
        "filename": "clip_1_Digitalization.mp4",
        "download_url": "/api/v1/download/49d2da6d/clip_1_Digitalization.mp4",
        "duration": 26.7,
        "topic": "Digitalization in Education",
        "reason": "Surprising statistic about future jobs",
        "caption": "90% pekerjaan berhubungan dengan digitalisasi",
        "hook_heading": "MASA DEPAN",
        "hook_subheading": "Digitalisasi",
        "file_size_bytes": 9337037
      }
    ],
    "total_clips": 2,
    "total_duration_seconds": 46.9
  }
}
```

**Status values saat polling:**

| Status | Progress | Arti |
|--------|----------|------|
| `queued` | 0% | Job dalam antrian |
| `preparing` | 10% | Download video dari YouTube |
| `transcribing` | 20-40% | ASR mengekstrak transcript |
| `analyzing` | 50-60% | LLM menganalisis dan memilih clip |
| `cutting` | 70-90% | FFmpeg cutting, hook overlay, subtitle burn |
| `complete` | 100% | Selesai, clips siap di-download |
| `failed` | - | Job gagal |

**Polling pattern:**

```powershell
# Poll setiap 10 detik sampai complete/failed
$jobId = "abc-123"
do {
  $resp = curl.exe -s http://127.0.0.1:9478/api/v1/jobs/$jobId | ConvertFrom-Json
  Write-Host "Status: $($resp.status) - $($resp.progress)% - $($resp.message)"
  if ($resp.status -notin @("complete","failed")) { Start-Sleep 10 }
} while ($resp.status -notin @("complete","failed"))
```

---

### GET /jobs/{id}/result

Ambil hasil clip saja (hanya jika job complete).

```powershell
curl.exe http://127.0.0.1:9478/api/v1/jobs/49d2da6d-ec7c-4767-8a3b-f3c6a94d9622/result
```

Error jika job belum selesai:

```json
{
  "success": false,
  "error": {
    "code": "JOB_NOT_COMPLETE",
    "message": "Job is still processing",
    "current_status": "analyzing",
    "progress": 60
  }
}
```

---

### GET /jobs

List semua jobs dengan filter opsional.

```powershell
# Semua jobs
curl.exe "http://127.0.0.1:9478/api/v1/jobs"

# Filter by status
curl.exe "http://127.0.0.1:9478/api/v1/jobs?status=complete&limit=10&offset=0"
```

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `status` | string | null | Filter: `queued`, `preparing`, `transcribing`, `analyzing`, `cutting`, `complete`, `failed` |
| `limit` | int | 20 | Maks jobs yang di-return |
| `offset` | int | 0 | Pagination offset |

**Response (200 OK):**

```json
{
  "jobs": [
    {
      "job_id": "49d2da6d-...",
      "status": "complete",
      "progress": 100,
      "source_url": "https://www.youtube.com/watch?v=...",
      "submitted_at": "2026-04-21T07:11:14+00:00",
      "total_clips": 2
    }
  ],
  "total": 15,
  "queue": {
    "pending": 1,
    "processing": 0
  }
}
```

---

### GET /download/{id}/{file}

Download clip file (MP4, H.264 yuv420p).

```powershell
# Download ke file
curl.exe -o my_clip.mp4 http://127.0.0.1:9478/api/v1/download/49d2da6d-ec7c-4767-8a3b-f3c6a94d9622/clip_0_Topic.mp4
```

Filename didapat dari `result.clips[].filename` di response status/result.

---

### POST /jobs/{id}/upload-r2

Upload semua clips dari job yang sudah selesai ke Cloudflare R2 storage. Mengembalikan public URL untuk setiap clip.

**Prasyarat:** Job harus berstatus `complete`.

```powershell
# Upload ke folder default "clips"
curl.exe -X POST http://127.0.0.1:9478/api/v1/jobs/49d2da6d-ec7c-4767-8a3b-f3c6a94d9622/upload-r2

# Upload ke folder custom
curl.exe -X POST "http://127.0.0.1:9478/api/v1/jobs/49d2da6d/upload-r2?folder=my-project"
```

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `folder` | string | `"clips"` | Folder prefix di R2 bucket |

**Response (200 OK):**

```json
{
  "success": true,
  "job_id": "49d2da6d-ec7c-4767-8a3b-f3c6a94d9622",
  "folder": "clips",
  "total_clips": 2,
  "uploaded": 2,
  "errors": 0,
  "skipped": 0,
  "clips": [
    {
      "filename": "clip_0_Criticism_of_Education.mp4",
      "r2_url": "https://pub-d7aed86314e24f0f988cb057c647ad50.r2.dev/clips/clip_0_Criticism_of_Education.mp4",
      "file_size_bytes": 7428144,
      "status": "uploaded"
    },
    {
      "filename": "clip_1_Digitalization.mp4",
      "r2_url": "https://pub-d7aed86314e24f0f988cb057c647ad50.r2.dev/clips/clip_1_Digitalization.mp4",
      "file_size_bytes": 9337037,
      "status": "uploaded"
    }
  ]
}
```

**Error jika job belum selesai (409):**

```json
{
  "success": false,
  "error": {
    "code": "JOB_NOT_COMPLETE",
    "message": "Job must be complete before uploading to R2",
    "current_status": "cutting"
  }
}
```

---

### POST /jobs/{id}/cancel

Batalkan job yang sedang berjalan.

```powershell
curl.exe -X POST http://127.0.0.1:9478/api/v1/jobs/abc-123/cancel
```

Response:

```json
{"success": true, "message": "Job cancelled"}
```

---

### DELETE /jobs/{id}

Hapus job dan semua file artifacts. Auto-cancel jika job masih berjalan.

```powershell
curl.exe -X DELETE http://127.0.0.1:9478/api/v1/jobs/abc-123
```

Response:

```json
{"success": true, "message": "Job abc-123 deleted"}
```

---

### GET /pipelines

Info pipeline stages dan default settings.

```powershell
curl.exe http://127.0.0.1:9478/api/v1/pipelines
```

Response:

```json
{
  "stages": [
    {"name": "preparing", "description": "Download video from YouTube"},
    {"name": "transcribing", "description": "Extract transcript via ASR"},
    {"name": "analyzing", "description": "LLM selects viral clips"},
    {"name": "cutting", "description": "Cut, crop, overlay, burn subtitles"},
    {"name": "complete", "description": "Clips ready for download"}
  ],
  "defaults": {
    "aspect_ratio": "9:16",
    "subtitle_enabled": true,
    "hook_enabled": true,
    "max_clips": 5,
    "min_clip_duration": 15,
    "transcription_mode": "fast",
    "quality": "720p"
  },
  "supported": {
    "aspect_ratios": ["9:16", "16:9", "1:1", "4:5", "original"],
    "transcription_modes": ["fast", "small", "accurate"],
    "qualities": ["best", "1080p", "720p", "480p", "audio"],
    "hook_styles": ["preset-1", "preset-2", "preset-3", "preset-4"]
  }
}
```

---

## Pipeline Stages

```
URL → Download → ASR Transcribe → LLM Analyze → FFmpeg Cut+Overlay+Subtitle → Output Clips
       10%          20-40%            50-60%           70-90%                    100%
```

Setiap stage otomatis:
- Download video dari YouTube (via yt-dlp)
- Transcribe audio via Faster Whisper (ASR)
- LLM menganalisis transcript dan memilih segmen viral
- FFmpeg 2-pass: Pass 1 (crop + scale + hook overlay), Pass 2 (subtitle burn-in)
- Output: H.264 encoded MP4 files, playable di semua player dan browser

---

## Konfigurasi Visual

API menggunakan settings dari `user_settings.json` sebagai default visual. Override settings tanpa edit code:

**File:** `backend/user_settings.json`

### Hook Defaults

```json
{
  "hook_font": "Impact",
  "hook_heading_color": "#FF0000",
  "hook_stroke_color": "#000000",
  "hook_stroke_width": 2,
  "hook_position": "top",
  "hook_font_size": 80,
  "hook_top_font_size": 28,
  "hook_sub_font_size": 35,
  "hook_highlight_color": "#CBFF00"
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `hook_font` | `Impact` | Hook heading font |
| `hook_heading_color` | `#FF0000` | Warna heading |
| `hook_stroke_color` | `#000000` | Warna outline/stroke |
| `hook_stroke_width` | `2` | Ketebalan stroke (0-10) |
| `hook_position` | `top` | Posisi: `top`, `center`, `bottom` |
| `hook_font_size` | `80` | Ukuran font heading (20-200) |
| `hook_top_font_size` | `28` | Ukuran font top text |
| `hook_sub_font_size` | `35` | Ukuran font subheading |
| `hook_highlight_color` | `#CBFF00` | Warna highlight (preset-2) |

### Subtitle Defaults

```json
{
  "defaultSubtitleStyle": "mozi",
  "subtitle_font_family": "Montserrat-Bold",
  "subtitle_font_size": 45,
  "subtitle_text_color": "#FFFF00",
  "subtitle_stroke_color": "#000000",
  "subtitle_stroke_width": 3,
  "subtitle_bg_color": "#2563eb",
  "subtitle_bg_opacity": 0.75,
  "subtitle_position": 75
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `defaultSubtitleStyle` | `word` | Style: `shadow`, `elegant`, `boxies`, `mozi`, `pod_d`, `rapid_fire`, `rapid_pro`, `karaoke`, `prince` |
| `subtitle_font_family` | `Arial` | Font family |
| `subtitle_font_size` | `45` | Ukuran font (10-200) |
| `subtitle_text_color` | `#FFFF00` | Warna teks |
| `subtitle_stroke_color` | `#000000` | Warna outline |
| `subtitle_stroke_width` | `3` | Ketebalan outline (0-10) |
| `subtitle_bg_color` | `#2563eb` | Warna background |
| `subtitle_bg_opacity` | `0.75` | Opacity background (0-1) |
| `subtitle_position` | `75` | Posisi vertikal (0=bawah, 100=atas) |

---

## Webhook Callbacks

Jika `webhook_url` di-set saat submit, sistem akan POST ke URL saat job selesai.

**Submit dengan webhook:**

```powershell
curl.exe -X POST http://127.0.0.1:9478/api/v1/clip ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://youtube.com/watch?v=abc\",\"webhook_url\":\"https://your-server.com/webhook\"}"
```

**Webhook Payload (POST ke webhook_url):**

```json
{
  "event": "job.complete",
  "job_id": "49d2da6d-...",
  "status": "complete",
  "clips": [
    {
      "index": 1,
      "filename": "clip_0_Topic.mp4",
      "download_url": "/api/v1/download/49d2da6d/clip_0_Topic.mp4",
      "duration": 20.2,
      "topic": "Topic Name",
      "caption": "Hook caption"
    }
  ],
  "total_clips": 2,
  "processing_time_seconds": 86.9
}
```

Retry: 3 attempts dengan backoff 1s, 5s.

---

## Font Management

Font di-bundle di folder project, tidak bergantung pada OS system fonts.

**Font folder:** `backend/static/fonts/`

Font yang tersedia:

| Font | File | Kegunaan |
|------|------|----------|
| Montserrat-Regular | `Montserrat-Regular.ttf` / `.otf` | Subtitle style umum |
| Montserrat-Bold | `Montserrat-Bold.ttf` / `.otf` | mozi, karaoke style |
| Montserrat-Black | `Montserrat-Black.ttf` / `.otf` | mozi, karaoke style (bold) |
| Poppins-Regular | `Poppins-Regular.ttf` | shadow, elegant, boxies style |
| Poppins-Bold | `Poppins-Bold.ttf` | prince style |
| Poppins-Black | `Poppins-Black.ttf` | prince style (bold) |
| PlayfairDisplay-Italic | `PlayfairDisplay-Italic.ttf` | elegant, prince style (italic) |
| Anton-Regular | `Anton-Regular.ttf` | Hook heading alternatif |

**Tambah font custom:**

1. Download font `.ttf` atau `.otf` (Google Fonts gratis)
2. Taruh file ke `backend/static/fonts/`
3. Restart backend
4. Font otomatis ter-scan dan bisa dipakai

**API list fonts:**

```powershell
curl.exe http://127.0.0.1:9478/api/fonts
```

---

## Cloudflare R2 Upload

Clips yang sudah selesai bisa di-upload ke Cloudflare R2 untuk mendapat public URL. Berguna untuk sharing, embedding, atau integrasi dengan platform lain.

### Setup R2

**File konfigurasi:** `backend/r2_config.json`

```json
{
  "r2_endpoint": "https://<account-id>.r2.cloudflarestorage.com",
  "r2_access_key": "<access-key-id>",
  "r2_secret_key": "<secret-access-key>",
  "r2_bucket": "ayomain-contents",
  "r2_public_url": "https://pub-<id>.r2.dev"
}
```

| Key | Description | Cara Mendapat |
|-----|-------------|---------------|
| `r2_endpoint` | R2 S3-compatible endpoint | Cloudflare Dashboard → R2 → Manage R2 API → S3 API |
| `r2_access_key` | Access key ID | Create API Token di R2 dashboard |
| `r2_secret_key` | Secret access key | Diberikan saat create token (hanya sekali tampil) |
| `r2_bucket` | Nama bucket | Create bucket di R2 dashboard |
| `r2_public_url` | Public URL untuk akses file | R2 → Bucket → Settings → Public access → Custom domain / r2.dev |

### Workflow: Process → Upload → Share

**Opsi 1: Auto-upload (1 API call)**

Tambah `"upload_r2": true` di request. Setelah clip selesai, otomatis upload ke R2. R2 URL langsung ada di result.

```powershell
# Submit dengan auto R2 upload
$resp = curl.exe -s -X POST http://127.0.0.1:9478/api/v1/clip `
  -H "Content-Type: application/json" `
  -d '{"url":"https://youtube.com/watch?v=abc","upload_r2":true}' | ConvertFrom-Json
$jobId = $resp.job_id

# Poll sampai complete — R2 URL sudah ada di result
do { Start-Sleep 10; $s = curl.exe -s http://127.0.0.1:9478/api/v1/jobs/$jobId | ConvertFrom-Json }
while ($s.status -notin @("complete","failed"))

# R2 URLs langsung di result
foreach ($clip in $s.result.clips) {
  Write-Host "$($clip.filename) → $($clip.r2_url)"
}
```

**Opsi 2: Manual upload (2 API call)**

```powershell
# 1. Submit job
$resp = curl.exe -s -X POST http://127.0.0.1:9478/api/v1/clip `
  -H "Content-Type: application/json" `
  -d '{"url":"https://youtube.com/watch?v=abc"}' | ConvertFrom-Json
$jobId = $resp.job_id

# 2. Tunggu sampai complete
do { Start-Sleep 10; $s = curl.exe -s http://127.0.0.1:9478/api/v1/jobs/$jobId | ConvertFrom-Json }
while ($s.status -notin @("complete","failed"))

# 3. Upload ke R2 manual
$upload = curl.exe -s -X POST http://127.0.0.1:9478/api/v1/jobs/$jobId/upload-r2 | ConvertFrom-Json

# 4. Ambil public URLs
foreach ($clip in $upload.clips) {
  Write-Host "$($clip.filename) → $($clip.r2_url)"
}
```

### Bucket Structure di R2

```
ayomain-contents/
├── clips/
│   ├── clip_0_Topic_Name.mp4
│   ├── clip_1_Another_Topic.mp4
│   └── ...
├── carousel/          ← folder custom via ?folder=carousel
│   └── ...
└── thumbnails/        ← folder custom via ?folder=thumbnails
    └── ...
```

### Dependencies

R2 upload memerlukan `boto3`:

```bash
pip install boto3
```

---

## Watermark & CTA

### Watermark (Text atau Image)

Watermark di-overlay di atas video selama durasi penuh clip.

**Text watermark (contoh):**

```powershell
curl.exe -X POST http://127.0.0.1:9478/api/v1/clip ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://youtube.com/watch?v=abc\",\"watermark_enabled\":true,\"watermark_text\":\"MYBRAND\",\"watermark_position\":\"bottom_right\",\"watermark_opacity\":0.5}"
```

**Image watermark:**

```powershell
curl.exe -X POST http://127.0.0.1:9478/api/v1/clip ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://youtube.com/watch?v=abc\",\"watermark_enabled\":true,\"watermark_type\":\"image\",\"watermark_image_path\":\"C:/logo/watermark.png\",\"watermark_position\":\"bottom_right\",\"watermark_opacity\":0.3}"
```

**Posisi watermark:**

| Value | Posisi |
|-------|--------|
| `top_left` | Kiri atas |
| `top_right` | Kanan atas |
| `top_center` | Tengah atas |
| `bottom_left` | Kiri bawah |
| `bottom_right` | Kanan bawah (default) |
| `bottom_center` | Tengah bawah |
| `center` | Tengah |

### CTA (Call-to-Action)

CTA di-append di **akhir** setiap clip (5-10 detik). Bisa berupa gambar statis atau video pendek.

**Image CTA (gambar statis 5 detik):**

```powershell
curl.exe -X POST http://127.0.0.1:9478/api/v1/clip ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://youtube.com/watch?v=abc\",\"cta_enabled\":true,\"cta_type\":\"image\",\"cta_path\":\"C:/cta/subscribe.png\",\"cta_duration\":5}"
```

**Video CTA (video pendek di akhir clip):**

```powershell
curl.exe -X POST http://127.0.0.1:9478/api/v1/clip ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://youtube.com/watch?v=abc\",\"cta_enabled\":true,\"cta_type\":\"video\",\"cta_path\":\"C:/cta/follow.mp4\",\"cta_duration\":7}"
```

**Semua fitur sekaligus (watermark + CTA + auto R2):**

```powershell
curl.exe -X POST http://127.0.0.1:9478/api/v1/clip ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://youtube.com/watch?v=abc\",\"watermark_enabled\":true,\"watermark_text\":\"BRAND\",\"cta_enabled\":true,\"cta_type\":\"image\",\"cta_path\":\"C:/cta/subscribe.png\",\"cta_duration\":5,\"upload_r2\":true}"
```

**CTA path:** Bisa file tunggal, folder, atau dikosongkan (otomatis pakai `backend/cta-media/`). Untuk setup permanen, simpan path di `user_settings.json` key `cta_path`.

**Random CTA dari folder** (setiap clip dapat CTA berbeda):

Cukup taruh file gambar/video di folder `backend/cta-media/`, lalu aktifkan CTA tanpa perlu specify path:

```powershell
curl.exe -X POST http://127.0.0.1:9478/api/v1/clip ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://youtube.com/watch?v=abc\",\"cta_enabled\":true,\"cta_duration\":5}"
```

Atau specify folder custom:

```powershell
curl.exe -X POST http://127.0.0.1:9478/api/v1/clip ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://youtube.com/watch?v=abc\",\"cta_enabled\":true,\"cta_path\":\"./cta-media/\",\"cta_duration\":5}"
```

Jika `cta_path` berupa **folder/direktori**, sistem akan:
1. Scan semua file gambar (`.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`) dan video (`.mp4`, `.mov`, `.mkv`, `.webm`) di folder tersebut
2. Setiap clip **random pick** satu file berbeda
3. Auto-detect `cta_type` (`image` atau `video`) berdasarkan ekstensi file yang terpilih
4. Parameter `cta_type` diabaikan saat menggunakan folder (otomatis detect)

**Struktur folder project:**
```
backend/
  ├── static/
  │   ├── cta-media/        ← taruh CTA files di sini
  │   │   ├── subscribe.png
  │   │   ├── follow.mp4
  │   │   └── like.jpg
  │   ├── fonts/            ← Built-in fonts (jangan diubah)
  │   └── fonts_custom/     ← Taruh font .ttf/.otf baru di sini
  ├── user_settings.json    ← Edit semua default di sini
  ├── downloads/
  └── src/
```

---

## Error Response

Semua error mengikuti format:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message"
  }
}
```

**Error codes:**

| Code | HTTP | Description |
|------|------|-------------|
| `JOB_NOT_FOUND` | 404 | Job ID tidak ditemukan |
| `JOB_NOT_COMPLETE` | 409 | Job belum selesai (saat akses result) |
| `NO_RESULT` | 404 | Job selesai tapi tidak ada clip hasil |
| Validation error | 422 | Request body tidak valid (field salah/tidak sesuai) |

**Contoh validation error:**

```powershell
# URL tidak valid
curl.exe -X POST http://127.0.0.1:9478/api/v1/clip ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://example.com/not-youtube\"}"

# Response (422):
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "url"],
      "msg": "Value error, URL must be a valid YouTube link",
      "input": "https://example.com/not-youtube"
    }
  ]
}
```

---

## Contoh Workflow Lengkap

### PowerShell Script

```powershell
# ============================================
# ZenClip Automation API - Contoh Workflow
# ============================================

$baseUrl = "http://127.0.0.1:9478/api/v1"
$videoUrl = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# 1. Submit job
Write-Host "Submitting job..." -ForegroundColor Cyan
$body = @{
    url = $videoUrl
    max_clips = 3
    llm_provider = "openrouter"
    aspect_ratio = "9:16"
    subtitle_style = "mozi"
    hook_enabled = $true
} | ConvertTo-Json

$resp = curl.exe -s -X POST "$baseUrl/clip" -H "Content-Type: application/json" -d $body | ConvertFrom-Json
$jobId = $resp.job_id
Write-Host "Job ID: $jobId" -ForegroundColor Green

# 2. Poll sampai selesai
Write-Host "Waiting for completion..." -ForegroundColor Cyan
do {
    Start-Sleep 10
    $status = curl.exe -s "$baseUrl/jobs/$jobId" | ConvertFrom-Json
    Write-Host "  [$($status.progress)%] $($status.status): $($status.message)"
} while ($status.status -notin @("complete", "failed"))

# 3. Download semua clips
if ($status.status -eq "complete") {
    Write-Host "`nDownloading $($status.result.total_clips) clips..." -ForegroundColor Green
    foreach ($clip in $status.result.clips) {
        $outFile = $clip.filename
        Write-Host "  Downloading: $outFile ($($clip.duration)s, topic: $($clip.topic))"
        curl.exe -s -o $outFile "$baseUrl$($clip.download_url)"
    }
    Write-Host "`nDone!" -ForegroundColor Green
} else {
    Write-Host "`nJob failed: $($status.message)" -ForegroundColor Red
}
```

### Python Script

```python
import requests
import time

BASE = "http://127.0.0.1:9478/api/v1"

def clip_video(url, max_clips=3, provider="openrouter"):
    # Submit
    resp = requests.post(f"{BASE}/clip", json={
        "url": url,
        "max_clips": max_clips,
        "llm_provider": provider,
    })
    data = resp.json()
    job_id = data["job_id"]
    print(f"Job submitted: {job_id}")

    # Poll
    while True:
        status = requests.get(f"{BASE}/jobs/{job_id}").json()
        print(f"  [{status['progress']}%] {status['status']}: {status['message']}")
        if status["status"] in ("complete", "failed"):
            break
        time.sleep(10)

    # Download
    if status["status"] == "complete":
        for clip in status["result"]["clips"]:
            filename = clip["filename"]
            print(f"  Downloading: {filename}")
            r = requests.get(f"{BASE}{clip['download_url']}")
            with open(filename, "wb") as f:
                f.write(r.content)
        print(f"Done! {status['result']['total_clips']} clips downloaded.")

    return status

# Usage
clip_video("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
```

### cURL (Bash/Linux)

```bash
#!/bin/bash
BASE="http://127.0.0.1:9478/api/v1"
URL="https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# Submit
JOB_ID=$(curl -s -X POST "$BASE/clip" \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"$URL\",\"max_clips\":3,\"llm_provider\":\"openrouter\"}" \
  | jq -r '.job_id')
echo "Job: $JOB_ID"

# Poll
while true; do
  STATUS=$(curl -s "$BASE/jobs/$JOB_ID")
  ST=$(echo $STATUS | jq -r '.status')
  PROG=$(echo $STATUS | jq -r '.progress')
  MSG=$(echo $STATUS | jq -r '.message')
  echo "  [$PROG%] $ST: $MSG"
  [ "$ST" = "complete" ] || [ "$ST" = "failed" ] && break
  sleep 10
done

# Download clips
echo $STATUS | jq -r '.result.clips[]?.download_url' | while read url; do
  FILE=$(basename "$url")
  echo "  Downloading: $FILE"
  curl -s -o "$FILE" "$BASE$url"
done
echo "Done!"
```

---

## File Referensi

Kalau perlu edit lebih lanjut:

| Tujuan | File |
|--------|------|
| API endpoints (router) | `backend/src/routers/automation.py` |
| Request/response models | `backend/src/services/automation/models.py` |
| Parameter mapping (bridge) | `backend/src/services/automation/pipeline_bridge.py` |
| Default hook visual config | `pipeline_bridge.py` → `DEFAULT_HOOK_STYLES` |
| Default subtitle visual config | `pipeline_bridge.py` → `DEFAULT_SUBTITLE_CONFIG` |
| User settings override | `backend/user_settings.json` |
| Hook rendering (per preset) | `backend/src/services/media/ffmpeg_pipeline.py` |
| Subtitle ASS generation | `backend/src/services/media/subtitle/ass_generator.py` |
| Subtitle shadow/color per style | `ass_generator.py` → `generate_{style}_events()` |
| Font embedding per style | `ass_generator.py` → `style_font_map` |
| Font name → file mapping | `backend/src/services/media/font_manager.py` |
| Font resolution engine | `backend/src/services/media/subtitle/utils/fonts.py` |
| Bundled font files | `backend/static/fonts/*.ttf` |
| CTA append (concat) | `backend/src/services/media/ffmpeg_pipeline.py` → `append_cta_to_clip()` |
| Watermark position mapping | `backend/src/services/media/ffmpeg_filter_builder.py` → `watermark_position_to_xy()` |
| R2 uploader | `backend/src/services/automation/r2_uploader.py` |
| R2 config | `backend/r2_config.json` |
| R2 upload endpoint | `backend/src/routers/automation.py` → `POST /jobs/{id}/upload-r2` |
