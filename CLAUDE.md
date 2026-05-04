# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ZenClip Studio — AI-powered video clipping tool for creating short-form content (TikTok, Reels, Shorts) from long-form videos. Electron desktop app wrapping a Python FastAPI backend + React/TypeScript frontend. Reverse-engineered from Norraclip desktop app.

## Development Commands

### Quick Start
```bash
start-dev.bat          # Backend on :9478, Frontend on :3987, auto-opens browser
stop-dev.bat           # Kills processes on both ports
```

### Backend (Python/FastAPI)
```bash
cd backend
python run_backend.py                                          # Monolith on :9478 (active default)
python -m uvicorn src.app_modular:app --reload --port 8011     # Modular entry (preferred for new work)

# Install dependencies (split by feature)
pip install -r requirements-recovery-core.txt    # FastAPI, yt-dlp, numpy
pip install -r requirements-recovery-media.txt   # Pillow, MoviePy, OpenCV, MediaPipe
pip install -r requirements-recovery-asr.txt     # faster-whisper, ctranslate2

# Tests
pip install -r requirements-test.txt
pytest tests/ -v --cov=src                         # All tests with coverage
pytest tests/test_foo.py::test_bar -v              # Single test
```

### Frontend (React/TypeScript)
```bash
cd zenclip-studio/frontend
npm install && npm run dev     # Vite dev server on :3987
npm run build                  # Production build
npm run test                   # Vitest
npm run lint                   # ESLint
```

### Electron & Full Workspace
```bash
cd zenclip-studio && npm run dev              # Backend + frontend concurrently
cd zenclip-studio/electron && npm run dev     # Electron dev mode
cd zenclip-studio/electron && npm run build:win   # Windows build

# From zenclip-studio/ root:
npm run build            # Build frontend + backend (PyInstaller)
npm run test             # Both test suites
npm run lint             # Frontend lint
```

## Architecture

### Dual Backend Copies
- `backend/src/` — **live development copy** (work here)
- `zenclip-studio/backend/src/` — **Electron-bundled copy** (for packaging/distribution)

Changes in `backend/` must be synced to `zenclip-studio/backend/` before releases.

### Entry Points
- **`app.py`** — Monolith (2270 lines), the active default entry via `run_backend.py`
- **`app_modular.py`** — Modular refactoring using `routers/` and `config.py`. Not yet the default but preferred for new work.

### 6-Stage Video Pipeline
```
Upload/URL → ASR (Faster Whisper) → LLM Analysis (6 providers)
    → Video Cutting (FFmpeg 2-pass) → Hook Overlay → Subtitle Burn-in → Output Clips
```
Stages: PREPARING → TRANSCRIBING → ANALYZING → WAITING_REVIEW → CUTTING → COMPLETE. Each checks for cancellation and supports resume from artifacts.

### 2-Pass FFmpeg Approach
1. **PASS1**: Crop (9:16/16:9/1:1) + scale + hook overlay → intermediate video
2. **PASS2**: Subtitle burn-in via ASS file → final clip

### Backend Service Layers
- **`routers/`** — 8 domain-specific API modules (health, settings, fonts, gallery, processing, transcript, youtube, debug)
- **`services/ai/`** — 6 LLM providers with automatic fallback to OpenRouter on 429/5xx. Analyzer, genre detection, smart metadata
- **`services/core/`** — Job management (queue, runner, SQLite database), gallery cache, resource monitor. Uses `Protocol` interfaces for SOLID dependency inversion via `ports/protocols.py` and composition root in `wiring.py`
- **`services/media/`** — Video processing: ASR (Faster Whisper), face detection (OpenCV Haar cascades at ~5.5 fps), smart crop, video encoder, font manager, subtitle system

### Frontend
React 19 + Radix UI + Tailwind CSS, built with Vite 5. Vite proxies `/api`, `/status`, `/process`, `/health` to backend. Main components: `ProcessForm`, `GalleryGrid`, `TranscriptEditor`, `SettingsPanel`, `JobStatusPanel`.

## Ports

| Service | Port | Notes |
|---------|------|-------|
| Backend (active) | **9478** | `app.py` via `run_backend.py` |
| Backend (modular) | 9479 | `app_modular.py` via root `package.json` |
| Frontend (Vite) | **3987** | Proxies to backend |

**Port mismatch warning**: Frontend `App.tsx` hardcodes `http://127.0.0.1:9478`. Always use `start-dev.bat` or `run_backend.py` to ensure consistency.

## Key Technical Rules

### Subtitle System (ASS format)
- **`\fad`** works reliably — use for fades
- **`\kf`** works for karaoke word-by-word color sweep (PrimaryColour=highlight, SecondaryColour=dim)
- **`\t`** and **`\move`** are **UNRELIABLE** — do NOT use for animations in FFmpeg burn-in
- ASS filename is always `subs.ass` (safe name, no special characters)
- Font files embedded as base64 in ASS `[Fonts]` section

### Hook Presets
`hook_styles` must be a **dict** with `hook_style` key, NOT a string:
```python
{"hook_style": "preset-2", "preset2_content": "This is **amazing**"}
```

### Gemini
Use `gemini-2.5-flash` (NOT `gemini-1.5-flash`). `maxOutputTokens` should be 16384 (not 4096).

### API Key Storage
`user_settings.json` in app data dir. API keys encrypted via DPAPI on Windows (`utils/secret_store.py`).

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `CLIP_DEBUG` | `0` | Enable debug router endpoints |
| `CLIP_BACKEND_PORT` | `8011` (config) / `9478` (app.py) | Server port override |
| `CLIP_USE_MODULAR_ENTRY` | — | Use `app_modular.py` instead of `app.py` |
| `CLIP_APP_DATA_DIR` | `./app-data` (dev) | App data directory |
| `CLIP_FFMPEG_PATH` | auto | FFmpeg binary path |
| `CLIP_SIDECAR_DIR` | auto | Electron sidecar base dir |

## CI/CD
GitHub Actions (`zenclip-studio/.github/workflows/ci.yml`): backend tests → frontend build/lint → Electron builds (Windows/macOS) → release on version tags.

## Specs
- **Python**: 3.10+, **Node**: >=18, **Electron**: 39.x, **React**: 19.x

## Documentation
All docs in `docs/`: `API_REFERENCE.md`, `API_V1_SPEC.md`, `ENV_REFERENCE.md`, `CONFIG_REFERENCE.md`, `AI_PROVIDERS_GUIDE.md`, `HOOK_PRESETS_GUIDE.md`, `TROUBLESHOOTING.md`.
