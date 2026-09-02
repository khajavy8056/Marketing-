@echo off
REM v4.1 Native - اجرای برنامه با پنجره نیتیو ویندوز - بدون مرورگر - بدون کنسول سیاه
title Divar Marketing v4.1 Native - Tira

cd /d "%~dp0"

echo Starting Divar Marketing v4.1 Native Windows...
echo 🪟 پنجره نیتیو ویندوز - نه مرورگر
echo.

if exist ".venv\Scripts\pythonw.exe" (
  echo Launching with pythonw - no console - native window...
  start "" ".venv\Scripts\pythonw.exe" "main.py"
  exit /b 0
)

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "main.py"
) else (
  python "main.py"
)

pause
