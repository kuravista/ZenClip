@echo off
REM ============================================
REM ZenClip Video Clipper - Quick Start Script
REM ============================================
REM Usage: clip_video.bat "path\to\video.mp4" [num_clips] [min_duration]
REM Example: clip_video.bat "D:\Videos\test.mp4" 3 30

setlocal enabledelayedexpansion

REM --- Configuration ---
set BACKEND_PORT=9478
set BACKEND_URL=http://127.0.0.1:%BACKEND_PORT%
set PYTHON_EXE=D:\Extend_C\Program\zenclip\resources\backend_sidecar\python\python.exe
set BACKEND_DIR=D:\Extend_C\Program\zenclip\audit\recovery-workspace\backend
set OUTPUT_DIR=D:\Extend_C\Program\zenclip\audit\recovery-workspace\static\clips

REM --- Arguments ---
set VIDEO_PATH=%~1
set NUM_CLIPS=%~2
set MIN_DURATION=%~3

if "%VIDEO_PATH%"=="" (
    echo Error: Video path required
    echo Usage: clip_video.bat "path\to\video.mp4" [num_clips] [min_duration]
    echo Example: clip_video.bat "D:\Videos\test.mp4" 3 30
    exit /b 1
)

if "%NUM_CLIPS%"=="" set NUM_CLIPS=3
if "%MIN_DURATION%"=="" set MIN_DURATION=30

echo.
echo ============================================
echo   ZenClip Video Clipper
echo ============================================
echo   Video: %VIDEO_PATH%
echo   Clips: %NUM_CLIPS%
echo   Min Duration: %MIN_DURATION%s
echo ============================================
echo.

REM --- Check video exists ---
if not exist "%VIDEO_PATH%" (
    echo Error: Video file not found: %VIDEO_PATH%
    exit /b 1
)

REM --- Check backend running ---
echo Checking backend...
curl -s %BACKEND_URL%/health >nul 2>&1
if errorlevel 1 (
    echo Backend not running. Starting...
    start /B "" "%PYTHON_EXE%" "%BACKEND_DIR%\run_backend.py"
    echo Waiting for backend to start...
    timeout /t 8 /nobreak >nul

    REM Check again
    curl -s %BACKEND_URL%/health >nul 2>&1
    if errorlevel 1 (
        echo Error: Failed to start backend
        exit /b 1
    )
)
echo Backend OK!

REM --- Submit job ---
echo.
echo Submitting video for processing...
curl -s -X POST %BACKEND_URL%/process ^
  -F "video=@%VIDEO_PATH%" ^
  -F "num_clips=%NUM_CLIPS%" ^
  -F "min_duration=%MIN_DURATION%" ^
  -F "add_subtitles=true" ^
  -F "aspect_ratio=9:16" > job_response.json

REM --- Extract job_id ---
for /f "tokens=2 delims=:" %%a in ('findstr "job_id" job_response.json') do (
    set JOB_ID=%%a
    set JOB_ID=!JOB_ID:"=!
    set JOB_ID=!JOB_ID:,=!
    set JOB_ID=!JOB_ID: =!
)

if "!JOB_ID!"=="" (
    echo Error: Failed to submit job
    type job_response.json
    del job_response.json
    exit /b 1
)

echo Job submitted: !JOB_ID!
del job_response.json

REM --- Monitor progress ---
echo.
echo Processing video...
set PROGRESS=0
:monitor_loop
timeout /t 5 /nobreak >nul
curl -s %BACKEND_URL%/status/!JOB_ID! > status.json

for /f "tokens=2 delims=:," %%a in ('findstr "progress" status.json') do (
    set PROGRESS=%%a
    set PROGRESS=!PROGRESS:"=!
    set PROGRESS=!PROGRESS: =!
)

for /f "tokens=2 delims=:," %%a in ('findstr "status" status.json') do (
    set STATUS=%%a
    set STATUS=!STATUS:"=!
    set STATUS=!STATUS: =!
)

echo Status: !STATUS! - Progress: !PROGRESS!%%%

if "!STATUS!"=="complete" (
    echo.
    echo ============================================
    echo   SUCCESS! Clips created!
    echo ============================================
    echo   Output: %OUTPUT_DIR%\!JOB_ID!\
    echo ============================================
    dir /b "%OUTPUT_DIR%\!JOB_ID!\*.mp4" 2>nul
    del status.json
    exit /b 0
)

if "!STATUS!"=="error" (
    echo.
    echo Error: Processing failed
    type status.json
    del status.json
    exit /b 1
)

goto monitor_loop
