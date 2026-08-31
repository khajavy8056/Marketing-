@echo off
setlocal EnableExtensions
title Tira - Build Offline Setup GUI
chcp 65001 >nul 2>nul
cd /d "%~dp0"

echo Opening graphical builder for offline Setup...

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY (
  where py >nul 2>nul
  if %errorlevel%==0 set "PY=py -3"
)
if not defined PY (
  where python >nul 2>nul
  if %errorlevel%==0 set "PY=python"
)
if not defined PY (
  echo Python not found - install from python.org
  pause
  exit /b 1
)

%PY% -m pip install -r requirements.txt pyinstaller --disable-pip-version-check --progress-bar off >nul 2>nul

:: Run GUI builder with progress bars for Chromium/Model using DownloadManager
%PY% installer\build_offline_gui.py

set EC=%errorlevel%
if "%EC%"=="0" (
  echo Build GUI closed
  exit /b 0
) else (
  echo Build failed code %EC%
  pause
  exit /b %EC%
)
