@echo off
REM ساخت نسخه نصبی ویندوز (روی ویندوز خودتان - بدون نیاز به GitHub)
pip install -r requirements.txt pyinstaller
pyinstaller --name DivarLead --onefile --noconfirm ^
  --collect-submodules uvicorn ^
  --add-data "marketing_divar/web/static;marketing_divar/web/static" ^
  main.py
echo.
echo تمام! فایل اجرایی: dist\DivarLead.exe
pause
