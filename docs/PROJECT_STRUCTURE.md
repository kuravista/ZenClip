# ZenClip - Project Structure & Documentation Index

**Last Updated:** 2026-04-15
**Root:** `D:\Extend_C\Program\zenclip\audit\recovery-workspace\`

---

## Folder Structure

```
recovery-workspace/                    # ROOT - Full source project
│
├── docs/                              # DOCUMENTATION (centralized)
│   ├── PROJECT_STRUCTURE.md           # ← You are here (this file)
│   ├── CONTRACT_AUDIT.md              # OpenAPI v1 ↔ modular routes matrix
│   ├── API_REFERENCE.md               # All API endpoints reference
│   ├── ENV_REFERENCE.md               # Environment variables reference
│   ├── CLI_USAGE_GUIDE.md             # CLI script usage (clip_video.py)
│   ├── CONFIG_REFERENCE.md            # Configuration & curl commands
│   ├── HOOK_PRESETS_GUIDE.md          # 4 hook overlay presets guide
│   ├── AI_PROVIDERS_GUIDE.md          # AI provider setup (5 providers)
│   ├── PERFORMANCE_RESEARCH.md        # Pipeline performance analysis
│   ├── OPENROUTER_COST_ANALYSIS.md    # LLM model cost comparison (IDR)
│   └── openrouter_research_results.json  # Raw research data
│
├── backend/                           # PYTHON BACKEND (FastAPI)
│   ├── src/
│   │   ├── app.py                     # Main FastAPI app (entry point)
│   │   ├── app_modular.py             # Modular app (production)
│   │   ├── config.py                  # App configuration
│   │   │
│   │   ├── routers/                   # API route modules
│   │   │   ├── health.py              #   Health check
│   │   │   ├── debug.py               #   Debug endpoints
│   │   │   ├── settings.py            #   Settings management
│   │   │   ├── fonts.py               #   Font management
│   │   │   ├── transcript.py          #   Transcript endpoints
│   │   │   ├── gallery.py             #   Video gallery
│   │   │   ├── processing.py          #   Video processing
│   │   │   └── youtube.py             #   YouTube preview & download
│   │   │
│   │   ├── services/
│   │   │   ├── ai/
│   │   │   │   ├── llm_provider.py    #   Unified LLM (5 providers)
│   │   │   │   ├── llm_analyzer.py    #   Clip analysis via LLM
│   │   │   │   ├── genre_detection.py #   Genre detection
│   │   │   │   ├── llm.py             #   Legacy LLM wrapper
│   │   │   │   └── smart_metadata.py  #   Smart metadata generation
│   │   │   │
│   │   │   ├── core/
│   │   │   │   ├── job_manager.py     #   Job state management
│   │   │   │   ├── job_runner.py      #   Pipeline runner (6 stages)
│   │   │   │   ├── job_database.py    #   SQLite job persistence
│   │   │   │   ├── gallery_cache.py   #   Gallery cache manager
│   │   │   │   ├── binary_manager.py  #   FFmpeg/FFprobe manager
│   │   │   │   ├── cache.py           #   Response caching
│   │   │   │   ├── state.py           #   App state management
│   │   │   │   └── resource_monitor.py#   RAM/CPU monitoring
│   │   │   │
│   │   │   └── media/
│   │   │       ├── yt_downloader.py   #   YouTube download (yt-dlp)
│   │   │       ├── video_cutter.py    #   Video cutting & rendering
│   │   │       ├── video_encoder.py   #   Video encoding (FFmpeg)
│   │   │       ├── audio_transcriber.py#  ASR (Faster Whisper)
│   │   │       ├── asr_provider.py    #   ASR provider abstraction
│   │   │       ├── face_detector.py   #   Face detection (OpenCV)
│   │   │       ├── smart_crop.py      #   Smart crop / face tracking
│   │   │       ├── font_manager.py    #   Font management
│   │   │       ├── time_alignment.py  #   Time alignment utility
│   │   │       └── subtitle/          #   Subtitle & hook overlays
│   │   │           ├── generator.py   #     Main subtitle generator
│   │   │           ├── ass_generator.py#    ASS file generator
│   │   │           ├── preset2_hook.py #     Glow text hook (Preset 2)
│   │   │           ├── preset3_hook.py #     Viral stack hook (Preset 3)
│   │   │           ├── preset4_hook.py #     Simple box hook (Preset 4)
│   │   │           ├── styles/        #     Subtitle style modules
│   │   │           │   ├── boxies.py  #       Box style
│   │   │           │   ├── elegant.py #       Elegant style
│   │   │           │   ├── karaoke.py #       Karaoke style
│   │   │           │   ├── mozi.py    #       Mozi style
│   │   │           │   ├── pod_d.py   #       Pod-D style
│   │   │           │   ├── rapid_fire.py #    Rapid Fire style
│   │   │           │   ├── rapid_pro.py #     Rapid Pro style
│   │   │           │   └── shadow.py  #       Shadow style
│   │   │           └── utils/         #     Subtitle utilities
│   │   │               ├── color.py   #       Color helpers
│   │   │               ├── fonts.py   #       Font helpers
│   │   │               ├── image.py   #       Image helpers
│   │   │               └── text.py    #       Text helpers
│   │   │
│   │   ├── utils/
│   │   │   ├── encoding_fix.py        #   UTF-8 encoding fix
│   │   │   ├── logger.py              #   Logging utility
│   │   │   ├── secret_store.py        #   DPAPI secure storage
│   │   │   └── path_validator.py      #   Path validation
│   │   │
│   │   ├── tests/                     # Test & research scripts
│   │   │   ├── research_openrouter_models.py  # LLM comparison
│   │   │   ├── test_preset2.py
│   │   │   ├── test_preset2_video.py
│   │   │   ├── test_real_video.py
│   │   │   ├── test_subtitles.py
│   │   │   └── ...
│   │   │
│   │   └── bin/                       # Binary tools (FFmpeg, etc.)
│   │
│   ├── runtime/                       # Runtime data directory
│   │   ├── data/                      #   App data
│   │   ├── logs/                      #   Application logs
│   │   ├── downloads/                 #   Downloaded videos
│   │   ├── uploads/                   #   Uploaded videos
│   │   └── mod/                       #   Module data
│   │
│   ├── jobs_data/                     # Job processing data (17 jobs)
│   ├── cache/                         # Processing cache
│   ├── static/                        # Static assets
│   │   ├── background/                #   Background images
│   │   ├── clips/                     #   Output clips
│   │   ├── fonts/                     #   System fonts
│   │   ├── fonts_custom/              #   Custom fonts
│   │   └── thumbnails/                #   Video thumbnails
│   ├── templates/                     # HTML templates
│   ├── uploads/                       # Upload directory
│   ├── downloads/                     # Download directory
│   └── .venv/                         # Python virtual environment
│
├── zenclip-studio/                  # ELECTRON DESKTOP APP
│   ├── electron/
│   │   └── src/
│   │       └── main.py                # Electron main process
│   ├── frontend/
│   │   └── src/
│   │       └── components/            # React UI components
│   ├── scripts/                       # CLI scripts
│   │   └── clip_video.py             #   Main CLI tool
│   ├── backend/                       # Production backend copy
│   ├── docs/                          # (empty - centralized to docs/)
│   ├── README.md                      # App README
│   └── .github/workflows/             # CI/CD
│
├── frontend-reconstructed/            # LEGACY FRONTEND (reference only)
│   ├── app.js
│   ├── index.html
│   ├── styles.css
│   └── components/                    # Original UI components
│
├── static/                            # SHARED STATIC FILES
└── downloads/                         # SHARED DOWNLOADS
```

---

## Architecture Overview

### Modular backend (composition root)

The preferred HTTP entry for new work is [`app_modular.py`](../backend/src/app_modular.py): the app sets `app.state.job_commands` from [`wiring.py`](../backend/src/services/core/wiring.py) (`build_default_job_command_port`). Routers obtain `JobCommandPort` via [`deps.py`](../backend/src/routers/deps.py) (`Depends(get_job_commands)`) instead of importing the `job_manager` singleton. Job JSON on disk is mirrored into SQLite through composite persistence (see [`composite_metadata_persistence.py`](../backend/src/services/core/composite_metadata_persistence.py)). The monolith [`app.py`](../backend/src/app.py) remains for legacy clients; set environment variable **`CLIP_USE_MODULAR_ENTRY=1`** when launching `app.py` to run `app_modular` instead. Target REST paths live in [`openapi-v1.yaml`](openapi-v1.yaml); current modular paths often differ at the root (see [`CONTRACT_AUDIT.md`](CONTRACT_AUDIT.md)).

### Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Desktop Shell | Electron | 39.6.1 |
| Backend API | Python FastAPI | 0.100+ |
| Frontend UI | React 19 + Radix UI | - |
| AI Transcription | Faster Whisper (base) | CPU mode |
| AI Analysis | Multi-provider LLM | 5 providers |
| Video Processing | MoviePy + OpenCV + FFmpeg | - |
| Face Tracking | OpenCV Haar Cascade | ~5.5 fps |

### Pipeline Flow (6 Stages)

```
YouTube URL ──┐
              ├──→ [1. PREPARING] ──→ Download / Receive upload
Upload File ──┘         │
                        ▼
              [2. TRANSCRIBING] ──→ Faster Whisper ASR
                        │
                        ▼
              [3. ANALYZING]   ──→ LLM clip selection
                        │
                        ▼
              [4. CUTTING]     ──→ MoviePy + face tracking
                        │
                        ▼
              [5. PROCESSING]  ──→ Hook overlay + encoding
                        │
                        ▼
              [6. COMPLETE]    ──→ Output clips ready
```

### Port Configuration

| Service | Port | Mode |
|---------|------|------|
| Backend (dev) | 9478 | Development |
| Backend (prod) | 9479 | Production |
| Vite Frontend | 5173 | Development |
| Ollama Local | 11434 | Local LLM |

---

## Documentation Index

### Core Documentation (in `docs/`)

| File | Description | Priority |
|------|-------------|----------|
| `PROJECT_STRUCTURE.md` | This file — project overview & structure | **Start here** |
| `API_V1_SPEC.md` | API v1 target contract, legacy mapping, transcript/clip schemas | **API design** |
| `openapi-v1.yaml` | OpenAPI 3.0 snippet for v1 (Swagger / codegen) | **API design** |
| `CONTRACT_AUDIT.md` | OpenAPI v1 paths vs modular routes + schema notes | **API design** |
| `API_REFERENCE.md` | All REST API endpoints | Developer reference |
| `ENV_REFERENCE.md` | Environment variables | Configuration |
| `CLI_USAGE_GUIDE.md` | CLI script usage (clip_video.py) | Quick start |
| `CONFIG_REFERENCE.md` | Configuration & curl commands | API testing |

### Feature Documentation

| File | Description |
|------|-------------|
| `HOOK_PRESETS_GUIDE.md` | 4 hook overlay presets (Classic, Glow, Viral, Simple) |
| `AI_PROVIDERS_GUIDE.md` | 5 AI provider setup (DeepSeek, OpenAI, Gemini, Anthropic, Ollama) |

### Research & Analysis

| File | Description |
|------|-------------|
| `PERFORMANCE_RESEARCH.md` | Pipeline performance, bottleneck analysis, spec recommendations |
| `OPENROUTER_COST_ANALYSIS.md` | LLM model cost comparison in IDR |
| `openrouter_research_results.json` | Raw data from 9-model LLM comparison |

### Legacy (in `audit/` parent)

| Location | Description |
|----------|-------------|
| `audit/Archives/` | Reverse engineering documents (01-07) |
| `audit/09-GAP-ANALYSIS.md` | Feature gap analysis |
| `audit/10-RE-SUMMARY.md` | RE progress summary (98%) |

---

## AI Provider Summary

| Provider | Model | Cost/Video | Recommended For |
|----------|-------|------------|-----------------|
| **Llama 4 Maverick** | via OpenRouter | Rp 34 | Daily production (best value) |
| **DeepSeek R1** | via OpenRouter | Rp 191 | Balanced quality + cost |
| **Gemini 2.5 Flash** | Google API (free) | Rp 0 | Development & testing |
| **Gemini 2.5 Pro** | via OpenRouter | Rp 1.333 | Premium content |
| DeepSeek V3 | DeepSeek API | Cheap | Budget alternative |
| Claude Sonnet 4 | Anthropic API | Premium | High-quality analysis |
| GPT-4o Mini | OpenAI API | Cheap | **NOT recommended** (0/7 valid) |

---

## Key Technical Notes

1. **Hook styles** must be a dict: `{"hook_style": "preset-2", "preset2_content": "..."}` — NOT a string
2. **Preset 2** uses `preset2_content` with markdown: `**highlight**`, `*italic*`, normal text
3. **Gemini model** is `gemini-2.5-flash` (NOT `gemini-1.5-flash`)
4. **Test video** `teszenclip001.mp4` has NO audio track — ASR cannot work
5. **Face tracking** uses OpenCV Haar Cascade at ~5.5 fps (80% of pipeline time)
6. **RAM** is the primary bottleneck, not GPU (85% Indonesian laptops have no NVIDIA)

---

## Quick Start

```bash
# 1. Start backend
cd recovery-workspace/backend
python src/app.py
# → http://127.0.0.1:9478

# 2. Process a YouTube video
python clip_video.py --youtube "https://youtube.com/watch?v=..." --clips 3 --preset preset-2

# 3. Or upload a local file
curl -X POST http://127.0.0.1:9478/process \
  -F "video=@video.mp4" \
  -F "num_clips=5" \
  -F "min_duration=30"
```

---

*Generated: 2026-04-08*
