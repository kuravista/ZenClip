import os
import warnings
# Suppress urllib3's NotOpenSSLWarning — harmless on macOS (LibreSSL vs OpenSSL)
warnings.filterwarnings("ignore", message=".*NotOpenSSLWarning.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="urllib3")

# Initialize binary environment first to ensure libraries like moviepy/yt-dlp pick up the correct paths
from services.core import binary_manager 

import time
import json
import uuid
import threading
import glob
import subprocess
import pydantic
from pydantic import BaseModel
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from werkzeug.utils import secure_filename

from services.ai.llm import auto_fix_transcript_with_llm
from services.core.job_manager import job_manager, JobStatus

import traceback
from utils.logger import log

# --- GPU/CUDA Path Injection ---
# Must be done early to ensure DLLs are found
SIDECAR_DIR_ENV = os.environ.get('CLIP_SIDECAR_DIR')
cuda_path = os.environ.get('CLIP_CUDA_DIR')
if not cuda_path and SIDECAR_DIR_ENV:
    cuda_path = os.path.join(SIDECAR_DIR_ENV, 'cuda')
if cuda_path and os.path.exists(cuda_path):
    log.info(f"Adding bundled CUDA to PATH: {cuda_path}", module="App")
    os.environ['PATH'] = cuda_path + os.pathsep + os.environ['PATH']
    # Also needed for some libraries to find dlls
    try:
        os.add_dll_directory(cuda_path)
    except AttributeError:
        pass # add_dll_directory is Python 3.8+ Windows only


# --- Configuration ---
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Debug mode - gate sensitive endpoints
DEBUG_MODE = os.environ.get('CLIP_DEBUG', '0') == '1'

# --- Helper Functions ---
def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def cleanup_old_files(folder, max_age_hours=24):
    """Delete files older than max_age_hours"""
    if not os.path.exists(folder):
        return
    
    now = time.time()
    cutoff = now - (max_age_hours * 3600)
    
    deleted_count = 0
    freed_space = 0
    
    try:
        for filename in os.listdir(folder):
            filepath = os.path.join(folder, filename)
            
            if os.path.isfile(filepath):
                file_age = os.path.getmtime(filepath)
                
                if file_age < cutoff:
                    try:
                        file_size = os.path.getsize(filepath)
                        os.remove(filepath)
                        deleted_count += 1
                        freed_space += file_size
                    except Exception as e:
                        log.warn(f"Failed to delete {filename}: {e}", module="Cleanup")
    except Exception as outer_e:
        log.warn(f"Error during cleanup: {outer_e}", module="Cleanup")
    
    if deleted_count > 0:
        log.info(f"Cleanup: deleted {deleted_count} files, freed {freed_space/(1024**2):.1f} MB", module="Cleanup")

def start_cleanup_thread():
    """Start background cleanup tasks"""
    def cleanup_loop():
        while True:
            time.sleep(3600)  # 1 hour
            cleanup_old_files(UPLOAD_FOLDER, max_age_hours=168) # 1 week (was 1 hour)
            # Ensure these directories exist before cleaning
            if os.path.exists('downloads'):
                 cleanup_old_files('downloads', max_age_hours=48)
            if os.path.exists(CLIPS_DIR):
                 cleanup_old_files(CLIPS_DIR, max_age_hours=168) # 1 week
    
    thread = threading.Thread(target=cleanup_loop, daemon=True)
    thread.start()


_runtime_probe_cache = {
    "timestamp": 0.0,
    "payload": None,
}


def probe_transcription_runtime(force: bool = False) -> Dict[str, Any]:
    ttl_seconds = 45
    now = time.time()
    cached_payload = _runtime_probe_cache["payload"]

    if not force and cached_payload and (now - _runtime_probe_cache["timestamp"] < ttl_seconds):
        return cached_payload

    probe_code = """
import json

result = {
    "imports_ok": False,
    "cuda_devices": None,
    "cpu_probe": "not_run",
    "cpu_probe_error": None,
    "import_error": None,
}

try:
    from faster_whisper import WhisperModel
    import ctranslate2
    result["imports_ok"] = True
    try:
        result["cuda_devices"] = ctranslate2.get_cuda_device_count()
    except Exception as exc:
        result["cuda_devices_error"] = str(exc)
    try:
        WhisperModel("base", device="cpu", compute_type="float32", num_workers=1)
        result["cpu_probe"] = "loaded"
    except Exception as exc:
        result["cpu_probe"] = "error"
        result["cpu_probe_error"] = str(exc)
except Exception as exc:
    result["import_error"] = str(exc)

print(json.dumps(result))
"""

    payload: Dict[str, Any] = {
        "status": "unknown",
        "transcript_available": False,
        "processing_available": False,
        "recovery_safe": os.environ.get("CLIP_RECOVERY_SAFE") == "1",
        "summary": "Runtime probe has not completed yet.",
        "recommendation": "Try the probe again after the backend finishes starting.",
        "details": {},
    }

    try:
        completed = subprocess.run(
            [sys.executable, "-c", probe_code],
            capture_output=True,
            text=True,
            cwd=os.getcwd(),
            env=os.environ.copy(),
            timeout=8,
            check=False,
        )
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()

        details = {}
        if stdout:
            try:
                details = json.loads(stdout.splitlines()[-1])
            except json.JSONDecodeError:
                details = {"raw_stdout": stdout}

        if stderr:
            details["stderr"] = stderr

        imports_ok = bool(details.get("imports_ok"))
        cpu_probe = details.get("cpu_probe")
        transcript_available = imports_ok and cpu_probe == "loaded"

        if transcript_available:
            status = "ready"
            summary = "Bundled Whisper runtime passed the CPU probe."
            recommendation = "Transcript extraction and full processing should be available."
        elif completed.returncode != 0 and not details:
            status = "unavailable"
            summary = "Bundled Whisper runtime terminated during the recovery probe."
            recommendation = "Transcript extraction is disabled on this host until the bundled CTranslate2/OpenMP runtime is repaired or replaced."
        elif imports_ok:
            status = "unavailable"
            summary = "Bundled Whisper runtime imports, but CPU model loading is unstable on this host."
            recommendation = "Keep transcript work in manual-review mode or replace the bundled CTranslate2 runtime."
        else:
            status = "unavailable"
            summary = "Bundled Whisper runtime could not be imported in the recovery backend."
            recommendation = "Repair the sidecar Python environment before using transcript-dependent flows."

        payload = {
            "status": status,
            "transcript_available": transcript_available,
            "processing_available": transcript_available,
            "recovery_safe": os.environ.get("CLIP_RECOVERY_SAFE") == "1",
            "summary": summary,
            "recommendation": recommendation,
            "details": details,
        }
    except subprocess.TimeoutExpired:
        payload = {
            "status": "unavailable",
            "transcript_available": False,
            "processing_available": False,
            "recovery_safe": os.environ.get("CLIP_RECOVERY_SAFE") == "1",
            "summary": "Bundled Whisper runtime stalled during the CPU probe.",
            "recommendation": "Transcript extraction is disabled on this host until the CTranslate2/OpenMP runtime is replaced or repaired.",
            "details": {
                "imports_ok": True,
                "cpu_probe": "timeout",
            },
        }
    except Exception as exc:
        payload = {
            "status": "unknown",
            "transcript_available": False,
            "processing_available": False,
            "recovery_safe": os.environ.get("CLIP_RECOVERY_SAFE") == "1",
            "summary": "Runtime probe failed unexpectedly.",
            "recommendation": "Inspect backend logs before using transcript-dependent flows.",
            "details": {
                "probe_error": str(exc),
            },
        }

    _runtime_probe_cache["timestamp"] = now
    _runtime_probe_cache["payload"] = payload
    return payload


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pick_value(item: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for key in keys:
        if key in item and item[key] not in [None, '']:
            return item[key]
    return default


def normalize_phrase_timings_payload(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    normalized = []
    warnings = []

    for index, raw in enumerate(items or [], start=1):
        if not isinstance(raw, dict):
            warnings.append(f"phrase_timings[{index}] skipped: item is not an object")
            continue

        text = _pick_value(raw, ['text', 'caption', 'content', 'transcript', 'phrase', 'line'], '').strip()
        start = _coerce_float(_pick_value(raw, ['start', 'start_time', 'begin', 'from', 'offset']))
        end = _coerce_float(_pick_value(raw, ['end', 'end_time', 'finish', 'to']))
        duration = _coerce_float(_pick_value(raw, ['duration', 'length']))

        if end is None and start is not None and duration is not None:
            end = start + duration

        if not text:
            warnings.append(f"phrase_timings[{index}] skipped: text is missing")
            continue
        if start is None or end is None:
            warnings.append(f"phrase_timings[{index}] skipped: start/end is missing")
            continue
        if end < start:
            warnings.append(f"phrase_timings[{index}] skipped: end precedes start")
            continue

        normalized.append({
            'text': text,
            'start': round(start, 3),
            'end': round(end, 3),
        })

    return {
        'items': normalized,
        'warnings': warnings,
    }


def normalize_clips_payload(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    normalized = []
    warnings = []

    for index, raw in enumerate(items or [], start=1):
        if not isinstance(raw, dict):
            warnings.append(f"clips_data[{index}] skipped: item is not an object")
            continue

        start_time = _coerce_float(_pick_value(raw, ['start_time', 'start', 'begin', 'from', 'startSeconds']))
        end_time = _coerce_float(_pick_value(raw, ['end_time', 'end', 'finish', 'to', 'endSeconds']))
        duration = _coerce_float(_pick_value(raw, ['duration', 'length']))
        if end_time is None and start_time is not None and duration is not None:
            end_time = start_time + duration

        if start_time is None or end_time is None:
            warnings.append(f"clips_data[{index}] skipped: start/end is missing")
            continue
        if end_time <= start_time:
            warnings.append(f"clips_data[{index}] skipped: end must be greater than start")
            continue

        topic = str(_pick_value(raw, ['topic', 'title', 'label', 'headline'], 'Manual')).strip() or 'Manual'
        reason = str(_pick_value(raw, ['reason', 'description', 'summary'], topic)).strip() or topic
        hook_heading = str(_pick_value(raw, ['hook_heading', 'headline', 'title'], topic)).strip() or topic
        hook_subheading = str(_pick_value(raw, ['hook_subheading', 'subheading', 'subtitle'], '')).strip()
        viral_caption = str(_pick_value(raw, ['viral_caption', 'caption', 'title'], hook_heading)).strip() or hook_heading
        viral_score = _pick_value(raw, ['viral_score', 'score', 'priority'], 100)

        normalized.append({
            'start_time': round(start_time, 3),
            'end_time': round(end_time, 3),
            'topic': topic,
            'viral_score': viral_score,
            'reason': reason,
            'hook_heading': hook_heading,
            'hook_subheading': hook_subheading,
            'viral_caption': viral_caption,
        })

    return {
        'items': normalized,
        'warnings': warnings,
    }

# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    start_cleanup_thread()
    # Ensure static directories exist
    os.makedirs(CLIPS_DIR, exist_ok=True)
    os.makedirs(BACKGROUND_DIR, exist_ok=True)
    os.makedirs(FONTS_DIR, exist_ok=True)
    os.makedirs("downloads", exist_ok=True)
    
    # Copy bundled background to user directory if it doesn't exist (frozen mode)
    if getattr(sys, 'frozen', False):
        bundled_bg = os.path.join(STATIC_DIR, 'background', 'background_hook.png')
        user_bg = os.path.join(BACKGROUND_DIR, 'background_hook.png')
        
        if os.path.exists(bundled_bg) and not os.path.exists(user_bg):
            log.step("Copying hook background to user directory", module="App")
            try:
                import shutil
                shutil.copy2(bundled_bg, user_bg)
                log.success(f"Background copied to: {user_bg}", module="App")
            except Exception as e:
                log.warn(f"Failed to copy background: {e}", module="App")
    
    yield
    
    # Shutdown
    log.info("Application shutting down", module="App")
    
    # 1. Stop Job Manager (Cancel active jobs)
    try:
        log.step("Stopping Job Manager", module="App")
        job_manager.stop_all()  # You'll need to implement this in JobManager or ensure it handles it
    except Exception as e:
        log.warn(f"Error stopping job manager: {e}", module="App")

    # 2. Cleanup Temp Files
    log.step("Cleaning up temporary files", module="App")
    # Add more cleanup logic here if needed (e.g. killing ffmpeg orphans)
    try:
         cleanup_old_files(UPLOAD_FOLDER, max_age_hours=24) # Only cleanup uploads older than 24 hours
    except Exception as e:
         log.warn(f"Cleanup error: {e}", module="App")
    
    log.success("Shutdown complete", module="App")

# --- App Initialization ---
app = FastAPI(lifespan=lifespan)

# Include YouTube preview router
from routers.youtube import router as youtube_router
app.include_router(youtube_router)

# Include Automation API v1 router
from routers.automation import router as automation_router
app.include_router(automation_router, prefix="/api/v1")

@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/runtime-probe")
async def runtime_probe(force: bool = False):
    return probe_transcription_runtime(force=force)

# Add CORS
# Electron packaged renderer uses file:// which sends Origin: null — include it.
# Dev mode uses Vite dev server on localhost:5173.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "null",                    # Electron packaged (file:// origin)
        "http://localhost:5173",   # Vite dev server (original)
        "http://127.0.0.1:5173",
        "http://localhost:3987",   # Vite dev server (current)
        "http://127.0.0.1:3987",
        "http://localhost:9478",
        "http://127.0.0.1:9478",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static & Templates
# Determine if running in frozen mode (PyInstaller)
import sys

# Check if running in Sidecar Mode (Production non-frozen)
# run_backend.py sets CLIP_SIDECAR_DIR
SIDECAR_DIR = os.environ.get('CLIP_SIDECAR_DIR')
OVERRIDE_APP_DATA_DIR = os.environ.get('CLIP_APP_DATA_DIR')
OVERRIDE_STATIC_DIR = os.environ.get('CLIP_STATIC_DIR')
OVERRIDE_TEMPLATES_DIR = os.environ.get('CLIP_TEMPLATES_DIR')
OVERRIDE_CLIPS_DIR = os.environ.get('CLIP_CLIPS_DIR')
OVERRIDE_BACKGROUND_DIR = os.environ.get('CLIP_BACKGROUND_DIR')
OVERRIDE_FONTS_DIR = os.environ.get('CLIP_FONTS_DIR')
OVERRIDE_THUMBNAILS_DIR = os.environ.get('CLIP_THUMBNAILS_DIR')
OVERRIDE_JOBS_DIR = os.environ.get('CLIP_JOBS_DIR')
OVERRIDE_LEGACY_FONTS_DIR = os.environ.get('CLIP_LEGACY_FONTS_DIR')
DEFAULT_APP_DATA_DIR = os.environ.get('CLIP_DEFAULT_APP_DATA_DIR')

from pathlib import Path

def _get_app_data_root() -> Path:
    if OVERRIDE_APP_DATA_DIR:
        return Path(OVERRIDE_APP_DATA_DIR)
    if DEFAULT_APP_DATA_DIR:
        return Path(DEFAULT_APP_DATA_DIR)
    return Path.home() / 'Documents' / 'SnipieAI'

if getattr(sys, 'frozen', False):
    # PyInstaller Bundle Path (Single File EXE)
    BUNDLE_DIR = sys._MEIPASS
    
    STATIC_DIR = OVERRIDE_STATIC_DIR or os.path.join(BUNDLE_DIR, 'static')
    TEMPLATES_DIR = OVERRIDE_TEMPLATES_DIR or os.path.join(BUNDLE_DIR, 'templates')
    
    # User Data — all writable dirs go to ~/Documents/SnipieAI
    app_data_dir = _get_app_data_root()
    
    CLIPS_DIR = OVERRIDE_CLIPS_DIR or str(app_data_dir / 'clips')
    BACKGROUND_DIR = OVERRIDE_BACKGROUND_DIR or str(app_data_dir / 'backgrounds')
    FONTS_DIR = OVERRIDE_FONTS_DIR or str(app_data_dir / 'fonts')
    # Thumbnails must also be writable (STATIC_DIR is bundled/read-only)
    THUMBNAILS_DIR = OVERRIDE_THUMBNAILS_DIR or str(app_data_dir / 'thumbnails')
    
    log.info("Running in frozen (PyInstaller) mode", module="App")
    log.info(f"Static dir: {STATIC_DIR}", module="App")

elif SIDECAR_DIR:
    # Production Sidecar Mode (Bundled Python, but not frozen)
    # Static assets are in sidecar/static (copied by build script) — READ ONLY
    STATIC_DIR = OVERRIDE_STATIC_DIR or os.path.join(SIDECAR_DIR, 'static')
    TEMPLATES_DIR = OVERRIDE_TEMPLATES_DIR or os.path.join(SIDECAR_DIR, 'templates')
    
    # User Data (Same as frozen - write to Documents)
    app_data_dir = _get_app_data_root()
    
    CLIPS_DIR = OVERRIDE_CLIPS_DIR or str(app_data_dir / 'clips')
    BACKGROUND_DIR = OVERRIDE_BACKGROUND_DIR or str(app_data_dir / 'backgrounds')
    FONTS_DIR = OVERRIDE_FONTS_DIR or str(app_data_dir / 'fonts')
    # Thumbnails must also be writable (STATIC_DIR is bundled/read-only)
    THUMBNAILS_DIR = OVERRIDE_THUMBNAILS_DIR or str(app_data_dir / 'thumbnails')
    
    log.info("Running in sidecar mode", module="App")
    log.info(f"Sidecar dir: {SIDECAR_DIR}", module="App")
    log.info(f"Static dir: {STATIC_DIR}", module="App")
    log.info(f"App data dir: {app_data_dir}", module="App")

else:
    # Original Dev Logic
    # Using absolute paths relative to this file to match original structure
    # Backend/src/app.py -> Backend/static and Backend/templates
    BASE_DIR = os.path.dirname(os.path.abspath(__file__)) # Backend/src
    PARENT_DIR = os.path.dirname(BASE_DIR) # Backend
    PROJECT_ROOT = os.path.dirname(PARENT_DIR) # clipiee root

    # Static files are in project root /static directory
    STATIC_DIR = OVERRIDE_STATIC_DIR or os.path.join(PROJECT_ROOT, 'static')
    TEMPLATES_DIR = OVERRIDE_TEMPLATES_DIR or os.path.join(PARENT_DIR, 'templates')
    
    # In dev mode, clips go to static/clips
    CLIPS_DIR = OVERRIDE_CLIPS_DIR or os.path.join(STATIC_DIR, 'clips')
    BACKGROUND_DIR = OVERRIDE_BACKGROUND_DIR or os.path.join(STATIC_DIR, 'background')
    FONTS_DIR = OVERRIDE_FONTS_DIR or os.path.join(STATIC_DIR, 'fonts_custom')
    # Dev thumbnails sit in the static dir (writable in dev)
    THUMBNAILS_DIR = OVERRIDE_THUMBNAILS_DIR or os.path.join(STATIC_DIR, 'thumbnails')
    
    # app_data_dir not set in dev mode; set to None so SETTINGS_FILE block can check it
    app_data_dir = None

LEGACY_FONTS_DIR = OVERRIDE_LEGACY_FONTS_DIR or os.path.join(STATIC_DIR, 'fonts')

# Create if not exist to avoid errors, though they should exist
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(CLIPS_DIR, exist_ok=True)
os.makedirs(BACKGROUND_DIR, exist_ok=True)
os.makedirs(FONTS_DIR, exist_ok=True)
os.makedirs(THUMBNAILS_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/custom_fonts", StaticFiles(directory=FONTS_DIR), name="custom_fonts")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# --- Routes ---

@app.get("/dynamic_fonts.css")
async def dynamic_fonts_css():
    font_files = []
    # Use STATIC_DIR/fonts to match the actual font location
    fonts_dir = os.path.join(STATIC_DIR, 'fonts')
    if os.path.exists(fonts_dir):
        font_files = [f for f in os.listdir(fonts_dir) if f.lower().endswith(('.ttf', '.otf'))]
        font_files.sort()
    
    css_content = []
    for font in font_files:
        # Strip extension first
        font_name = os.path.splitext(font)[0]
        
        # Apply same cleanup as get_available_fonts
        for bad_suffix in [' PERSONAL USE ONLY!', ' DEMO VERSION', ' Demo']:
            if font_name.endswith(bad_suffix):
                font_name = font_name[:-len(bad_suffix)]
                break
                
        css_content.append(f"@font-face {{ font-family: '{font_name}'; src: url('/static/fonts/{font}'); }}")
            
    # Custom Fonts
    if os.path.exists(FONTS_DIR):
        custom_fonts = [f for f in os.listdir(FONTS_DIR) if f.lower().endswith(('.ttf', '.otf', '.woff2'))]
        custom_fonts.sort()
        for font in custom_fonts:
            font_name = os.path.splitext(font)[0]
            # Use /custom_fonts mount point for these files
            css_content.append(f"@font-face {{ font-family: '{font_name}'; src: url('/custom_fonts/{font}'); }}")
            
    return HTMLResponse(content="\n".join(css_content), media_type="text/css")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # List fonts
    font_files = []
    fonts_dir = LEGACY_FONTS_DIR
    if os.path.exists(fonts_dir):
        font_files = [f for f in os.listdir(fonts_dir) if f.lower().endswith(('.ttf', '.otf'))]
        font_files.sort()
    
    return templates.TemplateResponse(request, "index.html", {"fonts": font_files})

@app.get("/fonts/{filename}")
async def serve_fonts(filename: str):
    return FileResponse(os.path.join(LEGACY_FONTS_DIR, filename))

@app.get("/guide", response_class=HTMLResponse)
async def guide(request: Request):
    return templates.TemplateResponse(request, "guide.html", {})

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return templates.TemplateResponse(request, "about.html", {})

@app.get("/about_api", response_class=HTMLResponse)
async def about_api(request: Request):
    return templates.TemplateResponse(request, "about_api.html", {})

# --- Font Library Endpoints ---

@app.post("/api/fonts")
async def upload_font(font_file: UploadFile = File(...)):
    try:
        if not font_file.filename or not font_file.filename.lower().endswith(('.ttf', '.otf')):
            return JSONResponse(status_code=400, content={'error': 'Invalid font file. Only .ttf and .otf allowed'})

        filename = secure_filename(font_file.filename)
        # Use FONTS_DIR (writable) instead of STATIC_DIR (read-only in frozen)
        fonts_dir = FONTS_DIR 
        os.makedirs(fonts_dir, exist_ok=True)
        
        filepath = os.path.join(fonts_dir, filename)
        
        with open(filepath, "wb") as buffer:
            import shutil
            shutil.copyfileobj(font_file.file, buffer)
            
        return {"status": "success", "filename": filename}
    except Exception as e:
        log.error(f"Font upload failed: {e}", module="Fonts")
        return JSONResponse(status_code=500, content={'error': str(e)})

@app.get("/api/fonts")
async def list_fonts():
    try:
        fonts_data = []
        seen_fonts = set()

        # 1. Bundled Fonts (Read-only)
        bundled_fonts_dir = os.path.join(STATIC_DIR, 'fonts')
        if os.path.exists(bundled_fonts_dir):
            for f in os.listdir(bundled_fonts_dir):
                if f.lower().endswith(('.ttf', '.otf')):
                    name = os.path.splitext(f)[0]
                    # Clean up common suffixes
                    for bad_suffix in [' PERSONAL USE ONLY!', ' DEMO VERSION', ' Demo']:
                        if name.endswith(bad_suffix):
                            name = name[:-len(bad_suffix)]

                    if name not in seen_fonts:
                        seen_fonts.add(name)
                        fonts_data.append({
                            "filename": f,
                            "name": name,
                            "url": f"/static/fonts/{f}",
                            "is_custom": False
                        })

        # 2. Custom Fonts (Writable)
        custom_fonts_dir = FONTS_DIR
        if os.path.exists(custom_fonts_dir):
             for f in os.listdir(custom_fonts_dir):
                if f.lower().endswith(('.ttf', '.otf')):
                    name = os.path.splitext(f)[0]
                    # Clean up common suffixes
                    for bad_suffix in [' PERSONAL USE ONLY!', ' DEMO VERSION', ' Demo']:
                        if name.endswith(bad_suffix):
                            name = name[:-len(bad_suffix)]
                    
                    # Custom fonts override bundled ones? Or just add?
                    # Let's add them as separate entries if names differ, or mark as custom
                    # If duplicate name, we might want to prioritize custom or show both
                    # For now, let's show both but maybe append (Custom)?
                    # Ideally, file names are unique enough.
                    
                    fonts_data.append({
                        "filename": f,
                        "name": name, 
                        "url": f"/custom_fonts/{f}", # Note the different URL prefix
                        "is_custom": True
                    })

        # 3. Curated recommended fonts (always available, no file needed)
        _RECOMMENDED = [
            ("Impact", "Built-in"), ("Arial", "Built-in"), ("Arial Black", "Built-in"),
            ("Verdana", "Built-in"), ("Tahoma", "Built-in"), ("Trebuchet MS", "Built-in"),
            ("Georgia", "Built-in"), ("Times New Roman", "Built-in"), ("Courier New", "Built-in"),
            ("Anton", "Google Fonts"), ("Bebas Neue", "Google Fonts"),
            ("Montserrat", "Google Fonts"), ("Montserrat-Black", "Google Fonts"), ("Montserrat-Bold", "Google Fonts"),
            ("Poppins", "Google Fonts"), ("Poppins-Bold", "Google Fonts"), ("Poppins-Black", "Google Fonts"),
            ("Roboto", "Google Fonts"), ("Roboto-Bold", "Google Fonts"),
            ("Oswald", "Google Fonts"), ("Oswald-Bold", "Google Fonts"),
            ("Playfair Display", "Google Fonts"),
        ]
        for name, cat in _RECOMMENDED:
            if name not in seen_fonts:
                seen_fonts.add(name)
                fonts_data.append({"name": name, "category": cat, "is_custom": False})

        # Sort by name
        fonts_data.sort(key=lambda x: x['name'])
            
        return {"fonts": fonts_data}
    except Exception as e:
        log.error(f"List fonts failed: {e}", module="Fonts")
        return JSONResponse(status_code=500, content={'error': str(e)})

@app.delete("/api/fonts/{filename}")
async def delete_font(filename: str):
    try:
        if '..' in filename or filename.startswith('/'):
             return JSONResponse(status_code=403, content={'error': 'Invalid path'})
             
        # Use FONTS_DIR for deletion
        fonts_dir = FONTS_DIR
        file_path = os.path.join(fonts_dir, filename)
        
        # Verify it's within the fonts directory
        real_file = os.path.realpath(file_path)
        real_fonts = os.path.realpath(fonts_dir)
        
        if not real_file.startswith(real_fonts):
             return JSONResponse(status_code=403, content={'error': 'Access denied'})

        if os.path.exists(file_path):
            os.remove(file_path)
            return {"status": "success", "message": "Font deleted"}
        else:
            return JSONResponse(status_code=404, content={'error': 'Font not found'})

    except Exception as e:
        log.error(f"Delete font failed: {e}", module="Fonts")
        return JSONResponse(status_code=500, content={'error': str(e)})

# --- Settings Endpoints ---
# Settings file location - use app data directory for persistence
# In frozen/sidecar mode, app_data_dir is already set above from the path config block.
# In dev mode, use current directory.
if OVERRIDE_APP_DATA_DIR:
    SETTINGS_FILE = str(Path(OVERRIDE_APP_DATA_DIR) / "user_settings.json")
elif DEFAULT_APP_DATA_DIR:
    SETTINGS_FILE = str(Path(DEFAULT_APP_DATA_DIR) / "user_settings.json")
elif getattr(sys, 'frozen', False) or SIDECAR_DIR:
    # Production: use the app_data_dir already established in the path config block above
    # app_data_dir is Documents/SnipieAI (writable, not read-only install dir)
    SETTINGS_FILE = str(app_data_dir / "user_settings.json")
else:
    # Dev mode - use current directory
    SETTINGS_FILE = "user_settings.json"

log.info(f"Settings file: {SETTINGS_FILE}", module="Settings")

@app.get("/api/settings")
async def get_settings():
    
    
    
    if not os.path.exists(SETTINGS_FILE):
        log.debug("Settings file not found, returning defaults", module="Settings")
        return {}
    
    try:
        with open(SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
        
        
        return settings
    except json.JSONDecodeError as e:
        log.error(f"Settings JSON decode error: {e}", module="Settings")
        return {}
    except Exception as e:
        log.error(f"Error reading settings: {e}", module="Settings")
        return {}

@app.post("/api/settings")
async def save_settings(request: Request):
    try:
        data = await request.json()
        
        
        
        
        # Merge with existing if possible
        existing = {}
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r') as f:
                    existing = json.load(f)
                
            except Exception as merge_err:
                log.warn(f"Could not load existing settings: {merge_err}", module="Settings")
                pass
        
        # Merge
        updated = {**existing, **data}
        
        
        # Ensure directory exists (extra safety)
        settings_dir = os.path.dirname(SETTINGS_FILE)
        if settings_dir:
            os.makedirs(settings_dir, exist_ok=True)
        
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(updated, f, indent=2)
        
        # Verify write by reading back
        if os.path.exists(SETTINGS_FILE):
            file_size = os.path.getsize(SETTINGS_FILE)
            
        else:
            log.error("Settings file missing after write!", module="Settings")
            
        return {"status": "success", "settings": updated}
    except Exception as e:
        log.error(f"Error saving settings: {e}", module="Settings")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
@app.delete("/api/settings")
async def reset_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            os.remove(SETTINGS_FILE)
        return {"status": "success", "message": "Settings reset"}
    except Exception as e:
        log.error(f"Error resetting settings: {e}", module="Settings")
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api/settings/debug")
async def debug_settings():
    """Diagnostic endpoint to troubleshoot settings persistence"""
    if not DEBUG_MODE:
        raise HTTPException(status_code=403, detail="Debug endpoints disabled. Set CLIP_DEBUG=1 to enable.")
    try:
        import stat
        from datetime import datetime
        
        debug_info = {
            "settings_file_path": SETTINGS_FILE,
            "file_exists": os.path.exists(SETTINGS_FILE),
            "frozen_mode": getattr(sys, 'frozen', False),
        }
        
        if os.path.exists(SETTINGS_FILE):
            # File info
            file_stat = os.stat(SETTINGS_FILE)
            debug_info["file_size"] = file_stat.st_size
            debug_info["last_modified"] = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            debug_info["permissions"] = oct(stat.S_IMODE(file_stat.st_mode))
            
            # Try reading contents
            try:
                with open(SETTINGS_FILE, 'r') as f:
                    contents = json.load(f)
                debug_info["num_keys"] = len(contents)
                debug_info["keys"] = list(contents.keys())
                debug_info["contents_preview"] = {k: str(v)[:50] for k, v in list(contents.items())[:5]}
            except Exception as read_err:
                debug_info["read_error"] = str(read_err)
        else:
            # Check directory
            settings_dir = os.path.dirname(SETTINGS_FILE)
            if settings_dir:
                debug_info["directory_exists"] = os.path.exists(settings_dir)
                if os.path.exists(settings_dir):
                    dir_stat = os.stat(settings_dir)
                    debug_info["directory_permissions"] = oct(stat.S_IMODE(dir_stat.st_mode))
                    debug_info["directory_writable"] = os.access(settings_dir, os.W_OK)
        
        return debug_info
    except Exception as e:
        log.error(f"Debug endpoint error: {e}", module="App")
        return {"error": str(e)}



from services.core.resource_monitor import get_resource_monitor

@app.get("/api/resources")
async def get_system_resources():
    """Real-time CPU/RAM usage for frontend monitoring."""
    try:
        monitor = get_resource_monitor()
        return monitor.get_system_info()
    except Exception as e:
        return {"error": str(e)}



@app.post("/api/settings/clear-cache")
async def clear_cache():
    import shutil
    try:
        deleted_counts = {}
        
        # Determine base data dir — works in dev, sidecar, and frozen mode
        # In production, user data lives in Documents/SnipieAI (same as jobs/clips/settings)
        if getattr(sys, 'frozen', False) or SIDECAR_DIR or OVERRIDE_APP_DATA_DIR or DEFAULT_APP_DATA_DIR:
            _base_dir = str(_get_app_data_root())
        else:
            # Dev mode: use project root (defined in the else branch above)
            BASE_DIR_HERE = os.path.dirname(os.path.abspath(__file__))
            _base_dir = os.path.dirname(os.path.dirname(BASE_DIR_HERE))  # clipiee root
        
        # Directories to clear
        dirs_to_clear = [
            os.path.join(_base_dir, 'cache'),
            os.path.join(_base_dir, 'jobs_data'),
            os.path.join(_base_dir, 'downloads'),
            CLIPS_DIR,  # Always use the resolved CLIPS_DIR
        ]

        for folder in dirs_to_clear:
            if os.path.exists(folder):
                count = 0
                # Delete contents but keep directory
                for filename in os.listdir(folder):
                    file_path = os.path.join(folder, filename)
                    try:
                        if os.path.isfile(file_path) or os.path.islink(file_path):
                            os.unlink(file_path)
                            count += 1
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                            count += 1
                    except Exception as e:
                        log.warn(f"Failed to delete {file_path}: {e}", module="Cache")
                
                deleted_counts[os.path.basename(folder)] = count
        
        return {
            "status": "success", 
            "message": "Cache cleared successfully",
            "details": deleted_counts
        }
    except Exception as e:
        log.error(f"Error clearing cache: {e}", module="Cache")
        raise HTTPException(status_code=500, detail=str(e))

# --- System Check Endpoint ---
@app.get("/api/system-check")
async def system_check():
    import psutil
    import platform
    
    try:
        # Chipset / Processor Name
        chipset = platform.processor()
        try:
            if platform.system() == "Darwin":
                import subprocess
                command = ["sysctl", "-n", "machdep.cpu.brand_string"]
                chipset = subprocess.check_output(command).strip().decode()
        except:
            pass

        # CPU
        cpu_count = os.cpu_count()
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # RAM
        ram = psutil.virtual_memory()
        ram_total_gb = round(ram.total / (1024**3), 2)
        ram_available_gb = round(ram.available / (1024**3), 2)
        ram_percent = ram.percent
        
        # Disk
        disk = psutil.disk_usage('/')
        disk_total_gb = round(disk.total / (1024**3), 2)
        disk_free_gb = round(disk.free / (1024**3), 2)
        
        return {
            "status": "success",
            "system": {
                "os": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "processor": chipset, # Use the better name
                "chipset": chipset,
                "cpu_count": cpu_count,
                "cpu_usage": cpu_percent,
                "ram_total": ram_total_gb,
                "ram_free": ram_available_gb,
                "ram_usage": ram_percent,
                "disk_total": disk_total_gb,
                "disk_free": disk_free_gb
            }
        }
    except Exception as e:
        log.error(f"System check error: {e}", module="App")
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/process")
async def process_video(
    request: Request,
    video_file: Optional[UploadFile] = File(None),

    num_clips: int = Form(3),
    min_duration: str = Form('30'),
    add_viral_hook: str = Form('false'),
    add_subtitles: str = Form('false'),
    transcription_mode: str = Form('fast'),
    # Manual Cut Params
    manual_cut: str = Form('false'),
    manual_start: str = Form('00:00'),
    manual_end: str = Form('00:30'),
    manual_segments: str = Form('[]'),
    # Viral Hook Params
    hook_font: str = Form('Impact'),
    hook_style: str = Form('preset-1'), # Added missing param
    hook_heading_color: str = Form('#FF0000'),
    hook_position: str = Form('top'),
    hook_top_text: str = Form(''),
    hook_headline: str = Form(''),
    hook_subheading: str = Form(''),
    hook_stroke_width: int = Form(2),
    hook_stroke_color: str = Form('#000000'),
    hook_line_spacing: int = Form(0),
    hook_top_gap: int = Form(10), # Added missing param
    hook_bottom_gap: int = Form(20), # Added missing param
    hook_font_size: int = Form(80),
    hook_top_font_size: int = Form(28),
    hook_sub_font_size: int = Form(35),
    hook_full_duration: str = Form('false'),
    # Preset 2
    hook_preset2_text: str = Form(''),
    hook_highlight_color: str = Form('#CBFF00'),
    # Subtitle Params
    subtitle_font_size: int = Form(45),
    subtitle_text_color: str = Form('#FFFF00'),
    subtitle_stroke_color: str = Form('#000000'),
    subtitle_stroke_width: int = Form(3),
    subtitle_bg_opacity: float = Form(0.75),
    subtitle_font_family: str = Form('Arial'),
    subtitle_style: str = Form('word'),
    subtitle_bg_color: str = Form('#2563eb'),
    glow_enabled: str = Form('false'),
    glow_color: str = Form('#00FF00'),
    glow_intensity: int = Form(2),
    smart_subtitles: str = Form('false'),
    subtitle_position: int = Form(75),
    # Other Params
    video_aspect: str = Form('9:16'),
    video_type: str = Form('general'),
    randomize_metadata: str = Form('false'),
    custom_metadata: str = Form(''),
    api_key: str = Form(''),
    api_provider: str = Form('deepseek'),
    custom_prompt: str = Form(''),
    # Watermark Params
    add_watermark: str = Form('false'),
    watermark_type: str = Form('text'),
    watermark_text: str = Form(''),
    watermark_opacity: float = Form(0.5),
    watermark_position: str = Form('bottom_right'),
    watermark_font: str = Form('Arial-Bold'), # New Param
    watermark_size: float = Form(0.3),
    watermark_image: Optional[UploadFile] = File(None),
    # Encoding Quality Preset (only affects libx264/libx265, not hardware encoders)
    encoding_preset: str = Form('medium'),
    # YouTube / URL download params
    url: Optional[str] = Form(None),
    yt_quality: str = Form('720p')
):
    try:
        log.info(f"Processing video | aspect={video_aspect} hook_font_size={hook_font_size}", module="Process")
        data = {}
        
        # Handle input
        if video_file:
             if not video_file.filename:
                 raise HTTPException(status_code=400, detail='No file selected')
             
             if not allowed_file(video_file.filename):
                 raise HTTPException(status_code=400, detail='Invalid file type. Only MP4, MOV, AVI are allowed')
             
             filename = secure_filename(video_file.filename)
             filepath = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}_{filename}")
             
             with open(filepath, "wb") as buffer:
                 while content := await video_file.read(1024 * 1024): # Read in chunks
                     buffer.write(content)
             
             data['video_file'] = True
             data['filepath'] = filepath
        elif url:
            # YouTube / URL download mode
            from services.media.yt_downloader import YtDownloader
            url = url.strip()
            if not YtDownloader.is_supported_url(url):
                raise HTTPException(status_code=400, detail='Unsupported URL format')
            data['url'] = url
            data['yt_quality'] = yt_quality
            data['download_folder'] = 'downloads'
        else:
             raise HTTPException(status_code=400, detail='No file selected. Please upload a video.')

        # Common Parameters
        data['stop_for_review'] = False
        data['num_clips'] = num_clips
        # Bool conversions
        is_add_subtitles = add_subtitles.lower() == 'true' # Keep temp var if used
        data['add_subtitles'] = is_add_subtitles
        data['add_viral_hook'] = add_viral_hook.lower() == 'true'
        data['add_watermark'] = add_watermark.lower() == 'true'
        data['transcription_mode'] = transcription_mode
        
        # Manual Cut
        data['manual_cut'] = manual_cut.lower() == 'true'
        data['manual_start'] = manual_start
        data['manual_end'] = manual_end
        data['manual_segments'] = manual_segments
        
        # Min Duration Logic (Override for manual cut)
        if data['manual_cut']:
             data['min_duration'] = 0
        else:
             data['min_duration'] = "auto" if min_duration.lower() == "auto" else int(min_duration)
        
        # Hook Styles
        data['hook_styles'] = {}
        if data['add_viral_hook']:
            data['hook_styles'] = {
                'hook_style': hook_style,
                'font': hook_font,
                'color': hook_heading_color,
                'position': hook_position,
                'top_text': hook_top_text,
                'headline': hook_headline,
                'subheading': hook_subheading,
                'stroke_width': hook_stroke_width,
                'stroke_color': hook_stroke_color,
                'line_spacing': hook_line_spacing,
                'top_gap': hook_top_gap, # Added
                'bottom_gap': hook_bottom_gap, # Added
                'font_size': hook_font_size,
                'top_font_size': hook_top_font_size,
                'sub_font_size': hook_sub_font_size,
                'full_duration': hook_full_duration.lower() == 'true',
                # Preset 2
                'preset2_content': hook_preset2_text,
                'highlight_color': hook_highlight_color
            }
        
        # Subtitle Config
        data['subtitle_config'] = None
        if data['add_subtitles']:
            data['subtitle_config'] = {
                'fontsize': subtitle_font_size,
                'color': subtitle_text_color,
                'stroke_color': subtitle_stroke_color,
                'stroke_width': subtitle_stroke_width,
                'bg_opacity': subtitle_bg_opacity,
                'font': subtitle_font_family,
                'style': subtitle_style,
                'bg_color': subtitle_bg_color,
                'glow_enabled': glow_enabled.lower() == 'true',
                'glow_color': glow_color,
                'glow_intensity': glow_intensity,
                'smart_subtitles': smart_subtitles.lower() in ['true', 'on', '1'],
                'vertical_position': subtitle_position,
            }
            
        # Watermark Config
        data['watermark_config'] = {}
        if data['add_watermark']:
            data['watermark_config'] = {
                'watermark_type': watermark_type,
                'watermark_text': watermark_text,
                'watermark_opacity': watermark_opacity,
                'watermark_size': watermark_size,
                'watermark_position': watermark_position,
                'watermark_font': watermark_font
            }
            if watermark_image:
                 watermark_filename = f"watermark_{uuid.uuid4().hex[:8]}_{watermark_image.filename}"
                 watermark_path = os.path.join(UPLOAD_FOLDER, watermark_filename)
                 with open(watermark_path, "wb") as buffer:
                     import shutil
                     shutil.copyfileobj(watermark_image.file, buffer)
                 data['watermark_config']['watermark_image_path'] = watermark_path

        # Other params
        asp = video_aspect.strip().lower()
        if asp not in ['9:16', '16:9', '1:1', '4:5', 'original']: asp = '9:16'
        data['video_aspect'] = asp
        
        data['video_type'] = video_type.strip().lower()
        data['randomize_metadata'] = randomize_metadata.lower() == 'true'
        # Encoding preset — validated to safe values only
        _valid_presets = {'veryslow', 'slow', 'medium', 'fast', 'veryfast', 'ultrafast'}
        data['encoding_preset'] = encoding_preset if encoding_preset in _valid_presets else 'medium'
        data['custom_metadata'] = custom_metadata.strip()
        data['api_key'] = api_key
        data['api_provider'] = api_provider
        data['custom_prompt'] = custom_prompt.strip()

        # Submit Job
        
        try:
            job_id = job_manager.submit_job(data)
            log.success(f"Job submitted: {job_id}", module="Process")
        except Exception as e:
            log.error(f"Job submission failed: {e}", module="Process")
            import traceback
            traceback.print_exc()
            raise
        
        return {"job_id": job_id}

    except HTTPException as he:
        raise he
    except ValueError as e:
        return JSONResponse(status_code=400, content={
            'error': 'Invalid input',
            'details': str(e),
            'suggestion': 'Please check your video settings'
        })
    except Exception as e:
        log.error(f"Server error: {e}", module="Process")
        return JSONResponse(status_code=500, content={
            'error': 'Internal server error',
            'details': str(e),
            'suggestion': 'Please try again or restart the application'
        })

@app.post("/extract_transcript")
async def extract_transcript(
    request: Request,
    video_file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    local_video_path: Optional[str] = Form(None),
    # Params repeated from process...
    # For brevity I'll assume standard params. In FastAPI reuse is cleaner with Dependency classes but keeping it simple.
    num_clips: int = Form(3),
    min_duration: str = Form('30'),
    add_subtitles: str = Form('false'), 
    # Hook Params (add_viral_hook checked below)
    add_viral_hook: str = Form('false'),
    hook_style: str = Form('preset-1'),
    transcription_mode: str = Form('fast'),
    # ... hook params ...
    hook_font: str = Form('Impact'),
    hook_heading_color: str = Form('#FF0000'),
    hook_position: str = Form('top'),
    hook_top_text: str = Form(''),
    hook_headline: str = Form(''),
    hook_subheading: str = Form(''),
    hook_stroke_width: int = Form(2),
    hook_stroke_color: str = Form('#000000'),
    hook_line_spacing: int = Form(0), # Deprecated
    hook_top_gap: int = Form(10),
    hook_bottom_gap: int = Form(20),
    hook_font_size: int = Form(80),
    hook_top_font_size: int = Form(28),
    hook_sub_font_size: int = Form(35),
    hook_full_duration: str = Form('false'),
    # Preset 2 params
    hook_preset2_text: str = Form(''),
    hook_highlight_color: str = Form('#CBFF00'),
    # ... subtitle params ...
    subtitle_font_size: int = Form(40),
    subtitle_text_color: str = Form('#FFFFFF'),
    subtitle_stroke_color: str = Form('#000000'),
    subtitle_stroke_width: int = Form(1),
    subtitle_bg_opacity: float = Form(0.75),
    subtitle_font_family: str = Form('Arial'),
    subtitle_style: str = Form('word'),
    subtitle_bg_color: str = Form('#2563eb'),
    glow_enabled: str = Form('false'),
    glow_color: str = Form('#00FF00'),
    glow_intensity: int = Form(2),
    subtitle_position: int = Form(75),
    smart_subtitles: str = Form('false'),
    
    # Manual Cut Params
    manual_cut: str = Form('false'),
    manual_start: str = Form('00:00'),
    manual_end: str = Form('00:30'),
    manual_segments: str = Form('[]'),

    video_aspect: str = Form('9:16'),
    video_type: str = Form('general'),
    randomize_metadata: str = Form('false'),
    custom_metadata: str = Form(''),
    api_key: str = Form(''),
    api_provider: str = Form('deepseek'),
    custom_prompt: str = Form(''),
    # Watermark Params
    add_watermark: str = Form('false'),
    watermark_type: str = Form('text'),
    watermark_text: str = Form(''),
    watermark_opacity: float = Form(0.5),
    watermark_position: str = Form('bottom_right'),
    watermark_font: str = Form('Arial-Bold'), # New Param
    watermark_size: float = Form(0.3)
):
    try:
        data = {}
        if video_file:
             filename = secure_filename(video_file.filename)
             filepath = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}_{filename}")
             with open(filepath, "wb") as buffer:
                 while content := await video_file.read(1024 * 1024): 
                     buffer.write(content)
             data['video_file'] = True
             data['filepath'] = filepath
        elif url:
            data['url'] = url
        elif local_video_path:
             if not os.path.exists(local_video_path):
                 abs_path = os.path.abspath(local_video_path)
                 return JSONResponse(status_code=400, content={'error': f'Local file not found: {local_video_path} (Checked: {abs_path})'})
             data['video_file'] = True
             data['filepath'] = local_video_path
        else:
            return JSONResponse(status_code=400, content={'error': 'No valid file, URL, or local path provided'})

        data['stop_for_review'] = True 
        data['num_clips'] = num_clips
        data['manual_cut'] = manual_cut.lower() == 'true' # Set early
        
        if data['manual_cut']:
             data['min_duration'] = 0
        else:
             data['min_duration'] = "auto" if min_duration.lower() == "auto" else int(min_duration)

        data['add_subtitles'] = add_subtitles.lower() == 'true'
        data['add_viral_hook'] = add_viral_hook.lower() == 'true'
        data['transcription_mode'] = transcription_mode
        
        # Manual Cut Data
        data['manual_cut'] = manual_cut.lower() == 'true'
        data['manual_start'] = manual_start
        data['manual_end'] = manual_end
        data['manual_segments'] = manual_segments
        
        data['hook_styles'] = {}
        if data['add_viral_hook']:
            data['hook_styles'] = {
                'hook_style': hook_style,
                'font': hook_font,
                'color': hook_heading_color,
                'position': hook_position,
                'top_text': hook_top_text,
                'headline': hook_headline,
                'subheading': hook_subheading,
                'stroke_width': hook_stroke_width,
                'stroke_color': hook_stroke_color,
                'line_spacing': hook_line_spacing,
                'top_gap': hook_top_gap,
                'bottom_gap': hook_bottom_gap,
                'font_size': hook_font_size,
                'top_font_size': hook_top_font_size,
                'sub_font_size': hook_sub_font_size,
                'full_duration': hook_full_duration.lower() == 'true',
                # Preset 2
                'preset2_content': hook_preset2_text,
                'highlight_color': hook_highlight_color
            }
        
        data['subtitle_config'] = None
        if data['add_subtitles']:
            data['subtitle_config'] = {
                'fontsize': subtitle_font_size,
                'color': subtitle_text_color,
                'stroke_color': subtitle_stroke_color,
                'stroke_width': subtitle_stroke_width,
                'bg_opacity': subtitle_bg_opacity,
                'font': subtitle_font_family,
                'style': subtitle_style,
                'bg_color': subtitle_bg_color,
                'glow_enabled': glow_enabled.lower() == 'true',
                'glow_color': glow_color,
                'glow_intensity': glow_intensity,
                'smart_subtitles': smart_subtitles.lower() in ['true', 'on', '1'],
                'vertical_position': subtitle_position,
            }

        # Watermark Config
        data['add_watermark'] = add_watermark.lower() == 'true'
        if data['add_watermark']:
            data['watermark_type'] = watermark_type
            data['watermark_text'] = watermark_text
            data['watermark_opacity'] = watermark_opacity
            data['watermark_position'] = watermark_position
            data['watermark_size'] = watermark_size
            data['watermark_font'] = watermark_font
        
        asp = video_aspect.strip().lower()
        if asp not in ['9:16', '16:9', '1:1', '4:5', 'original']: asp = '9:16'
        data['video_aspect'] = asp
        data['video_type'] = video_type.strip().lower()
        data['randomize_metadata'] = randomize_metadata.lower() == 'true'
        data['custom_metadata'] = custom_metadata.strip()
        
        # FALLBACK: If api_key is empty, try to load from backend settings
        if not api_key:
            try:
                if os.path.exists(SETTINGS_FILE):
                    with open(SETTINGS_FILE, 'r') as f:
                        saved_settings = json.load(f)
                        if saved_settings.get('apiKey'):
                            api_key = saved_settings.get('apiKey')
                            log.info("API key recovered from settings", module="App")
            except Exception as e:
                print(f"[WARN] Failed to recover API key from settings: {e}")

        data['api_key'] = api_key
        data['api_provider'] = api_provider
        data['custom_prompt'] = custom_prompt.strip()
        
        job_id = job_manager.submit_job(data)
        return {"job_id": job_id}
        
    except Exception as e:
        print(f"Error: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})



class TranscriptUpdate(pydantic.BaseModel):
    job_id: str
    phrase_timings: List[Dict[str, Any]]
    clips_data: List[Dict[str, Any]]

class ManualTranscriptImportRequest(pydantic.BaseModel):
    video_path: str
    phrase_timings: List[Dict[str, Any]]
    clips_data: List[Dict[str, Any]] = []
    num_clips: int = 3
    min_duration: str = '30'
    video_aspect: str = '9:16'
    add_subtitles: bool = True
    add_viral_hook: bool = False
    transcription_mode: str = 'fast'
    api_key: str = ''
    api_provider: str = 'deepseek'
    custom_prompt: str = ''
    subtitle_config: Optional[Dict[str, Any]] = None
    hook_styles: Dict[str, Any] = {}
    watermark_config: Dict[str, Any] = {}
    randomize_metadata: bool = False
    custom_metadata: str = ''
    video_type: str = 'general'
    encoding_preset: str = 'medium'
    language: str = 'en'

class AutoFixRequest(pydantic.BaseModel):
    phrase_timings: List[Dict[str, Any]]
    api_key: str
    api_provider: str = 'deepseek'

class NormalizeSchemaRequest(pydantic.BaseModel):
    phrase_timings: List[Any] = []
    clips_data: List[Any] = []

@app.post("/auto_fix_transcript")
async def auto_fix_transcript(payload: AutoFixRequest):
    try:
        if not payload.api_key:
             return JSONResponse(status_code=400, content={'error': 'API Key is required'})
             
        fixed_timings = auto_fix_transcript_with_llm(
            payload.phrase_timings,
            payload.api_key,
            payload.api_provider
        )
        return {"phrase_timings": fixed_timings}
    except Exception as e:
        print(f"Error in auto_fix_transcript: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})

@app.post("/normalize_import_schema")
async def normalize_import_schema(payload: NormalizeSchemaRequest):
    try:
        normalized_phrase_timings = normalize_phrase_timings_payload(payload.phrase_timings)
        normalized_clips = normalize_clips_payload(payload.clips_data)
        return {
            "phrase_timings": normalized_phrase_timings["items"],
            "clips_data": normalized_clips["items"],
            "warnings": normalized_phrase_timings["warnings"] + normalized_clips["warnings"],
        }
    except Exception as e:
        print(f"Error normalizing schema: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})

@app.post("/manual_transcript_import")
async def manual_transcript_import(payload: ManualTranscriptImportRequest):
    try:
        video_path = (payload.video_path or '').strip()
        if not video_path:
            return JSONResponse(status_code=400, content={'error': 'video_path is required'})

        normalized_path = os.path.normpath(video_path)
        if not os.path.exists(normalized_path):
            return JSONResponse(status_code=400, content={'error': f'Video path not found: {video_path}'})

        if not payload.phrase_timings:
            return JSONResponse(status_code=400, content={'error': 'phrase_timings is required'})

        aspect = (payload.video_aspect or '9:16').strip().lower()
        if aspect not in ['9:16', '16:9', '1:1', '4:5', 'original']:
            aspect = '9:16'

        valid_presets = {'veryslow', 'slow', 'medium', 'fast', 'veryfast', 'ultrafast'}
        encoding_preset = payload.encoding_preset if payload.encoding_preset in valid_presets else 'medium'

        job_data = {
            'video_file': True,
            'filepath': normalized_path,
            'stop_for_review': not bool(payload.clips_data),
            'num_clips': max(1, min(int(payload.num_clips or 3), 5)),
            'min_duration': payload.min_duration,
            'add_subtitles': bool(payload.add_subtitles),
            'add_viral_hook': bool(payload.add_viral_hook),
            'add_watermark': bool(payload.watermark_config),
            'transcription_mode': payload.transcription_mode or 'fast',
            'manual_cut': False,
            'manual_start': '00:00',
            'manual_end': '00:30',
            'manual_segments': '[]',
            'hook_styles': payload.hook_styles or {},
            'subtitle_config': payload.subtitle_config if payload.add_subtitles else None,
            'watermark_config': payload.watermark_config or {},
            'video_aspect': aspect,
            'video_type': (payload.video_type or 'general').strip().lower(),
            'randomize_metadata': bool(payload.randomize_metadata),
            'encoding_preset': encoding_preset,
            'custom_metadata': (payload.custom_metadata or '').strip(),
            'api_key': payload.api_key or '',
            'api_provider': payload.api_provider or 'deepseek',
            'custom_prompt': (payload.custom_prompt or '').strip(),
            'language': payload.language or 'en',
        }

        if payload.clips_data:
            job_id = job_manager.submit_job(job_data)
            job_dir = os.path.join(job_manager.jobs_dir, job_id)
        else:
            job_id = str(uuid.uuid4())
            job_dir = os.path.join(job_manager.jobs_dir, job_id)
            os.makedirs(job_dir, exist_ok=True)
            metadata = {
                "id": job_id,
                "created_at": time.time(),
                "status": JobStatus.WAITING_REVIEW.value,
                "progress": "Waiting for user review...",
                "progress_msg": "Waiting for user review...",
                "percentage": 70,
                "priority": 5,
                "data": job_data,
                "history": [],
                "last_updated": time.time(),
            }
            job_manager._save_job_file(job_id, "metadata.json", metadata)

        with open(os.path.join(job_dir, "transcript.json"), 'w', encoding='utf-8') as handle:
            json.dump(payload.phrase_timings, handle, indent=2, ensure_ascii=False)

        if payload.clips_data:
            with open(os.path.join(job_dir, "analysis.json"), 'w', encoding='utf-8') as handle:
                json.dump(payload.clips_data, handle, indent=2, ensure_ascii=False)

        return {
            "job_id": job_id,
            "status": "queued" if payload.clips_data else "waiting_review",
        }
    except Exception as e:
        print(f"Error importing manual transcript: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})

@app.post("/process_with_transcript")
async def process_with_transcript(payload: TranscriptUpdate):
    try:
        job_id = payload.job_id
        
        # 1. Update Job Data with edited transcript/clips
        # We save these as artifacts so the runner picks them up on resume
        job_dir = os.path.join(job_manager.jobs_dir, job_id)
        
        # Save edited transcript
        with open(os.path.join(job_dir, "transcript.json"), 'w') as f:
            json.dump(payload.phrase_timings, f, indent=2)
            
        # Save edited clips
        with open(os.path.join(job_dir, "analysis.json"), 'w') as f:
            json.dump(payload.clips_data, f, indent=2)

        # IMPORTANT: efficient loop prevention
        # We must disable stop_for_review so the runner proceeds further
        job_manager.update_job_data(job_id, {'stop_for_review': False})
        
        # CRITICAL FIX: Delete previous results to force re-cutting
        # If we don't do this, JobRunner sees clips_result.json and skips the cutting step
        clips_result_path = os.path.join(job_dir, "clips_result.json")
        if os.path.exists(clips_result_path):
            try:
                os.remove(clips_result_path)
                print(f"[INFO] Deleted stale clips_result.json for job {job_id} to force re-processing")
            except Exception as e:
                print(f"[WARN] Failed to delete clips_result.json: {e}")
            
        # 2. Resume Job
        if job_manager.resume_job(job_id):
            return {"status": "resumed"}
        else:
            return JSONResponse(status_code=400, content={'error': 'Could not resume job (invalid state or already running)'})

    except Exception as e:
        print(f"Error resuming job: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})
@app.get("/get_transcript/{job_id}")
async def get_transcript_status(job_id: str):
    meta = job_manager.get_job(job_id)
    if not meta:
         return JSONResponse(status_code=404, content={'error': 'Job not found'})

    status_enum = meta.get('status')
    
    # Map backend status to frontend status
    frontend_status = 'processing'
    if status_enum in ['queued', 'preparing', 'transcribing', 'analyzing', 'cutting']:
        frontend_status = 'processing'
    elif status_enum == 'waiting_review':
        frontend_status = 'waiting_review'
    elif status_enum == 'complete':
        frontend_status = 'complete'
    elif status_enum == 'error':
        frontend_status = 'error'
    elif status_enum == 'cancelled':
        frontend_status = 'cancelled'

    response_data = {
        'status': frontend_status,
        'progress': meta.get('percentage', 0), # Prefer numeric percentage
        'msg': meta.get('progress'), # Original text message
        'error': meta.get('error')
    }

    # If we are ready for review, load the heavy data
    if frontend_status == 'waiting_review':
        job_dir = os.path.join(job_manager.jobs_dir, job_id)
        
        transcript_path = os.path.join(job_dir, "transcript.json")
        analysis_path = os.path.join(job_dir, "analysis.json")
        
        if os.path.exists(transcript_path):
             with open(transcript_path, 'r', encoding='utf-8') as f:
                 response_data['phrase_timings'] = json.load(f)
                 
        if os.path.exists(analysis_path):
             with open(analysis_path, 'r', encoding='utf-8') as f:
                 response_data['clips_data'] = json.load(f)

    return response_data

@app.get("/status/{job_id}")
async def get_status(job_id: str):
    meta = job_manager.get_job(job_id)
    if not meta:
        return JSONResponse(status_code=404, content={'error': 'Not found'})
        
    status_enum = meta.get('status')
    frontend_status = 'processing'
    
    if status_enum in ['queued', 'preparing', 'transcribing', 'analyzing', 'cutting']:
        frontend_status = 'processing'
    elif status_enum == 'waiting_review':
        frontend_status = 'waiting_review'
    elif status_enum == 'complete':
        frontend_status = 'complete'
    elif status_enum == 'error':
        frontend_status = 'error'
    elif status_enum == 'cancelled':
        frontend_status = 'cancelled'
        
    return {
        'status': frontend_status,
        'progress': meta.get('percentage', 0),
        'msg': meta.get('progress'),
        'error': meta.get('error'),
        'clips': meta.get('clips', [])
    }

@app.get("/download/{filepath:path}")
async def download_file(filepath: str):
    if '..' in filepath or filepath.startswith('/'):
         return JSONResponse(status_code=403, content={'error': 'Invalid path'})
         
    file_path = os.path.join('static', filepath)
    
    try:
        real_file = os.path.realpath(file_path)
        real_static = os.path.realpath('static')
        
        if not real_file.startswith(real_static):
            return JSONResponse(status_code=403, content={'error': 'Access denied'})
            
        if os.path.exists(file_path):
            filename = os.path.basename(file_path)
            return FileResponse(
                file_path,
                media_type='application/octet-stream',
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
    except Exception as e:
        print(f"Download error: {e}")
        
    return JSONResponse(status_code=404, content={'error': 'File tidak ditemukan'})

@app.get("/gallery", response_class=HTMLResponse)
async def gallery(request: Request):
    return templates.TemplateResponse(request, "gallery.html", {})

@app.get("/api/thumbnail/{filename:path}")
async def get_thumbnail(filename: str):
    log.debug(f"Serving thumbnail: {filename}", module="App")
    # Serve from THUMBNAILS_DIR (writable in prod) not STATIC_DIR/thumbnails (read-only)
    thumb_path = os.path.join(THUMBNAILS_DIR, filename)
    if os.path.exists(thumb_path):
        return FileResponse(thumb_path, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
    # Fallback: legacy path (dev/old installs that still have it in static)
    legacy_path = os.path.join(STATIC_DIR, 'thumbnails', filename)
    if os.path.exists(legacy_path):
        return FileResponse(legacy_path, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
    
    log.warn(f"Thumbnail not found: {thumb_path}", module="App")
    return JSONResponse(status_code=404, content={"error": "Thumbnail not found"})

# --- Preview Generation ---
@app.post("/api/preview")
async def generate_preview_endpoint(request: Request):
    """Generate thumbnail preview for a clip"""
    try:
        data = await request.json()
        video_path = data.get('video_path')
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        
        if not video_path or start_time is None or end_time is None:
            return JSONResponse(status_code=400, content={'error': 'Missing required fields'})
        
        # Import here to avoid circular imports
        from video_cutter import generate_clip_preview
        
        preview_base64 = generate_clip_preview(video_path, start_time, end_time)
        
        if not preview_base64:
            return JSONResponse(status_code=500, content={'error': 'Failed to generate preview'})
        
        return {'preview': preview_base64}
        
    except Exception as e:
        print(f"[ERROR] Preview generation error: {e}")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={'error': str(e)})

@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    """Handle standalone video upload from Video Library"""
    
    try:
        if not allowed_file(file.filename):
             return JSONResponse(status_code=400, content={'error': 'Invalid file type. Allowed: mp4, mov, avi'})

        # Generate unique filename similar to existing logic
        original_filename = secure_filename(file.filename)
        unique_id = str(uuid.uuid4())
        filename = f"{unique_id}_{original_filename}"
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        abs_file_path = os.path.abspath(file_path) # Absolute path for ffmpeg
        
        # Save file
        
        with open(abs_file_path, "wb") as buffer:
            import shutil
            shutil.copyfileobj(file.file, buffer)
            
        

        # Helper to generate thumbnail (copy logic from list_videos or abstract it)
        # Use THUMBNAILS_DIR (writable in prod)
        thumb_dir = THUMBNAILS_DIR
        os.makedirs(thumb_dir, exist_ok=True)
        thumb_name = f"{filename}.jpg"
        thumb_path = os.path.join(thumb_dir, thumb_name)
        abs_thumb_path = os.path.abspath(thumb_path)
        
        thumb_url = None
        try:
             import subprocess
             
             ffmpeg_exe = binary_manager.get_ffmpeg_path()
             cmd = [
                ffmpeg_exe, '-y', 
                '-i', abs_file_path, 
                '-ss', '00:00:01.000', 
                '-vframes', '1', 
                '-vf', 'scale=320:-1', 
                abs_thumb_path
            ]
             # Capture output to debug why it might fail
             result = subprocess.run(cmd, capture_output=True, text=True)
             if result.returncode != 0:
                 log.error(f"Thumbnail generation failed (retcode={result.returncode}): {result.stderr[:200]}", module="Upload")
             else:
                 thumb_url = f"/api/thumbnail/{thumb_name}"
                 
                 
        except Exception as e:
            log.error(f"Thumbnail generation exception: {e}", module="Upload")

        # Return file info
        return {
            'filename': filename,
            'path': f"{UPLOAD_FOLDER}/{filename}",
            'thumbnail': thumb_url,
            'created_at': time.time(),
            'size': os.path.getsize(abs_file_path)
        }

    except Exception as e:
        print(f"ERROR in upload_video: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})




@app.delete("/api/video/{file_path:path}")
async def delete_video(file_path: str):
    """Delete a video, its source file, metadata, and thumbnail using path (abs or relative)."""
    try:
        print(f"[DELETE VIDEO] file_path received: {file_path}")
        print(f"[DELETE VIDEO] frozen: {getattr(sys, 'frozen', False)}")
        
        # Check if it's already an absolute path
        if os.path.isabs(file_path):
            # It's an absolute path (likely from CLIPS_DIR)
            full_path = os.path.abspath(file_path)
            print(f"[DELETE VIDEO] Detected absolute path")
        else:
            # It's a relative path - join with app directory
            if getattr(sys, 'frozen', False):
                app_dir = os.path.dirname(sys.executable)
            else:
                app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
            full_path = os.path.join(app_dir, file_path)
            full_path = os.path.abspath(full_path)
            print(f"[DELETE VIDEO] Detected relative path, app_dir: {app_dir}")
        
        
        print(f"[DELETE VIDEO] full_path computed: {full_path}")
        print(f"[DELETE VIDEO] file exists: {os.path.exists(full_path)}")
        
        # If file doesn't exist at computed path, try resolving against standard directories
        if not os.path.exists(full_path) and not os.path.isabs(file_path):
             print("[DELETE VIDEO] File not found at default path, trying standard directories...")
             candidates = [
                 os.path.join(CLIPS_DIR, file_path),
                 os.path.join(UPLOAD_FOLDER, file_path),
                 os.path.join("downloads", file_path)
             ]
             for candidate in candidates:
                 if os.path.exists(candidate):
                     full_path = os.path.abspath(candidate)
                     print(f"[DELETE VIDEO] Found at: {full_path}")
                     break

        # Security check: ensure it's in allowed directories
        # For absolute paths, check against CLIPS_DIR
        # For relative paths, check against app-relative dirs
        allowed_dirs = [CLIPS_DIR]  # Add CLIPS_DIR for absolute paths
        
        # Also add app-relative directories if frozen
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        allowed_dirs.extend([
            os.path.join(app_dir, 'static'),
            os.path.join(app_dir, 'uploads'),
            os.path.join(app_dir, 'downloads')
        ])
        
        print(f"[DELETE VIDEO] allowed_dirs: {allowed_dirs}")
        
        is_allowed = False
        for allowed_dir in allowed_dirs:
            abs_allowed = os.path.abspath(allowed_dir)
            if full_path.startswith(abs_allowed):
                is_allowed = True
                print(f"[DELETE VIDEO] Matched allowed dir: {abs_allowed}")
                break
        
        print(f"[DELETE VIDEO] is_allowed: {is_allowed}")
        
        if not is_allowed or not os.path.exists(full_path):
             return JSONResponse(status_code=403, content={"error": "Invalid file path or file not found"})

        # Delete file
        os.remove(full_path)
        
        # Delete metadata if exists
        meta_path = full_path + ".json"
        if os.path.exists(meta_path):
            try:
                os.remove(meta_path)
            except: pass
            
        # Delete thumbnail if exists
        # Thumbnails are flattened in static/thumbnails with filename.jpg
        # This might collide if two files have same name in different folders.
        # Ideally thumbnails should mirror structure, but current gen logic relies on filename.
        filename = os.path.basename(file_path)
        thumb_path = os.path.join(STATIC_DIR, 'thumbnails', f"{filename}.jpg")
        if os.path.exists(thumb_path):
            try:
                os.remove(thumb_path)
            except: pass
            
        return {"status": "deleted", "path": file_path}
        
    except Exception as e:
        print(f"Error deleting video {file_path}: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/video/{file_path:path}")
async def stream_video(file_path: str):
    """Serve video file from relative path."""
    # Handle both absolute and relative paths
    # If it's already absolute, use it. Otherwise, treat as relative to current directory or STATIC_DIR
    
    # Always normalize to ensure consistent slash direction (Windows uses backslash)
    full_path = os.path.normpath(file_path)
    if not os.path.isabs(full_path):
         # Try as relative to current working directory first
         full_path = os.path.abspath(full_path)
         
         # If not found, try relative to STATIC_DIR
         if not os.path.exists(full_path):
             full_path = os.path.join(STATIC_DIR, file_path.replace('static/', ''))
             full_path = os.path.normpath(full_path)
    
    # Security check - allow CLIPS_DIR, STATIC_DIR, uploads, downloads
    allowed_prefixes = [os.path.abspath(CLIPS_DIR), os.path.abspath(STATIC_DIR), os.path.abspath(UPLOAD_FOLDER), os.path.abspath('downloads')]
    is_allowed = False
    
    for prefix in allowed_prefixes:
        if full_path.startswith(prefix):
            is_allowed = True
            break
            
    if is_allowed and os.path.exists(full_path):
        return FileResponse(full_path, media_type="video/mp4")
    
    print(f"⚠️ Video not found or not allowed: {file_path} -> {full_path}")        
    return JSONResponse(status_code=404, content={"error": "Video not found"})

@app.get("/api/videos")
async def list_videos():
    # Use THUMBNAILS_DIR — writable in prod (unlike STATIC_DIR/thumbnails which is read-only)
    thumb_dir = THUMBNAILS_DIR
    os.makedirs(thumb_dir, exist_ok=True)
    
    def generate_thumbnail(video_path, filename):
        # NOTE: Using only filename for thumbnail might cause collisions for same-named files in diff folders.
        # For now, we stick to this to avoid breaking existing logic, but maybe prefix with hash?
        thumb_name = f"{filename}.jpg"
        thumb_path = os.path.join(thumb_dir, thumb_name)
        
        # Return existing if valid
        if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            return f"/api/thumbnail/{thumb_name}"
            
        try:
            import subprocess
            ffmpeg_exe = binary_manager.get_ffmpeg_path()
            
            # Use a slightly better seek time (2 seconds to skip potential black frames)
            seek_time = '00:00:02.000'
            
            cmd = [
                ffmpeg_exe, '-y', 
                '-i', video_path, 
                '-ss', seek_time,
                '-vframes', '1', 
                '-vf', 'scale=320:-1', 
                thumb_path
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if not os.path.exists(thumb_path):
                 return None
            return f"/api/thumbnail/{thumb_name}"
        except Exception as e:
            log.error(f"Thumbnail generation failed: {e}", module="App")
            return None

    def scan_dir(root_dir):
        videos = []
        if not os.path.exists(root_dir):
            return videos
            
        # Recursive walk
        for dirpath, _, filenames in os.walk(root_dir):
            for filename in filenames:
                if filename.lower().endswith(('.mp4', '.mov', '.avi')):
                    full_path = os.path.join(dirpath, filename)
                    
                    # For clips in CLIPS_DIR (which might be in ~/Documents), use absolute path
                    # For other directories (uploads, downloads) that are relative to CWD, use relative path
                    if root_dir == CLIPS_DIR:
                        # Use absolute path for clips since they might be outside CWD
                        path_to_return = full_path.replace('\\', '/')
                    else:
                        # Use relative path for backwards compatibility with uploads/downloads
                        path_to_return = os.path.relpath(full_path, os.getcwd()).replace('\\', '/')
                    
                    stat = os.stat(full_path)
                    
                    meta_path = full_path + ".json"
                    meta = {}
                    if os.path.exists(meta_path):
                        try:
                            with open(meta_path, 'r') as f:
                                meta = json.load(f)
                        except: pass
                    
                    thumb_url = generate_thumbnail(full_path, filename)
                    
                    videos.append({
                        'filename': filename,
                        'path': path_to_return,  # Absolute for clips, relative for others
                        'thumbnail': thumb_url,
                        'created_at': stat.st_mtime,
                        'size': stat.st_size,
                        'size': stat.st_size,
                        'caption': meta.get('viral_caption', ''),
                        'score': meta.get('viral_score', ''),
                        'url': meta.get('original_url', '') # Return original URL for frontend matching
                    })
            
            # SCAN FOR FAILED DOWNLOADS (.failed.json)
            for filename in filenames:
                if filename.endswith('.failed.json'):
                    full_path = os.path.join(dirpath, filename)
                    try:
                        with open(full_path, 'r') as f:
                            data = json.load(f)
                            
                        # Calculate relative path same as above
                        if root_dir == CLIPS_DIR:
                            path_to_return = full_path.replace('\\', '/')
                        else:
                            path_to_return = os.path.relpath(full_path, os.getcwd()).replace('\\', '/')

                        videos.append({
                            'id': filename, # distinct ID
                            'filename': data.get('url', 'Unknown URL'),
                            'path': path_to_return, # Return actual path so it can be deleted
                            'thumbnail': None,
                            'created_at': data.get('timestamp', os.path.getmtime(full_path)),
                            'status': 'failed',
                            'error': data.get('error', 'Unknown error'),
                            'is_failed': True
                        })
                    except:
                        pass

        return videos

    categories = {
        'clips': scan_dir(CLIPS_DIR),
        'uploads': scan_dir('uploads'),
        'downloads': scan_dir('downloads')
    }
    
    for cat in categories:
        categories[cat].sort(key=lambda x: x['created_at'], reverse=True)
        
    return categories

@app.delete("/api/videos")
async def delete_video(path: Optional[str] = None, delete_all: bool = False):
    """
    Delete a video file and its associated JSON metadata (if any).
    The 'path' parameter is expected to be a relative path from the project root.
    If 'delete_all' is True, all files in CLIPS_DIR will be deleted.
    """
    if delete_all:
        try:
            import shutil
            count = 0
            # Only clear CLIPS_DIR for safety
            folder = CLIPS_DIR
            if os.path.exists(folder):
                for filename in os.listdir(folder):
                     file_path = os.path.join(folder, filename)
                     try:
                         if os.path.isfile(file_path) or os.path.islink(file_path):
                             os.unlink(file_path)
                             count += 1
                         elif os.path.isdir(file_path):
                             shutil.rmtree(file_path)
                             count += 1
                     except Exception as e:
                         log.warn(f"Failed to delete {file_path}: {e}", module="Cache")
            return {"status": "success", "message": f"Deleted {count} items from gallery"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    if not path:
         raise HTTPException(status_code=400, detail="Path is required unless delete_all is True")

    # Defensive input cleaning
    clean_path = path.strip()
    # Removed incorrect stripping of leading slash which broke absolute paths
    # if clean_path.startswith('/'):
    #     clean_path = clean_path[1:]
    
    # Normalize path separators
    clean_path = os.path.normpath(clean_path)
    
    # Security check: Ensure we only delete from allowed dirs
    # allowed_dirs should also be absolute/normalized
    allowed_dirs = [os.path.abspath(CLIPS_DIR), os.path.abspath('uploads'), os.path.abspath('downloads')]
    
    # Resolve clean_path to absolute to match allowed_dirs
    if not os.path.isabs(clean_path):
         clean_path = os.path.abspath(clean_path)

    # Allow deleting .failed.json explicitly even if strictly outside standard clips flow, 
    # but still must be in project dirs
    is_allowed = any(clean_path.startswith(d) for d in allowed_dirs)
    
    # Allow .failed.json specifically
    if clean_path.endswith('.failed.json'):
         # Ensure it is in uploads or downloads at least
         if not is_allowed:
             # loose check
             is_allowed = 'uploads' in clean_path or 'downloads' in clean_path
    
    if not is_allowed or '..' in clean_path:
        raise HTTPException(status_code=403, detail="Invalid file path or permission denied")

    # Simple check for existence in CWD relative path
    if not os.path.exists(clean_path):
        raise HTTPException(status_code=404, detail="File not found")

    try:
        os.remove(clean_path)
        
        # Try to remove associated json
        json_path = clean_path + ".json"
        if os.path.exists(json_path):
            os.remove(json_path)
            
        return {"status": "success", "message": f"Deleted {clean_path}"}
    except Exception as e:
        print(f"Error deleting file: {e}")
        # Allow deleting .failed files specifically even if checking path existence might fail naturally?
        # Actually .failed files exist, so os.remove works.
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/fonts")
async def get_available_fonts():
    """Get list of available fonts from static/fonts directory"""
    fonts_folder = "static/fonts"
    if not os.path.exists(fonts_folder):
        return {"fonts": []}
    
    fonts = []
    font_files = glob.glob(os.path.join(fonts_folder, "*.ttf")) + glob.glob(os.path.join(fonts_folder, "*.otf"))
    
    for font_path in sorted(font_files):
        filename = os.path.basename(font_path)
        # Extract font name from filename (remove extension only)
        font_name = filename.rsplit('.', 1)[0]
        
        # Clean up certain bad suffixes but keep variants like -Bold, -Black
        for bad_suffix in [' PERSONAL USE ONLY!', ' DEMO VERSION', ' Demo']:
            if font_name.endswith(bad_suffix):
                font_name = font_name[:-len(bad_suffix)]
                break
        
        fonts.append({
            "name": font_name,
            "filename": filename,
            "family": font_name,  # Keep full name including variant
            "path": f"/static/fonts/{filename}"  # Path for loading in browser
        })
    
    # Scan custom fonts
    if os.path.exists(FONTS_DIR):
        custom_font_files = glob.glob(os.path.join(FONTS_DIR, "*.ttf")) + \
                           glob.glob(os.path.join(FONTS_DIR, "*.otf")) + \
                           glob.glob(os.path.join(FONTS_DIR, "*.woff2"))
                           
        for font_path in sorted(custom_font_files):
            filename = os.path.basename(font_path)
            font_name = filename.rsplit('.', 1)[0]
            
            fonts.append({
                "name": font_name,
                "filename": filename,
                "family": font_name,
                "path": f"/custom_fonts/{filename}", # Custom mount point
                "is_custom": True
            })
    
    return {"fonts": fonts}






@app.get("/api/debug/config")
async def debug_config():
    """Debug endpoint to check backend configuration and paths"""
    if not DEBUG_MODE:
        raise HTTPException(status_code=403, detail="Debug endpoints disabled. Set CLIP_DEBUG=1 to enable.")
    return {
        "frozen": getattr(sys, 'frozen', False),
        "paths": {
            "upload_folder": UPLOAD_FOLDER,
            "clips_dir": CLIPS_DIR,
            "background_dir": BACKGROUND_DIR,
            "fonts_dir": FONTS_DIR,
            "static_dir": STATIC_DIR,
            "cwd": os.getcwd()
        },
        "exists": {
            "clips_dir": os.path.exists(CLIPS_DIR),
            "fonts_dir": os.path.exists(FONTS_DIR),
            "static_dir": os.path.exists(STATIC_DIR)
        },
        "contents": {
            "fonts_dir": os.listdir(FONTS_DIR) if os.path.exists(FONTS_DIR) else [],
            "static_fonts": os.listdir(os.path.join(STATIC_DIR, 'fonts')) if os.path.exists(os.path.join(STATIC_DIR, 'fonts')) else []
        }
    }



@app.post("/api/cancel_job/{job_id}")
async def cancel_job(job_id: str):
    """
    Cancels a running or queued job.
    """
    print(f"[INFO] Cancel request received for job_id: '{job_id}'")
    
    # 1. Check if job exists
    job = job_manager.get_job(job_id)
    if not job:
         print(f"[ERROR] Cancel failed: Job {job_id} not found in manager.")
         return JSONResponse(status_code=404, content={"error": f"Job {job_id} not found"})
         
    # 2. Trigger cancellation
    print(f"[INFO] calling job_manager.cancel_job({job_id})...")
    success = job_manager.cancel_job(job_id)
    print(f"[INFO] job_manager.cancel_job returned: {success}")
    
    if success:
        return {"status": "success", "message": "Job cancellation requested"}
    else:
        return JSONResponse(status_code=400, content={"error": "Failed to cancel job (it might already be complete)"})


if __name__ == "__main__":
    import os
    import runpy
    import sys

    if os.environ.get("CLIP_USE_MODULAR_ENTRY", "").lower() in ("1", "true", "yes"):
        _mod = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_modular.py")
        log.info(f"CLIP_USE_MODULAR_ENTRY: starting {_mod}", module="App")
        sys.argv[0] = _mod
        runpy.run_path(_mod, run_name="__main__")
        raise SystemExit(0)

    import uvicorn
    import logging

    # Route uvicorn startup messages to stdout (not stderr)
    # so Electron doesn't label them [BACKEND-ERR]
    log_config = uvicorn.config.LOGGING_CONFIG.copy()
    for handler in log_config.get("handlers", {}).values():
        handler["stream"] = "ext://sys.stdout"

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=9478,
        log_level="warning",   # Suppress per-request access logs
        log_config=log_config,
    )
