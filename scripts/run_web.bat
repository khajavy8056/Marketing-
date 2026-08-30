@echo off
REM Run the panel on Windows. Console is minimized.
cd /d "%~dp0.."
set PYTHONUTF8=1
if exist ".venv\Scripts\python.exe" (
  start /min "Divar Marketing" ".venv\Scripts\python.exe" main.py
) else (
  start /min "Divar Marketing" python main.py
)
exit /b 0
