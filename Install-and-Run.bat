@echo off
REM DivarLead - GUI installer with progress bar (needs only Windows)
cd /d "%~dp0"
where powershell >nul 2>nul
if errorlevel 1 (
  echo [ERROR] PowerShell not found on this system.
  pause
  exit /b 1
)
powershell -NoProfile -STA -ExecutionPolicy Bypass -File "installer\installer.ps1"
set EC=%errorlevel%
if not "%EC%"=="0" (
  echo.
  echo ============================================================
  echo   Installer exited unexpectedly (error code %EC%).
  echo   The full technical log is saved here:
  echo   %~dp0installer\install-log.txt
  echo   Please send that file for support.
  echo ============================================================
  echo Press any key to close this window...
  pause >nul
)
exit /b %EC%
