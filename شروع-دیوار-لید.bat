@echo off
chcp 65001 >nul
title دیوار لید - سیستم جمع‌آوری سرنخ
echo ============================================
echo    دیوار لید — راه‌اندازی اولیه
echo ============================================
echo.
where python >nul 2>nul
if errorlevel 1 (
  echo [خطا] پایتون نصب نیست!
  echo از python.org/downloads آخرین نسخه 3.11 را نصب کنید
  echo و حتماً تیک [Add python.exe to PATH] را بزنید.
  pause & exit /b 1
)
echo [1/2] نصب پیش‌نیازها (فقط بار اول چند دقیقه طول می‌کشد)...
python -m pip install -q -r requirements.txt
echo [2/2] اجرای برنامه... مرورگر خودکار باز می‌شود.
echo.
echo آدرس دستی: http://localhost:8642
echo برای خروج: این پنجره را ببندید.
echo.
python main.py
pause
