@echo off
setlocal EnableExtensions
title Khajavy Lead
cd /d "%~dp0"

if not exist "main.py" goto NOEXTRACT
if not exist "installer\installer.ps1" goto NOEXTRACT

if exist ".venv\Scripts\python.exe" (
  echo Checking previous install...
  ".venv\Scripts\python.exe" -c "import fastapi,uvicorn" 1>nul 2>nul
  if not errorlevel 1 (
    echo Starting Khajavy Lead...
    set PYTHONUTF8=1
    start "Khajavy Lead" ".venv\Scripts\python.exe" main.py
    ping -n 4 127.0.0.1 >nul
    start "" "http://localhost:8642"
    echo App started: http://localhost:8642
    ping -n 6 127.0.0.1 >nul
    exit /b 0
  )
  echo Previous install is incomplete. Opening installer...
)

where powershell >nul 2>nul
if errorlevel 1 (
  echo [ERROR] PowerShell not found.
  goto FAIL
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath '%CD%' -Recurse -Include *.ps1,*.bat -ErrorAction SilentlyContinue | Unblock-File" 1>nul 2>nul
powershell -NoProfile -STA -ExecutionPolicy Bypass -File "installer\installer.ps1"
set EC=%errorlevel%
if "%EC%"=="0" exit /b 0

echo GUI installer failed (code %EC%). Console install...
powershell -NoProfile -ExecutionPolicy Bypass -File "installer\install-console.ps1"
set EC=%errorlevel%
if "%EC%"=="0" exit /b 0
goto FAIL

:NOEXTRACT
echo [ERROR] Extract the ZIP first (right-click - Extract All).
echo Do not run from inside the zip window.
goto FAIL

:FAIL
echo.
echo Install did not finish.
echo Log: %TEMP%\khajavy-lead-install.log
echo Log: %CD%\installer\install-log.txt
pause
exit /b 1
