@echo off
setlocal EnableExtensions
title Tira - Build Offline Setup 1-2GB
chcp 65001 >nul 2>nul
cd /d "%~dp0"

echo.
echo  ============================================
echo   Tira - Sakht Nasb Konande Offline
echo   Offline Setup Builder 1-2GB
echo  ============================================
echo   In file nasb konande offline misazad:
echo   - Chromium + Model Qwen dakhelesh hast
echo   - Dar system maghsad niaz be download nadarad
echo   - Code ramznegari shode (PyInstaller)
echo   Khoroji: dist\DivarMarketing-Setup.exe
echo  ============================================
echo.

if not exist "main.py" goto FAIL
if not exist "requirements.txt" goto FAIL

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
  echo [ERROR] Python not found
  pause
  exit /b 1
)

echo [0/6] Python: %PY%
%PY% --version

echo [1/6] Installing build tools...
%PY% -m pip install --upgrade pip --disable-pip-version-check --progress-bar off >nul 2>nul
%PY% -m pip install -r requirements.txt pyinstaller --disable-pip-version-check --progress-bar off
if errorlevel 1 (
  %PY% -m pip install -r requirements.txt pyinstaller -i https://mirror-pypi.runflare.com/simple --disable-pip-version-check --progress-bar off
  if errorlevel 1 goto FAIL
)

echo [2/6] Building icon...
%PY% installer\png_to_ico.py

echo [3/6] Downloading Chromium for offline...
%PY% main.py --install-chromium
if errorlevel 1 echo [WARN] Chromium will retry

echo [4/6] Downloading Tira model for offline...
%PY% main.py --install-nlu
if errorlevel 1 echo [WARN] Model fallback

echo [5/6] Packing ALL files into payload (1-2GB)...
%PY% installer\pack_payload.py --offline
if errorlevel 1 goto FAIL
for %%A in ("installer\payload.zip") do echo Payload: %%~zA bytes

echo [6/6] Building encrypted Setup.exe...
if exist "build" rmdir /s /q build
if exist "dist\DivarMarketing-Setup.exe" del /q "dist\DivarMarketing-Setup.exe"
if exist "dist\DivarMarketing.exe" del /q "dist\DivarMarketing.exe"

%PY% -m PyInstaller --noconfirm --clean --onefile --name DivarMarketing ^
  --icon "installer\app.ico" ^
  --collect-all uvicorn --collect-submodules uvicorn ^
  --collect-all playwright --collect-submodules playwright ^
  --hidden-import marketing_divar.web.server ^
  --hidden-import marketing_divar.desktop_app ^
  --hidden-import marketing_divar.nlu_model ^
  --add-data "marketing_divar\web\static;marketing_divar\web\static" ^
  --add-data "installer\fetch_chromium.py;." ^
  --add-data "installer\app.ico;." ^
  main.py
if errorlevel 1 goto FAIL

%PY% -c "import zipfile; z=zipfile.ZipFile('installer/payload.zip','a',zipfile.ZIP_DEFLATED); z.write('dist/DivarMarketing.exe','DivarMarketing.exe'); z.close(); print('added exe')"

%PY% -m PyInstaller --noconfirm --clean --onefile --windowed --name DivarMarketing-Setup ^
  --icon "installer\app.ico" ^
  --add-data "installer\payload.zip;." ^
  --add-data "installer\app.ico;." ^
  --add-data "installer\fetch_chromium.py;." ^
  installer\setup_app.py
if errorlevel 1 goto FAIL

copy /y "dist\DivarMarketing-Setup.exe" "%USERPROFILE%\Desktop\DivarMarketing-Setup.exe" >nul 2>nul

echo.
echo  DONE: %CD%\dist\DivarMarketing-Setup.exe
echo  Desktop: %USERPROFILE%\Desktop\DivarMarketing-Setup.exe
echo  Size 1-2GB offline, no download needed at install
echo  Double-click -> graphical install -> native Tira window
echo.
pause
exit /b 0

:FAIL
echo BUILD FAILED
pause
exit /b 1
