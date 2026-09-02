@echo off
REM v4.1 Native — سازنده نصب‌کننده — GUI تضمینی — بدون کنسول سیاه
title Divar Marketing - Builder GUI v4.1 Native - No Console

cd /d "%~dp0"

echo Opening Native Windows Builder GUI v4.1...
echo بدون کنسول سیاه - فقط پنل گرافیکی شیک

REM Try pythonw first (no console)
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "installer\build_offline_gui.py"
  exit /b 0
)

where pythonw >nul 2>nul
if not errorlevel 1 (
  start "" pythonw "installer\build_offline_gui.py"
  exit /b 0
)

REM Fallback to python with GUI
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "installer\build_offline_gui.py"
) else (
  python "installer\build_offline_gui.py"
)

pause
