@echo off
setlocal
set WS=D:\Extend_C\Program\zenclip\audit\recovery-workspace\backend
set RUNTIME=%WS%\runtime\portable
set FRONTEND=D:\Extend_C\Program\zenclip\audit\recovery-workspace\frontend-reconstructed

if not exist "%RUNTIME%" mkdir "%RUNTIME%"
if not exist "%RUNTIME%\app-data" mkdir "%RUNTIME%\app-data"
if not exist "%RUNTIME%\templates" mkdir "%RUNTIME%\templates"
if not exist "%RUNTIME%\static" mkdir "%RUNTIME%\static"
if not exist "%RUNTIME%\static\recovery" mkdir "%RUNTIME%\static\recovery"
if not exist "%RUNTIME%\logs" mkdir "%RUNTIME%\logs"

echo [INFO] Syncing portable static assets...
robocopy "%WS%\static" "%RUNTIME%\static" /E /NFL /NDL /NJH /NJS /NC /NS >nul
copy /Y "%FRONTEND%\app.js" "%RUNTIME%\static\recovery\app.js" >nul
copy /Y "%FRONTEND%\styles.css" "%RUNTIME%\static\recovery\styles.css" >nul

echo [INFO] Writing portable templates...
copy /Y "%FRONTEND%\index.html" "%RUNTIME%\templates\index.html" >nul
powershell -NoProfile -Command "(Get-Content '%RUNTIME%\templates\index.html' -Raw).Replace('./styles.css','/static/recovery/styles.css').Replace('./app.js','/static/recovery/app.js') | Set-Content '%RUNTIME%\templates\index.html'"

copy /Y "%RUNTIME%\templates\index.html" "%RUNTIME%\templates\guide.html" >nul
copy /Y "%RUNTIME%\templates\index.html" "%RUNTIME%\templates\about.html" >nul
copy /Y "%RUNTIME%\templates\index.html" "%RUNTIME%\templates\about_api.html" >nul
copy /Y "%RUNTIME%\templates\index.html" "%RUNTIME%\templates\gallery.html" >nul

echo [INFO] Portable runtime ready at %RUNTIME%
endlocal
