"""
ZenClip Backend - Modular Version

This is a refactored version of app.py that uses routers for better organization.
The original app.py is kept for backward compatibility.

Usage:
    python app_modular.py

To use the original monolithic version:
    python app.py
"""
import os
import sys
import warnings

# Add src directory to path for imports
src_dir = os.path.dirname(os.path.abspath(__file__))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

# Suppress warnings
warnings.filterwarnings("ignore", message=".*NotOpenSSLWarning.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="urllib3")

# Initialize binary environment first
from services.core import binary_manager

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from utils.logger import log

# Import routers
from routers import (
    health_router,
    settings_router,
    fonts_router,
    gallery_router,
    processing_router,
    debug_router,
)

# Import job manager for lifecycle
from services.core.job_manager import job_manager

# --- Configuration ---
DEBUG_MODE = os.environ.get('CLIP_DEBUG', '0') == '1'
BACKEND_PORT = int(os.environ.get('CLIP_BACKEND_PORT', '9479'))

# --- Path Configuration ---
def get_app_data_dir() -> str:
    """Get app data directory."""
    app_data_dir = os.environ.get('CLIP_APP_DATA_DIR')
    if app_data_dir:
        return app_data_dir

    # Default
    if sys.platform == 'win32':
        return os.path.join(os.environ.get('USERPROFILE', '.'), 'Documents', 'SnipieAI')
    return os.path.join(os.path.expanduser('~'), '.snipieai')


APP_DATA_DIR = get_app_data_dir()
STATIC_DIR = os.environ.get('CLIP_STATIC_DIR', 'static')
TEMPLATES_DIR = os.environ.get('CLIP_TEMPLATES_DIR', 'templates')

# Ensure directories exist
os.makedirs(APP_DATA_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs('uploads', exist_ok=True)

# --- Application Setup ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    # Startup
    log.info("Starting ZenClip backend (modular)", module="App")
    log.info(f"App data directory: {APP_DATA_DIR}", module="App")
    log.info(f"Debug mode: {DEBUG_MODE}", module="App")

    yield

    # Shutdown
    log.info("Shutting down ZenClip backend", module="App")
    # Cancel any active jobs
    if job_manager.active_job_id:
        log.info(f"Cancelling active job: {job_manager.active_job_id}", module="App")
        job_manager.cancel_job(job_manager.active_job_id)


# Create FastAPI app
app = FastAPI(
    title="ZenClip Backend (Modular)",
    description="AI-powered video clipping tool",
    version="2.0.0",
    lifespan=lifespan
)

# --- CORS Configuration ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "null",  # Electron file:// protocol
        "http://localhost:5173",  # Vite dev server
        "http://127.0.0.1:5173",
        f"http://localhost:{BACKEND_PORT}",
        f"http://127.0.0.1:{BACKEND_PORT}",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Mount Static Files ---
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# --- Templates ---
templates = Jinja2Templates(directory=TEMPLATES_DIR) if os.path.exists(TEMPLATES_DIR) else None

# --- Include Routers ---
app.include_router(health_router)
app.include_router(settings_router)
app.include_router(fonts_router)
app.include_router(gallery_router)
app.include_router(processing_router)

if DEBUG_MODE:
    app.include_router(debug_router)
    log.info("Debug endpoints enabled", module="App")

# --- Root Endpoint ---
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Root endpoint - serve frontend."""
    if templates:
        return templates.TemplateResponse("index.html", {"request": request})
    return HTMLResponse(content="<h1>ZenClip Backend</h1><p>Frontend not found</p>", status_code=200)


# --- Fallback for unhandled routes ---
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def catch_all(path: str):
    """Catch-all for undefined routes."""
    return JSONResponse(
        status_code=404,
        content={"error": f"Route /{path} not found"}
    )


# --- Main Entry Point ---
if __name__ == "__main__":
    import uvicorn

    log.info(f"Starting server on port {BACKEND_PORT}", module="App")

    # Route uvicorn startup messages to stdout
    log_config = uvicorn.config.LOGGING_CONFIG.copy()
    for handler in log_config.get("handlers", {}).values():
        handler["stream"] = "ext://sys.stdout"

    uvicorn.run(
        app,
        host="127.0.0.1",  # Bind to localhost only for security
        port=BACKEND_PORT,
        log_level="warning",
        log_config=log_config,
    )
