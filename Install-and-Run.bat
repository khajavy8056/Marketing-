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
if errorlevel 1 pause
