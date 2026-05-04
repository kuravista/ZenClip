@echo off
title ZenClip - Stop All Services
echo Stopping ZenClip services ...

:: Kill backend (uvicorn on port 9478)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :9478 ^| findstr LISTENING') do (
    taskkill /PID %%a /F >nul 2>&1
    echo [OK] Backend stopped (PID %%a)
)

:: Kill frontend (vite on port 3987)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :3987 ^| findstr LISTENING') do (
    taskkill /PID %%a /F >nul 2>&1
    echo [OK] Frontend stopped (PID %%a)
)

echo.
echo All services stopped.
timeout /t 2 /nobreak >nul
