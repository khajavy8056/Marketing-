@echo off
setlocal EnableExtensions
title Tira - Install and Run
chcp 65001 >nul 2>nul
cd /d "%~dp0"

echo.
echo  ============================================
echo   Tira - Dastyar Shekar Herfei
echo   Divar Marketing - Tira Desktop
echo   Nasb va Ejra Khodkar
echo  ============================================
echo  Folder: %CD%
echo.

if not exist "main.py" goto NOEXTRACT
if not exist "requirements.txt" goto NOEXTRACT
if not exist "installer\setup_app.py" goto NOEXTRACT

set "PY="
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 --version >nul 2>nul
  if %errorlevel%==0 set "PY=py -3"
)
if not defined PY (
  where python >nul 2>nul
  if %errorlevel%==0 set "PY=python"
)
if not defined PY (
  echo [ERROR] Python not found. Install Python 3.11 from python.org
  echo Lotfan Python 3.11 ra nasb konid - Add to PATH
  pause
  exit /b 1
)

echo [1/3] Python: %PY%
%PY% --version

if not exist ".venv\Scripts\python.exe" (
  echo [2/3] Creating venv...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo [ERROR] venv failed
    pause
    exit /b 1
  )
) else (
  echo [2/3] venv exists
)

set "VPY=.venv\Scripts\python.exe"

echo [3/3] Installing deps...
%VPY% -m pip install --upgrade pip --disable-pip-version-check --progress-bar off >nul 2>nul
%VPY% -m pip install -r requirements.txt --disable-pip-version-check --progress-bar off
if errorlevel 1 (
  echo [WARN] Trying mirror...
  %VPY% -m pip install -r requirements.txt -i https://mirror-pypi.runflare.com/simple --disable-pip-version-check --progress-bar off
  if errorlevel 1 (
    echo [ERROR] pip failed
    pause
    exit /b 1
  )
)

echo.
echo Opening Tira graphical installer...
echo.

%VPY% installer\setup_app.py
set EC=%errorlevel%

if "%EC%"=="0" (
  echo.
  echo Install complete - app running as native window
  timeout /t 3 >nul
  exit /b 0
) else (
  echo.
  echo Installer closed code %EC% - log: %TEMP%\tira-install.log
  pause
  exit /b %EC%
)

:NOEXTRACT
echo [ERROR] Files missing - Extract ZIP first
echo Right-click ZIP -^> Extract All
pause
exit /b 1
