@echo off
setlocal EnableExtensions
title Divar Marketing - Build Standard Encrypted Setup v3.8 Final
cd /d "%~dp0"

echo.
echo  ============================================
echo   Divar Marketing - Build Standard Setup v3.8 Final
echo   Single Encrypted File Installer
echo  ============================================
echo  This Windows PC will produce:
echo    dist\DivarMarketing.exe (main app)
echo    dist\DivarMarketing-Setup.exe (single encrypted installer with Chromium + Tira model)
echo    - Welcome/License/Location/Components wizard
echo    - Encrypted payload (SHA256 XOR + zlib)
echo    - Next/Next/Finish like Office
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

echo [1/6] Installing build tools + download manager...
"%PY%" -m pip install --upgrade pip --disable-pip-version-check --progress-bar off
"%PY%" -m pip install --disable-pip-version-check --progress-bar off -r requirements.txt pyinstaller requests tqdm certifi
if errorlevel 1 (
  echo Trying PyPI mirror...
  "%PY%" -m pip install --disable-pip-version-check --progress-bar off -r requirements.txt pyinstaller requests tqdm certifi -i https://mirror-pypi.runflare.com/simple
  if errorlevel 1 goto FAIL
)

echo [2/6] Building icon...
"%PY%" installer\png_to_ico.py
if not exist "installer\app.ico" echo [WARN] icon missing - Setup will use default

echo [3/6] Downloading Chromium with fast download manager (resume + speed)...
"%PY%" main.py --install-chromium
if errorlevel 1 echo [WARN] Chromium download will be retried in Setup

echo [4/6] Downloading Tira model with download manager...
"%PY%" main.py --install-nlu
if errorlevel 1 echo [WARN] Model fallback will be used

echo [5/6] Building DivarMarketing.exe (main app with all libs)...
if exist "build" rmdir /s /q build
if exist "dist\DivarMarketing.exe" del /q "dist\DivarMarketing.exe"

"%PY%" -m PyInstaller --noconfirm --clean --onefile --name DivarMarketing ^
  --icon "installer\app.ico" ^
  --collect-all uvicorn --collect-submodules uvicorn ^
  --collect-all playwright --collect-submodules playwright ^
  --hidden-import marketing_divar.web.server ^
  --hidden-import marketing_divar.web ^
  --hidden-import marketing_divar.app_chromium ^
  --hidden-import marketing_divar.chromium_profile ^
  --add-data "marketing_divar\web\static;marketing_divar\web\static" ^
  --add-data "installer\fetch_chromium.py;." ^
  main.py
if errorlevel 1 goto FAIL
if not exist "dist\DivarMarketing.exe" goto FAIL

echo [6/6] Packing ALL files + Chromium + Model into ENCRYPTED payload and building Setup.exe...
echo       (This creates single encrypted file Setup.exe like old versions)
"%PY%" installer\pack_payload.py --all
if errorlevel 1 goto FAIL

if exist "dist\DivarMarketing.exe" (
  echo Adding DivarMarketing.exe to encrypted payload...
  "%PY%" -c "import zipfile, pathlib, hashlib, zlib; p=pathlib.Path('installer/payload.zip'); enc=pathlib.Path('installer/payload.zip.enc'); key=b'DivarMarketing-2024-Secure-Key-Tira-v3.8'; kh=hashlib.sha256(key).digest(); raw=p.read_bytes() if p.exists() else enc.read_bytes(); print(f'Payload ready {len(raw)//1024//1024} MB')"
)

REM Check encrypted payload exists, else use plain
if exist "installer\payload.zip.enc" (
  set "PAYLOAD=installer\payload.zip.enc"
  echo Using encrypted payload: %PAYLOAD%
) else (
  set "PAYLOAD=installer\payload.zip"
  echo Using plain payload (encrypting now...): %PAYLOAD%
  "%PY%" installer\pack_payload.py --all
  if exist "installer\payload.zip.enc" set "PAYLOAD=installer\payload.zip.enc"
)

if not exist "%PAYLOAD%" goto FAIL

echo Building DivarMarketing-Setup.exe with Wizard UI (Welcome/License/Location/Components/Progress/Finish)...
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name DivarMarketing-Setup ^
  --icon "installer\app.ico" ^
  --add-data "%PAYLOAD%;." ^
  --add-data "installer\app.ico;." ^
  --add-data "installer\fetch_chromium.py;." ^
  installer\setup_app.py
if errorlevel 1 goto FAIL
if not exist "dist\DivarMarketing-Setup.exe" goto FAIL

echo Copying to Desktop...
copy /y "dist\DivarMarketing-Setup.exe" "%USERPROFILE%\Desktop\DivarMarketing-Setup.exe" >nul
copy /y "dist\DivarMarketing.exe" "%USERPROFILE%\Desktop\DivarMarketing.exe" >nul

for %%I in ("dist\DivarMarketing-Setup.exe") do set SIZE=%%~zI
set /a SIZE_MB=%SIZE%/1024/1024

echo.
echo  ============================================
echo   DONE - Standard Encrypted Installer Ready
echo  ============================================
echo    %CD%\dist\DivarMarketing-Setup.exe (%SIZE_MB% MB)
echo    %USERPROFILE%\Desktop\DivarMarketing-Setup.exe
echo.
echo  Features:
echo    - Single encrypted file (Chromium + Tira model inside)
echo    - Chic wizard: Welcome ^> License ^> Location ^> Components ^> Progress ^> Finish
echo    - Fast download manager during build
echo    - No code exposure - encrypted payload
echo    - Send this ONE file to any PC and install
echo.
echo  Double-click Setup. It installs, makes shortcuts,
echo  then opens http://127.0.0.1:8642
echo  Phone on same Wi-Fi: http://THIS-PC-IP:8642
echo.
pause
exit /b 0

:FAIL
echo.
echo [FAILED] See messages above.
pause
exit /b 1
