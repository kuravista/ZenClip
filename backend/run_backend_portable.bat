@echo off
setlocal
set WS=D:\Extend_C\Program\zenclip\audit\recovery-workspace\backend
set VENV=%WS%\.venv
set RUNTIME=%WS%\runtime\portable

echo [MODE] Recovery portable launcher ^(default modern runtime^)

if not exist "%VENV%\Scripts\python.exe" (
  echo [ERROR] Local venv not found. Run bootstrap_mod_env.bat first.
  exit /b 1
)

if not exist "%RUNTIME%\templates\index.html" (
  call "%WS%\bootstrap_portable_runtime.bat"
)

set CLIP_RECOVERY_SAFE=1
if not defined CLIP_BACKEND_PORT set CLIP_BACKEND_PORT=9479
echo [INFO] Target port: %CLIP_BACKEND_PORT%
set CLIP_APP_DATA_DIR=%RUNTIME%\app-data
set CLIP_STATIC_DIR=%RUNTIME%\static
set CLIP_TEMPLATES_DIR=%RUNTIME%\templates
set CLIP_LEGACY_FONTS_DIR=%RUNTIME%\static\fonts
set CLIP_JOBS_DIR=%RUNTIME%\app-data\jobs_data
set CLIP_BACKGROUND_DIR=%RUNTIME%\static\background
set CLIP_FONTS_DIR=%RUNTIME%\static\fonts_custom
set CLIP_THUMBNAILS_DIR=%RUNTIME%\app-data\thumbnails
set CLIP_DLL_DIR=
set CLIP_CUDA_DIR=
set CLIP_SIDECAR_DIR=
if not defined CLIP_FFMPEG_PATH set CLIP_FFMPEG_PATH=ffmpeg
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
set OMP_WAIT_POLICY=PASSIVE
set KMP_DUPLICATE_LIB_OK=TRUE

cd /d %WS%
"%VENV%\Scripts\python.exe" run_backend_safe.py
endlocal
