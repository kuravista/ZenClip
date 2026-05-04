# ZenClip Environment Variables Reference

Complete reference for all environment variables used in the project.

---

## Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CLIP_BACKEND_PORT` | `8011` | Backend server port |
| `CLIP_DEBUG` | `0` | Enable debug mode (1 = enabled) |
| `SNIPIE_DEBUG` | `0` | Enable verbose backend logging |

---

## Path Configuration

### Sidecar Paths

| Variable | Description |
|----------|-------------|
| `CLIP_SIDECAR_DIR` | Sidecar base directory (bundled Python + FFmpeg + CUDA) |
| `CLIP_CUDA_DIR` | CUDA DLLs directory |
| `CLIP_DLL_DIR` | Additional DLL search path for Windows |
| `CLIP_FFMPEG_PATH` | FFmpeg binary path override |

### App Data Paths

| Variable | Description |
|----------|-------------|
| `CLIP_APP_DATA_DIR` | Override app data directory (user settings, jobs, cache) |
| `CLIP_DEFAULT_APP_DATA_DIR` | Default app data directory fallback |
| `CLIP_RECOVERY_SAFE` | Enable safe recovery mode (`1`) |

### Output Paths

| Variable | Default | Description |
|----------|---------|-------------|
| `CLIP_STATIC_DIR` | `static/` | Static files directory |
| `CLIP_TEMPLATES_DIR` | `templates/` | HTML templates directory |
| `CLIP_CLIPS_DIR` | `{app_data}/clips` | Output clips directory |
| `CLIP_FONTS_DIR` | `{app_data}/fonts` | Custom fonts directory |
| `CLIP_BACKGROUND_DIR` | `{app_data}/backgrounds` | Background images directory |
| `CLIP_THUMBNAILS_DIR` | `{app_data}/thumbnails` | Thumbnail cache directory |
| `CLIP_JOBS_DIR` | `{app_data}/jobs_data` | Job metadata directory |
| `CLIP_LEGACY_FONTS_DIR` | - | Legacy fonts route fallback |

---

## LLM Configuration

### DeepSeek API

| Variable | Description |
|----------|-------------|
| `DEEPSEEK_API_KEY` | DeepSeek API key fallback |

### Local LLM (Ollama)

| Variable | Default | Description |
|----------|---------|-------------|
| `LOCAL_LLM_URL` | `http://localhost:11434/v1` | Local LLM endpoint URL |
| `LOCAL_LLM_API_KEY` | `ollama` | Local LLM API key |
| `LOCAL_LLM_MODEL` | `mistral` | Local LLM model name |

---

## Runtime Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PYTHONIOENCODING` | `utf-8` | Python I/O encoding |
| `PYTHONUNBUFFERED` | `1` | Unbuffered Python output |
| `IMAGEIO_FFMPEG_EXE` | - | ImageIO FFmpeg path |
| `FFMPEG_BINARY` | - | Alternative FFmpeg path |
| `FORCE_COLOR` | `1` | Force colored log output |

---

## Content Security Policy

The CSP is defined in `dist/index.html` and allows:

| Origin | Purpose |
|--------|---------|
| `self` | Same-origin requests |
| `unsafe-inline` | Inline scripts |
| `unsafe-eval` | Eval() for bundled code |
| `127.0.0.1` | Local backend |
| `localhost` | Local development |
| `fonts.googleapis.com` | Google Fonts |
| `fonts.gstatic.com` | Google Fonts hosting |
| `hcaptcha.com` | hCaptcha |
| `*.supabase.co` | Supabase |

---

## User Data Storage

### Default Locations (Windows)

```
Documents\SnipieAI\
├── clips\                 # Rendered output clips
├── backgrounds\           # Background images
├── fonts\                # Custom fonts
├── thumbnails\           # Generated thumbnails
├── jobs_data\            # Job metadata
│   └── {job_id}\
│       ├── metadata.json
│       ├── transcript.json
│       ├── analysis.json
│       └── clips_result.json
├── cache\                # Transcript cache (SHA256 keyed)
├── logs\                 # Application logs
│   ├── app.log
│   └── backend.log
└── user_settings.json    # User settings (including API keys!)
```

---

## Security Notes

### ⚠️ API Keys Storage

API keys are currently stored in **plaintext** in `user_settings.json`.

**Recommendation:** Use Windows DPAPI for encryption:
```python
# utils/secret_store.py
import win32crypt

def encrypt_secret(plaintext: str) -> bytes:
    return win32crypt.CryptProtectData(plaintext.encode(), None, None, None, 0, 0)

def decrypt_secret(encrypted: bytes) -> str:
    return win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)[1].decode()
```

### Debug Endpoints

Debug endpoints are now gated by `CLIP_DEBUG=1`:
- `/api/debug/config`
- `/api/settings/debug`

Set `CLIP_DEBUG=1` to enable these endpoints in development.

---

## Usage Examples

### Portable Runtime
```batch
set CLIP_BACKEND_PORT=8011
set CLIP_APP_DATA_DIR=D:\zenclip\runtime\portable\app-data
set CLIP_STATIC_DIR=D:\zenclip\runtime\portable\static
set CLIP_FFMPEG_PATH=D:\zenclip\resources\backend_sidecar\ffmpeg\ffmpeg.exe
python run_backend_safe.py
```

### Development Mode
```batch
set CLIP_DEBUG=1
set SNIPIE_DEBUG=1
python src/app.py
```

### Custom Output Path
```batch
set CLIP_CLIPS_DIR=D:\my_clips
set CLIP_THUMBNAILS_DIR=D:\my_thumbnails
```

---

*Last updated: 2026-04-04*
