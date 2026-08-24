@echo off
setlocal EnableExtensions
title Divar Marketing - Build Setup EXE
cd /d "%~dp0"

echo.
echo  ============================================
echo   Divar Marketing - build one-file Setup
echo  ============================================
echo  This Windows PC will produce:
echo    dist\DivarMarketing.exe
echo    dist\DivarMarketing-Setup.exe
echo.

if not exist "main.py" goto FAIL
if not exist "requirements.txt" goto FAIL

where powershell >nul 2>nul
if errorlevel 1 (
  echo [ERROR] PowerShell not found.
  goto FAIL
)

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  echo Creating .venv first...
  where py >nul 2>nul && py -3 -m venv .venv
  if not exist ".venv\Scripts\python.exe" python -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Could not create venv. Run Install-and-Run.bat first.
    goto FAIL
  )
  set "PY=.venv\Scripts\python.exe"
)

echo [1/5] Installing build tools...
"%PY%" -m pip install --upgrade pip --disable-pip-version-check --progress-bar off
"%PY%" -m pip install --disable-pip-version-check --progress-bar off -r requirements.txt pyinstaller
if errorlevel 1 (
  echo Trying PyPI mirror...
  "%PY%" -m pip install --disable-pip-version-check --progress-bar off -r requirements.txt pyinstaller -i https://mirror-pypi.runflare.com/simple
  if errorlevel 1 goto FAIL
)

echo [2/5] Building icon...
"%PY%" installer\png_to_ico.py
if not exist "installer\app.ico" echo [WARN] icon missing - Setup will use default

echo [3/5] Building DivarMarketing.exe ...
if exist "build" rmdir /s /q build
if exist "dist\DivarMarketing.exe" del /q "dist\DivarMarketing.exe"

"%PY%" -m PyInstaller --noconfirm --clean --onefile --name DivarMarketing ^
  --icon "installer\app.ico" ^
  --collect-all uvicorn --collect-submodules uvicorn ^
  --hidden-import marketing_divar.web.server ^
  --hidden-import marketing_divar.web ^
  --add-data "marketing_divar\web\static;marketing_divar\web\static" ^
  main.py
if errorlevel 1 goto FAIL
if not exist "dist\DivarMarketing.exe" goto FAIL

echo [4/5] Packing payload and building Setup.exe ...
if exist "installer\_payload" rmdir /s /q "installer\_payload"
mkdir "installer\_payload"
copy /y "dist\DivarMarketing.exe" "installer\_payload\DivarMarketing.exe" >nul
if exist "installer\app.ico" copy /y "installer\app.ico" "installer\_payload\app.ico" >nul
if exist "installer\payload.zip" del /q "installer\payload.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'installer\_payload\*' -DestinationPath 'installer\payload.zip' -Force"
if not exist "installer\payload.zip" goto FAIL

"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name DivarMarketing-Setup ^
  --icon "installer\app.ico" ^
  --add-data "installer\payload.zip;." ^
  --add-data "installer\app.ico;." ^
  installer\setup_app.py
if errorlevel 1 goto FAIL
if not exist "dist\DivarMarketing-Setup.exe" goto FAIL

echo [5/5] Copying to Desktop...
copy /y "dist\DivarMarketing-Setup.exe" "%USERPROFILE%\Desktop\DivarMarketing-Setup.exe" >nul
copy /y "dist\DivarMarketing.exe" "%USERPROFILE%\Desktop\DivarMarketing.exe" >nul

echo.
echo  DONE. One installer file (no other files needed):
echo    %CD%\dist\DivarMarketing-Setup.exe
echo    %USERPROFILE%\Desktop\DivarMarketing-Setup.exe
echo.
echo  Double-click Setup. It installs, makes a desktop shortcut,
echo  then opens http://127.0.0.1:8642
echo  Phone on same Wi-Fi: http://THIS-PC-IP:8642
echo.
pause
exit /b 0

:FAIL
echo.
echo BUILD FAILED. Run Install-and-Run.bat first, then this file again.
pause
exit /b 1
