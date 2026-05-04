@echo off
title ZenClip Dev Launcher
echo ============================================
echo   ZenClip - Dev Mode Launcher
echo ============================================
echo.

:: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.10+
    pause
    exit /b 1
)

:: Check Node
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found. Install Node 18+
    pause
    exit /b 1
)

set BASE=%~dp0
set BACKEND=%BASE%backend
set FRONTEND=%BASE%zenclip-studio\frontend

echo [1/2] Starting Backend  (port 9478) ...
start "ZenClip Backend" cmd /k "cd /d "%BACKEND%" && python run_backend.py"

echo    Waiting backend ready ...
timeout /t 5 /nobreak >nul

echo [2/2] Starting Frontend (port 3987) ...
start "ZenClip Frontend" cmd /k "cd /d "%FRONTEND%" && npm run dev"

echo.
echo ============================================
echo   All services started!
echo.
echo   Frontend : http://localhost:3987
echo   Backend  : http://127.0.0.1:9478
echo   API Docs : http://127.0.0.1:9478/docs
echo.
echo   Close the terminal windows to stop.
echo ============================================
echo.

:: Auto open browser
timeout /t 3 /nobreak >nul
start http://localhost:3987
