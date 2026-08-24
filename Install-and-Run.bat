@echo off
setlocal EnableExtensions
title Khajavy Lead Installer
cd /d "%~dp0"

echo.
echo  ============================================
echo   Khajavy Lead - Install
echo  ============================================
echo  Folder: %CD%
echo.

if not exist "installer\installer.ps1" goto NOEXTRACT
if not exist "main.py" goto NOEXTRACT
if not exist "requirements.txt" goto NOEXTRACT

where powershell >nul 2>nul
if errorlevel 1 (
  echo [ERROR] PowerShell was not found.
  echo Windows needs PowerShell for this installer.
  goto FAIL
)

echo Unlocking files after ZIP extract...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath '%CD%' -Recurse -Include *.ps1,*.bat -ErrorAction SilentlyContinue | Unblock-File" 1>nul 2>nul

echo Opening installer window...
powershell -NoProfile -STA -ExecutionPolicy Bypass -File "installer\installer.ps1"
set EC=%errorlevel%
if "%EC%"=="0" (
  echo Installer window closed.
  exit /b 0
)

echo.
echo GUI installer did not finish (code %EC%).
echo Starting console install in this window...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "installer\install-console.ps1"
set EC=%errorlevel%
if "%EC%"=="0" exit /b 0
goto FAIL

:NOEXTRACT
echo [ERROR] Required files are missing.
echo.
echo Extract the ZIP first:
echo   Right-click the zip -^> Extract All
echo   Then open the extracted folder and double-click Install-and-Run.bat
echo.
echo Do not run this file from inside the zip window.
echo.
goto FAIL

:FAIL
echo.
echo ============================================================
echo  Install did not finish.
echo  Log 1: %TEMP%\khajavy-lead-install.log
echo  Log 2: %CD%\installer\install-log.txt
echo ============================================================
echo.
echo This window will stay open so you can read the error.
pause
exit /b 1
