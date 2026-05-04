# ZenClip Video Clipper - Usage Guide

## Quick Start

### 1. Start Backend

```bash
cd D:/Extend_C/Program/zenclip/audit/recovery-workspace/backend
python src/app.py
# → Runs on http://127.0.0.1:8000
```

### 2. Clip Video

**Windows Batch:**
```cmd
cd D:/Extend_C/Program/zenclip/audit/recovery-workspace/zenclip-studio/scripts
clip_video.bat "D:\Videos\myvideo.mp4" 3 30
```

**PowerShell:**
```powershell
.\clip_video.ps1 -VideoPath "D:\Videos\myvideo.mp4" -NumClips 3
```

**Python:**
```bash
python clip_video.py "D:\Videos\myvideo.mp4" --clips 3
```

### 2b. YouTube URL → Auto Clips

**Preview metadata (no download):**
```bash
python clip_video.py --youtube "https://www.youtube.com/watch?v=VIDEO_ID" --preview
```

**Download and auto-clip:**
```bash
python clip_video.py --youtube "https://www.youtube.com/watch?v=VIDEO_ID" --quality 720p --clips 3
```

**Quality options:** `best`, `1080p`, `720p`, `480p`, `audio`

### 3. Get Output

```
D:/Extend_C/Program/zenclip/audit/recovery-workspace/static/clips/{job_id}/
```

---

## VERIFIED: Full AI Pipeline

### Whisper ASR + Gemini AI + Video Cutting (2026-04-06)

**Test video:** 10-min Indonesian podcast about trading (test.mp4, 401MB, AAC audio)

| Step | Tool | Time | Output |
|------|------|------|--------|
| 1. Audio extraction | FFmpeg | ~5s | WAV 16kHz mono |
| 2. ASR transcription | Faster Whisper (base) | ~105s | 299 phrases, lang=id |
| 3. AI clip selection | Gemini 2.5 Flash | ~15s | 5 clips with hooks |
| 4. Video cutting | OpenCV face tracking + FFmpeg | ~30min | 5 clips, 193MB |

**AI-Generated Clips:**
| # | Topic | Hook Heading | Duration | Size |
|---|-------|-------------|----------|------|
| 1 | Filosofi trading vs game | GAME VS DIRI | 59s | 37MB |
| 2 | Stop forecasting, cukup bereaksi | JANGAN FORECAST | 36s | 24MB |
| 3 | Tanda-tanda EQ uang rendah | TANDA BAHAYA | 73s | 46MB |
| 4 | Kisah rugi 10 tahun investasi | KISAH NYATA | 79s | 52MB |
| 5 | Konsep wadah uang | WADAH UANG | 57s | 36MB |

### Manual AI Pipeline (when backend doesn't auto-trigger)

```bash
# Step 1: Extract audio
ffmpeg -i "video.mp4" -vn -acodec pcm_s16le -ar 16000 -ac 1 audio.wav

# Step 2: Transcribe
cd audit/recovery-workspace/backend
python -c "
from faster_whisper import WhisperModel
import json
model = WhisperModel('base', device='cpu', compute_type='int8')
segments, info = model.transcribe('audio.wav', beam_size=3, vad_filter=True)
phrases = [{'text': s.text.strip(), 'start': round(s.start, 2), 'end': round(s.end, 2)} for s in segments]
json.dump(phrases, open('transcript.json', 'w'), indent=2, ensure_ascii=False)
print(f'{len(phrases)} phrases, lang={info.language}')
"

# Step 3: Call Gemini for clip selection
python -c "
import json, sys
sys.path.insert(0, 'src')
from services.ai.llm_analyzer import analyze_transcript_with_llm
phrases = json.load(open('transcript.json'))
result = analyze_transcript_with_llm(
    transcript_data=phrases, num_clips=5, min_duration=30,
    video_type='podcast', api_key='YOUR_KEY', api_provider='gemini',
    language='id'
)
json.dump(result, open('clips.json', 'w'), indent=2, ensure_ascii=False)
"

# Step 4: Submit with clips
# POST /manual_transcript_import with phrase_timings + clips_data
```

---

## API Endpoints

### Health Check
```
GET /health
→ {"status":"ok"}
```

### Auto Process (with ASR)
```
POST /process
Content-Type: multipart/form-data

# File mode:
video_file: <file>
num_clips: 3
min_duration: 30
add_subtitles: true
video_aspect: 9:16

# OR YouTube URL mode:
url: https://www.youtube.com/watch?v=VIDEO_ID
yt_quality: 720p
num_clips: 3
min_duration: 30
add_subtitles: true
video_aspect: 9:16
```

### YouTube Preview (metadata only, no download)
```
POST /api/yt-preview
Content-Type: application/json

{"url": "https://www.youtube.com/watch?v=VIDEO_ID"}
→ {"status":"success","metadata":{"title":"...","duration":600,"thumbnail":"...","available_qualities":["best","1080p","720p"]}}
```

### YouTube URL Check
```
GET /api/yt-supported?url=https://...
→ {"supported": true}
```

### Manual Transcript Import (Bypass ASR)
```
POST /manual_transcript_import
Content-Type: application/json

{
  "video_path": "D:/path/to/video.mp4",
  "phrase_timings": [
    {"text": "Hello world", "start": 0.0, "end": 2.5}
  ],
  "clips_data": [
    {
      "start_time": 0,
      "end_time": 30,
      "topic": "Introduction",
      "hook_heading": "Watch This",
      "hook_subheading": "Amazing content"
    }
  ],
  "num_clips": 3,
  "video_aspect": "9:16",
  "add_subtitles": true,
  "add_viral_hook": true,
  "hook_style": "preset2",
  "language": "id",
  "api_provider": "gemini",
  "api_key": "YOUR_KEY"
}
```

### Check Job Status
```
GET /status/{job_id}
→ {"status":"processing","progress":50,"msg":"Processing...","clips":[]}
```

### List Videos
```
GET /api/videos
→ {"clips":[...],"uploads":[...],"downloads":[...]}
```

---

## AI Providers

See [AI_PROVIDERS_GUIDE.md](AI_PROVIDERS_GUIDE.md) for full setup.

| Provider | Model | Cost |
|----------|-------|------|
| DeepSeek | deepseek-chat | $0.001/1K tokens |
| OpenAI | gpt-4o-mini | $0.00015/1K tokens |
| Gemini | gemini-2.5-flash | Free tier |
| Anthropic | claude-3-haiku | $0.00025/1K tokens |
| Local | mistral (Ollama) | Free (needs GPU) |

---

## Common Issues

### ASR Fails (Whisper/CTranslate2 crashes)
**Solution:** Use manual transcript import or run Whisper externally.

### Video has no audio
**Symptom:** ASR returns empty transcript
**Solution:** Cannot use AI pipeline. Use manual clip selection with specific start/end times.

### Gemini returns 404
**Cause:** Wrong model name
**Solution:** Use `gemini-2.5-flash` (NOT `gemini-1.5-flash` or `gemini-pro`)

### Gemini response not parseable
**Cause:** Response has markdown wrapping
**Solution:** Strip `\`\`\`json` and `\`\`\`` before parsing. This is handled automatically in the codebase.

### Job Stuck at 80-85%
**Cause:** Video cutting with face tracking is CPU intensive (~5.5 it/s)
**Solution:** Wait. 60s clip takes ~5-7 min to process.

### Backend Not Starting
```bash
# Kill existing process
taskkill /F /PID $(netstat -ano | grep :8000 | grep LISTEN | awk '{print $5}')

# Or just restart
python src/app.py
```

---

## Project Structure

```
audit/
├── 09-GAP-ANALYSIS.md           # Gap analysis & action plan
├── 10-RE-SUMMARY.md             # RE summary (98% complete)
├── 11-FRONTEND-PARITY.md        # Frontend parity map
├── 12-PACKAGING-GUIDE.md        # Build/packaging guide
├── Archives/                    # Archived RE process (not needed)
└── recovery-workspace/          # CORE PROJECT
    ├── backend/                 # Python FastAPI
    │   ├── src/
    │   │   ├── app.py           # Main app (2225 lines)
    │   │   ├── app_modular.py   # Modular version
    │   │   ├── config.py        # Centralized config
    │   │   ├── routers/         # 8 router modules
    │   │   ├── services/
    │   │   │   ├── ai/          # 5 LLM providers + analyzer
    │   │   │   ├── core/        # Job manager, gallery cache, database
    │   │   │   └── media/       # Video cutter, ASR, face detector
    │   │   │       └── subtitle/  # Hook presets 1-4, 8 subtitle styles
    │   │   ├── utils/           # Security helpers
    │   │   └── tests/           # pytest
    │   ├── static/
    │   │   ├── fonts/           # 13 font files
    │   │   ├── background/      # background_hook.png
    │   │   └── clips/           # Output clips
    │   └── jobs_data/           # Job metadata
    ├── zenclip-studio/        # Electron + Frontend + Scripts
    │   ├── electron/            # Electron shell
    │   ├── frontend/            # React UI (Vite + Tailwind)
    │   ├── backend/dist/        # Built Python EXE
    │   └── scripts/             # CLI tools + docs
    │       ├── clip_video.bat
    │       ├── clip_video.ps1
    │       ├── clip_video.py
    │       ├── README.md
    │       ├── AI_PROVIDERS_GUIDE.md
    │       ├── HOOK_PRESETS_GUIDE.md
    │       └── CONFIG_REFERENCE.md
    └── static/                  # Shared static
```

---

*Updated: 2026-04-06*
