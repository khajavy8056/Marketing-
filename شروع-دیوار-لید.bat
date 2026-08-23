@echo off
REM DivarLead launcher (Persian name shortcut)
cd /d "%~dp0"
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
