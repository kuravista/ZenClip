@echo off
setlocal
set WS=D:\Extend_C\Program\zenclip\audit\recovery-workspace\backend
set SIDECAR=D:\Extend_C\Program\zenclip\resources\backend_sidecar

echo [MODE] Recovery safe launcher ^(legacy sidecar runtime^)
if not defined CLIP_BACKEND_PORT set CLIP_BACKEND_PORT=9479
echo [INFO] Target port: %CLIP_BACKEND_PORT%

set CLIP_SIDECAR_DIR=%SIDECAR%
set CLIP_RECOVERY_SAFE=1
if not defined CLIP_FFMPEG_PATH set CLIP_FFMPEG_PATH=%SIDECAR%\ffmpeg\ffmpeg.exe
if not defined CLIP_CUDA_DIR set CLIP_CUDA_DIR=%SIDECAR%\cuda
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
set OMP_WAIT_POLICY=PASSIVE
set KMP_DUPLICATE_LIB_OK=TRUE
set PATH=%CLIP_CUDA_DIR%;%PATH%
cd /d %WS%
"D:\Extend_C\Program\zenclip\resources\backend_sidecar\python\python.exe" run_backend_safe.py
endlocal
