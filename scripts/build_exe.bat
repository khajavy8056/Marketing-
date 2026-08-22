@echo off
REM ساخت نسخه نصبی ویندوز (این فایل را روی ویندوز اجرا کنید)
REM پیش‌نیاز: پایتون 3.10+ نصب باشد
REM خروجی: dist\DivarLead.exe (تک‌فایل، قابل اجرا بدون نصب پایتون)
pip install -r requirements.txt pyinstaller
pyinstaller --name DivarLead --onefile ^
  --add-data "marketing_divar/web/static;marketing_divar/web/static" ^
  marketing_divar/web/__main__.py
echo.
echo تمام! فایل اجرایی: dist\DivarLead.exe
pause
