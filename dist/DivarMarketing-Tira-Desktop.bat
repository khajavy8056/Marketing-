@echo off
setlocal EnableExtensions
title Tira Desktop - Divar Marketing
cd /d "%~dp0"
echo.
echo  ============================================
echo   🧠 تیرا - دستیار شکار حرفه‌ای
echo   Divar Marketing - Tira Desktop v3.4.0
echo  ============================================
echo   Native window without browser
echo   Model auto-installs with DownloadManager
echo.

if not exist "main.py" (
  echo [INFO] main.py not found in this folder.
  echo Searching parent folder...
  cd /d "%~dp0.."
)

if not exist "main.py" (
  echo [ERROR] Could not find main.py
  echo Download full zip from Releases:
  echo https://github.com/khajavy8056/Marketing-/releases
  pause
  exit /b 1
)

where python >nul 2>nul
if %errorlevel% neq 0 (
  where py >nul 2>nul
  if %errorlevel% equ 0 (
    set "PY=py -3"
  ) else (
    echo [ERROR] Python not found. Install Python 3.11 from python.org
    pause
    exit /b 1
  )
) else (
  set "PY=python"
)

echo [1/4] Installing dependencies...
%PY% -m pip install -r requirements.txt --disable-pip-version-check -q
if %errorlevel% neq 0 (
  echo Trying mirror...
  %PY% -m pip install -r requirements.txt -i https://mirror-pypi.runflare.com/simple --disable-pip-version-check -q
)

echo [2/4] Checking Chromium (DownloadManager)...
%PY% main.py --install-chromium
if %errorlevel% neq 0 echo [WARN] Chromium will retry in panel

echo [3/4] Checking Tira model (DownloadManager - auto install if missing)...
%PY% main.py --install-nlu
if %errorlevel% neq 0 echo [WARN] Tira fallback active - panel will retry

echo [4/4] Opening Tira Desktop (native window, no browser)...
echo   - Main panel: standalone window
echo   - Profiles: dedicated Chromium
echo   - Model: auto-installed with DownloadManager
echo.
%PY% main.py --desktop
if %errorlevel% neq 0 (
  echo [INFO] Desktop failed, trying web mode...
  %PY% main.py --web
)

pause
