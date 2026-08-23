@echo off
REM اجرای رابط وب روی ویندوز (سیستم داخل ایران)
cd /d "%~dp0.."
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" main.py
) else (
  python main.py
)
pause
