@echo off
setlocal EnableExtensions
title Divar Marketing - Build Standard Installer GUI v4.1 Native

REM v4.1 Native — این فایل فقط GUI سازنده را باز می‌کند — بدون کنسول سیاه — بدون CLI
REM ریشه مشکل قبلی: این .bat قبلاً CLI اجرا می‌کرد، حالا فقط GUI نیتیو

cd /d "%~dp0"

echo.
echo  ============================================
echo   Divar Marketing - Build GUI v4.1 Native
echo   Native Windows Installer Builder
echo  ============================================
echo  Opening GUI builder — no black console...
echo.

if not exist "main.py" (
  echo [ERROR] main.py not found — run from project root
  pause
  exit /b 1
)

REM پیدا کردن pythonw برای GUI بدون کنسول
set "PYW="
if exist ".venv\Scripts\pythonw.exe" (
  set "PYW=.venv\Scripts\pythonw.exe"
) else (
  where pythonw >nul 2>nul
  if not errorlevel 1 (
    for /f "delims=" %%i in ('where pythonw') do set "PYW=%%i" & goto FOUND_PYW
    :FOUND_PYW
  )
)

if "%PYW%"=="" (
  REM fallback به python
  if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
  ) else (
    set "PY=python"
  )
  echo [INFO] pythonw not found, using %PY% with GUI...
  "%PY%" installer\build_offline_gui.py
  if errorlevel 1 (
    echo [ERROR] GUI failed to start
    echo Trying with pythonw...
    pythonw installer\build_offline_gui.py
  )
) else (
  echo [INFO] Launching GUI with %PYW% — no console...
  "%PYW%" installer\build_offline_gui.py
  if errorlevel 1 (
    echo [WARN] pythonw failed, trying python...
    if exist ".venv\Scripts\python.exe" (
      ".venv\Scripts\python.exe" installer\build_offline_gui.py
    ) else (
      python installer\build_offline_gui.py
    )
  )
)

REM اگر GUI بسته شد، لاگ را نشان بده
if exist "build-offline.log" (
  echo.
  echo  Log: %CD%\build-offline.log
)

echo.
echo  GUI closed. Check dist\ for Setup.exe
echo  If GUI did not open, try:
echo    python installer\build_offline_gui.py
echo    or
echo    .venv\Scripts\pythonw.exe installer\build_offline_gui.py
echo.
pause
exit /b 0
