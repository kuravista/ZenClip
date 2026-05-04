# ZenClip

AI-powered video clipping tool for creating short-form content from long videos.

## Features

- **AI Transcription**: Automatic speech recognition using Faster Whisper
- **Smart Clip Detection**: AI-powered identification of viral moments
- **Subtitle Rendering**: 8 customizable subtitle styles
- **Viral Hooks**: Auto-generated hook text overlays
- **Smart Cropping**: Face-aware video cropping
- **Watermark Support**: Text and image watermarks
- **Gallery Management**: Browse and manage processed clips

## Tech Stack

| Layer | Technology |
|-------|------------|
| Desktop Shell | Electron 39 |
| Backend | Python 3.11 + FastAPI |
| Frontend | React 19 + Radix UI + Tailwind |
| AI/ML | Faster Whisper + DeepSeek API |
| Media | FFmpeg + MoviePy + OpenCV |

## Quick Start

### Prerequisites

- Node.js 18+
- Python 3.11+
- FFmpeg

### Installation

```bash
# Clone the repository
git clone https://github.com/your-repo/zenclip-studio.git
cd zenclip-studio

# Install frontend dependencies
npm install

# Install backend dependencies
cd backend
pip install -r requirements.txt
```

### Development

```bash
# Start backend (from project root)
cd backend
python -m uvicorn src.app_modular:app --reload --port 8011

# Start frontend (new terminal)
cd frontend
npm run dev

# Start electron (new terminal)
cd electron
npm run dev
```

### Production Build

```bash
# Build everything
npm run build

# Or build individually
npm run build:frontend
npm run build:backend
npm run build:electron
```

## Project Structure

```
zenclip-studio/
├── backend/
│   ├── src/
│   │   ├── app_modular.py     # Main FastAPI app
│   │   ├── config.py          # Configuration
│   │   ├── routers/           # API route handlers
│   │   │   ├── health.py
│   │   │   ├── settings.py
│   │   │   ├── fonts.py
│   │   │   ├── gallery.py
│   │   │   ├── processing.py
│   │   │   ├── transcript.py
│   │   │   └── debug.py
│   │   ├── services/          # Business logic
│   │   │   ├── ai/           # LLM integration
│   │   │   ├── core/         # Core services
│   │   │   └── media/        # Media processing
│   │   └── utils/            # Utilities
│   ├── tests/                 # Test files
│   └── requirements.txt       # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── components/        # React components
│   │   ├── hooks/            # Custom hooks
│   │   ├── lib/              # Utilities
│   │   └── styles/           # CSS/Tailwind
│   ├── package.json
│   └── vite.config.ts
├── electron/
│   ├── src/
│   │   ├── main.ts           # Main process
│   │   └── preload.ts        # Preload script
│   └── package.json
├── docs/                      # Documentation
└── scripts/                   # Build scripts
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CLIP_BACKEND_PORT` | `8011` | Backend server port |
| `CLIP_DEBUG` | `0` | Enable debug mode |
| `CLIP_APP_DATA_DIR` | - | App data directory |
| `CLIP_CLIPS_DIR` | - | Clips output directory |
| `CLIP_FFMPEG_PATH` | - | FFmpeg binary path |
| `DEEPSEEK_API_KEY` | - | DeepSeek API key |
| `LOCAL_LLM_URL` | `http://localhost:11434/v1` | Local LLM endpoint |

See [ENV_REFERENCE.md](docs/ENV_REFERENCE.md) for complete documentation.

## API Reference

See [API_REFERENCE.md](docs/API_REFERENCE.md) for complete API documentation.

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/settings` | GET/PUT | User settings |
| `/process` | POST | Process video |
| `/status/{job_id}` | GET | Job status |
| `/api/videos` | GET | List videos |
| `/extract_transcript` | POST | Extract transcript |
| `/manual_transcript_import` | POST | Import transcript |

## Testing

```bash
# Run backend tests
cd backend
pip install -r requirements-test.txt
pytest tests/ -v

# Run frontend tests
cd frontend
npm run test
```

## Security

### API Key Storage

API keys are encrypted using Windows DPAPI on Windows.

```python
from utils.secret_store import set_api_key, get_api_key

# Store securely
set_api_key('deepseek', 'your-api-key')

# Retrieve
key = get_api_key('deepseek')
```

### Debug Mode

Debug endpoints are gated by `CLIP_DEBUG=1`:

```bash
set CLIP_DEBUG=1
python -m uvicorn src.app_modular:app --port 8011
```

## Architecture

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for system design.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Acknowledgments

- Faster Whisper for transcription
- DeepSeek for LLM analysis
- FFmpeg for video processing
- Electron for desktop shell

---

*Generated: 2026-04-04*
