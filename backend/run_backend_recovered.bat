@echo off
setlocal
set WS=D:\Extend_C\Program\zenclip\audit\recovery-workspace\backend
set SIDECAR=D:\Extend_C\Program\zenclip\resources\backend_sidecar

echo [MODE] Original recovered launcher ^(legacy bootstrap path^)
if not defined CLIP_BACKEND_PORT set CLIP_BACKEND_PORT=9478
echo [INFO] Target port: %CLIP_BACKEND_PORT%

set CLIP_SIDECAR_DIR=%SIDECAR%
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
set PATH=%SIDECAR%\ffmpeg;%SIDECAR%\cuda;%PATH%
cd /d %WS%
"D:\Extend_C\Program\zenclip\resources\backend_sidecar\python\python.exe" run_backend.py
endlocal
