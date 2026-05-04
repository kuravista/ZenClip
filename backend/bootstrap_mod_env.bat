@echo off
setlocal
set WS=D:\Extend_C\Program\zenclip\audit\recovery-workspace\backend
set VENV=%WS%\.venv
set INSTALL_MEDIA=0
set INSTALL_ASR=0

if /I "%~1"=="--with-media" set INSTALL_MEDIA=1
if /I "%~1"=="--with-all" (
  set INSTALL_MEDIA=1
  set INSTALL_ASR=1
)
if /I "%~1"=="--with-asr" set INSTALL_ASR=1
if /I "%~2"=="--with-media" set INSTALL_MEDIA=1
if /I "%~2"=="--with-asr" set INSTALL_ASR=1

cd /d %WS%

where py >nul 2>nul
if %errorlevel%==0 (
  py -3.10 -m venv "%VENV%"
) else (
  python -m venv "%VENV%"
)

call "%VENV%\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 exit /b 1

python -m pip install -r "%WS%\requirements-recovery-core.txt"
if errorlevel 1 (
  echo [ERROR] Failed to install core recovery requirements.
  exit /b 1
)

if "%INSTALL_MEDIA%"=="1" (
  python -m pip install -r "%WS%\requirements-recovery-media.txt"
  if errorlevel 1 (
    echo [ERROR] Failed to install optional media requirements.
    exit /b 1
  )
)

if "%INSTALL_ASR%"=="1" (
  python -m pip install -r "%WS%\requirements-recovery-asr.txt"
  if errorlevel 1 (
    echo [ERROR] Failed to install optional ASR requirements.
    exit /b 1
  )
)

echo.
echo [OK] Recovery mod environment created at %VENV%
echo [INFO] Core editable backend stack installed.
if "%INSTALL_MEDIA%"=="1" echo [INFO] Media extras installed.
if "%INSTALL_ASR%"=="1" echo [INFO] ASR extras installed.
if "%INSTALL_MEDIA%"=="0" echo [INFO] Media extras not installed.
if "%INSTALL_ASR%"=="0" echo [INFO] ASR extras not installed.
echo [NEXT] Run run_backend_mod.bat to start backend with local Python.
endlocal
