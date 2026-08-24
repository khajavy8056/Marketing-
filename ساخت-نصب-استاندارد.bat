@echo off
setlocal EnableExtensions
title Khajavy Lead - Build EXE
cd /d "%~dp0"

echo.
echo  ============================================
echo   Khajavy Lead - build standard EXE
echo  ============================================
echo  This builds DivarLead.exe on THIS Windows PC.
echo  Folder: %CD%
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

echo [1/4] Installing build tools...
"%PY%" -m pip install --upgrade pip --disable-pip-version-check --progress-bar off
"%PY%" -m pip install --disable-pip-version-check --progress-bar off -r requirements.txt pyinstaller
if errorlevel 1 (
  echo Trying PyPI mirror...
  "%PY%" -m pip install --disable-pip-version-check --progress-bar off -r requirements.txt pyinstaller -i https://mirror-pypi.runflare.com/simple
  if errorlevel 1 goto FAIL
)

echo [2/4] Building one-file EXE (a few minutes)...
if exist "build" rmdir /s /q build
if exist "dist\DivarLead.exe" del /q "dist\DivarLead.exe"

"%PY%" -m PyInstaller --noconfirm --clean --onefile --name DivarLead ^
  --collect-all uvicorn --collect-submodules uvicorn ^
  --hidden-import marketing_divar.web.server ^
  --hidden-import marketing_divar.web ^
  --add-data "marketing_divar\web\static;marketing_divar\web\static" ^
  main.py
if errorlevel 1 goto FAIL
if not exist "dist\DivarLead.exe" goto FAIL

echo [3/4] Copying to Desktop...
set "DEST=%USERPROFILE%\Desktop\DivarLead.exe"
copy /y "dist\DivarLead.exe" "%DEST%" >nul
copy /y "dist\DivarLead.exe" "%CD%\DivarLead.exe" >nul

echo [4/4] Done.
echo.
echo  EXE ready:
echo    %CD%\dist\DivarLead.exe
echo    %CD%\DivarLead.exe
echo    %DEST%
echo.
echo  Double-click DivarLead.exe  -  browser: http://localhost:8642
echo  Settings stay in %%LOCALAPPDATA%%\KhajavyLead
echo.
pause
exit /b 0

:FAIL
echo.
echo BUILD FAILED. Run Install-and-Run.bat first, then this file again.
pause
exit /b 1
