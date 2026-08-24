@echo off
REM Build DivarLead.exe (Windows). Same as ..\ساخت-نصب-استاندارد.bat
cd /d "%~dp0.."
if exist "ساخت-نصب-استاندارد.bat" (
  call "ساخت-نصب-استاندارد.bat"
  exit /b %errorlevel%
)
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --onefile --name DivarLead --collect-all uvicorn --add-data "marketing_divar\web\static;marketing_divar\web\static" main.py
echo Done: dist\DivarLead.exe
pause
