@echo off
REM خواجوی لید — اگر نصب شده باشد برنامه باز می‌شود؛ وگرنه نصب‌کننده
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set PYTHONUTF8=1
  start "" ".venv\Scripts\python.exe" main.py
  exit /b 0
)
powershell -NoProfile -STA -ExecutionPolicy Bypass -File "installer\installer.ps1"
set EC=%errorlevel%
if not "%EC%"=="0" (
  echo.
  echo ============================================================
  echo   Installer exited unexpectedly (error code %EC%).
  echo   Log file: %~dp0installer\install-log.txt
  echo ============================================================
  pause >nul
)
exit /b %EC%
