@echo off
REM ============================================
REM ZenClip - Manual Process with Full Config
REM ============================================
REM Usage: process_video_config.bat "VIDEO_PATH"
REM ============================================

setlocal enabledelayedexpansion

set VIDEO_PATH=%~1
set BACKEND_URL=http://127.0.0.1:9478

REM ============================================
REM CONFIGURATION - EDIT THESE VALUES
REM ============================================

REM --- Clip Settings ---
set NUM_CLIPS=3
set MIN_DURATION=30
set ASPECT_RATIO=9:16

REM --- Subtitle Settings ---
set ADD_SUBTITLES=true
set SUBTITLE_STYLE=shadow
set SUBTITLE_FONT=Poppins-Bold.otf
set SUBTITLE_FONT_SIZE=24
set SUBTITLE_COLOR=#FFFFFF
set LANGUAGE=en

REM --- Hook Settings ---
set ADD_HOOK=true
set HOOK_STYLE=preset2
set HOOK_FONT=Montserrat-Black.otf
set HOOK_FONT_SIZE=48

REM --- Watermark ---
set ADD_WATERMARK=false
set WATERMARK_TEXT=

REM ============================================
REM BUILD JSON PAYLOAD
REM ============================================

set JSON_FILE=%TEMP%\zenclip_payload.json

(
echo {
echo   "video_path": "%VIDEO_PATH:\=/%",
echo   "phrase_timings": [
echo     {"text": "Welcome to this video", "start": 0.0, "end": 3.0},
echo     {"text": "Today we have something special", "start": 3.0, "end": 7.0},
echo     {"text": "Let me show you how it works", "start": 7.0, "end": 12.0},
echo     {"text": "This is important content", "start": 12.0, "end": 18.0},
echo     {"text": "Watch carefully at this part", "start": 18.0, "end": 25.0},
echo     {"text": "Now for the key demonstration", "start": 120.0, "end": 125.0},
echo     {"text": "This is what you need to know", "start": 125.0, "end": 130.0},
echo     {"text": "Pay attention here", "start": 130.0, "end": 135.0},
echo     {"text": "See how easy that was", "start": 135.0, "end": 140.0},
echo     {"text": "Now for the final segment", "start": 300.0, "end": 305.0},
echo     {"text": "This concludes our video", "start": 305.0, "end": 310.0},
echo     {"text": "Thank you for watching", "start": 310.0, "end": 315.0}
echo   ],
echo   "clips_data": [
echo     {"start_time": 0, "end_time": 25, "topic": "Opening", "hook_heading": "Watch This", "hook_subheading": "Amazing"},
echo     {"start_time": 120, "end_time": 150, "topic": "Key Demo", "hook_heading": "Must See", "hook_subheading": "Important"},
echo     {"start_time": 300, "end_time": 340, "topic": "Closing", "hook_heading": "The End", "hook_subheading": "Thanks"}
echo   ],
echo   "num_clips": %NUM_CLIPS%,
echo   "video_aspect": "%ASPECT_RATIO%",
echo   "add_subtitles": %ADD_SUBTITLES%,
echo   "subtitle_style": "%SUBTITLE_STYLE%",
echo   "subtitle_font": "%SUBTITLE_FONT%",
echo   "subtitle_font_size": %SUBTITLE_FONT_SIZE%,
echo   "subtitle_color": "%SUBTITLE_COLOR%",
echo   "add_viral_hook": %ADD_HOOK%,
echo   "hook_style": "%HOOK_STYLE%",
echo   "hook_font": "%HOOK_FONT%",
echo   "hook_font_size": %HOOK_FONT_SIZE%,
echo   "add_watermark": %ADD_WATERMARK%,
echo   "watermark_text": "%WATERMARK_TEXT%",
echo   "language": "%LANGUAGE%"
echo }
) > "%JSON_FILE%"

echo.
echo ============================================
echo   ZenClip Video Processor
echo ============================================
echo   Video: %VIDEO_PATH%
echo   Clips: %NUM_CLIPS%
echo   Aspect: %ASPECT_RATIO%
echo   Subtitles: %ADD_SUBTITLES% (%SUBTITLE_STYLE%)
echo   Hook: %ADD_HOOK% (%HOOK_STYLE%)
echo ============================================
echo.

REM Submit job
echo Submitting...
curl -s -X POST "%BACKEND_URL%/manual_transcript_import" ^
  -H "Content-Type: application/json" ^
  -d @"%JSON_FILE%" > response.json

REM Extract job_id
for /f "tokens=2 delims=:," %%a in ('findstr "job_id" response.json') do (
    set JOB_ID=%%a
    set JOB_ID=!JOB_ID:"=!
    set JOB_ID=!JOB_ID:,=!
    set JOB_ID=!JOB_ID: =!
)

if "!JOB_ID!"=="" (
    echo Error: Failed to submit job
    type response.json
    del response.json "%JSON_FILE%"
    exit /b 1
)

echo Job ID: !JOB_ID!
echo.

REM Monitor
:monitor
curl -s "%BACKEND_URL%/status/!JOB_ID!" > status.json
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

echo Progress: !PROGRESS!%% - !STATUS!

if "!STATUS!"=="complete" (
    echo.
    echo ============================================
    echo   SUCCESS!
    echo ============================================
    type status.json
    del response.json status.json "%JSON_FILE%"
    exit /b 0
)

if "!STATUS!"=="error" (
    echo.
    echo ERROR!
    type status.json
    del response.json status.json "%JSON_FILE%"
    exit /b 1
)

timeout /t 10 /nobreak >nul
goto monitor
