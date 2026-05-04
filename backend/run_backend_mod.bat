@echo off
setlocal
set WS=D:\Extend_C\Program\zenclip\audit\recovery-workspace\backend
set SIDECAR=D:\Extend_C\Program\zenclip\resources\backend_sidecar
set VENV=%WS%\.venv
set RUNTIME=%WS%\runtime\mod

echo [MODE] Recovery mod launcher ^(editable venv + local runtime, sidecar fallback only^)
if not defined CLIP_BACKEND_PORT set CLIP_BACKEND_PORT=8012
echo [INFO] Target port: %CLIP_BACKEND_PORT%

if not exist "%VENV%\Scripts\python.exe" (
  echo [ERROR] Local venv not found. Run bootstrap_mod_env.bat first.
  exit /b 1
)

if not exist "%WS%\runtime\portable\templates\index.html" (
  call "%WS%\bootstrap_portable_runtime.bat"
)

if not exist "%RUNTIME%\app-data" mkdir "%RUNTIME%\app-data"

set CLIP_RECOVERY_SAFE=1
set CLIP_APP_DATA_DIR=%RUNTIME%\app-data
set CLIP_STATIC_DIR=%WS%\runtime\portable\static
set CLIP_TEMPLATES_DIR=%WS%\runtime\portable\templates
set CLIP_LEGACY_FONTS_DIR=%WS%\runtime\portable\static\fonts
set CLIP_JOBS_DIR=%RUNTIME%\app-data\jobs_data
set CLIP_BACKGROUND_DIR=%WS%\runtime\portable\static\background
set CLIP_FONTS_DIR=%WS%\runtime\portable\static\fonts_custom
set CLIP_THUMBNAILS_DIR=%RUNTIME%\app-data\thumbnails
set CLIP_SIDECAR_DIR=
if not defined CLIP_FFMPEG_PATH set CLIP_FFMPEG_PATH=%SIDECAR%\ffmpeg\ffmpeg.exe
if not defined CLIP_CUDA_DIR set CLIP_CUDA_DIR=%SIDECAR%\cuda
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
set OMP_WAIT_POLICY=PASSIVE
set KMP_DUPLICATE_LIB_OK=TRUE
if defined CLIP_CUDA_DIR set PATH=%CLIP_CUDA_DIR%;%PATH%

cd /d %WS%
"%VENV%\Scripts\python.exe" run_backend_safe.py
endlocal
