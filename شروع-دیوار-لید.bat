@echo off
REM ═══════════════════════════════════════════════════════════════
REM  دیوار لید — نصب‌کننده و اجراکننده خودکار ویندوز
REM  ۱. بررسی/نصب خودکار پایتون (نصب کاربر، بدون نیاز به ادمین)
REM  ۲. نصب پیش‌نیازها (با سرور جایگزین در صورت قطعی PyPI)
REM  ۳. تست سلامت کامل برنامه
REM  ۴. اجرای رابط گرافیکی
REM ═══════════════════════════════════════════════════════════════
setlocal EnableExtensions
chcp 65001 >nul
title دیوار لید — نصب و اجرا
cd /d "%~dp0"

set "PYVER=3.11.9"
set "PYURL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
set "PYDIR=%LOCALAPPDATA%\Programs\Python\Python311"
set "PYEXE="

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║     دیوار لید — راه‌اندازی خودکار          ║
echo  ╚══════════════════════════════════════════╝
echo.

REM ─── بررسی: فایل‌ها Extract شده‌اند؟ ────────────────────────────
if not exist main.py (
  echo  [خطا] فایل‌های برنامه پیدا نشد!
  echo  اول ZIP را روی کامپیوتر Extract کنید بعد این فایل را اجرا کنید.
  pause & exit /b 1
)
if not exist requirements.txt (
  echo  [خطا] فایل requirements.txt پیدا نشد — Extract کامل نیست.
  pause & exit /b 1
)

echo  [1/4] بررسی پایتون...
call :find_python
if not defined PYEXE (
  echo        پایتون پیدا نشد ← دانلود و نصب خودکار نسخه %PYVER%
  call :install_python
)
if not defined PYEXE goto :pyfail
echo        ✓ پایتون آماده:
"%PYEXE%" --version
echo.

echo  [2/4] نصب پیش‌نیازها (بار اول چند دقیقه)...
"%PYEXE%" -m pip install --disable-pip-version-check -q --upgrade pip 2>nul
"%PYEXE%" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
  echo        تلاش با سرور جایگزین (mirror)...
  "%PYEXE%" -m pip install --disable-pip-version-check -q -r requirements.txt -i https://mirror-pypi.runflare.com/simple
  if errorlevel 1 goto :pipfail
)
echo        ✓ پیش‌نیازها نصب شد
echo.

echo  [3/4] تست سلامت برنامه...
"%PYEXE%" main.py --check
if errorlevel 1 (
  echo.
  echo  [خطا] تست سلامت ناموفق بود — پیام بالا را به پشتیبانی بدهید.
  pause & exit /b 1
)
echo.

echo  [4/4] اجرای برنامه...  (مرورگر خودکار باز می‌شود)
echo  ─────────────────────────────────────────────
echo   آدرس دستی:  http://localhost:8642
echo   خروج: بستن همین پنجره
echo   داده‌ها و لاگ‌ها: پوشه‌های data و logs همین مسیر
echo  ─────────────────────────────────────────────
echo.
"%PYEXE%" main.py
echo.
echo  برنامه بسته شد. (اگر بی‌دلیل بسته شد، logs\divar_app.log را ببینید)
pause
exit /b 0

REM ═════════════════════ زیربرنامه‌ها ═════════════════════

:find_python
REM ترتیب: py launcher ← python مسیر ← مسیر پیش‌فرض نصب کاربر
py -3 -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
if not errorlevel 1 (
  for /f "usebackq delims=" %%i in (`py -3 -c "import sys; print(sys.executable)"`) do set "PYEXE=%%i"
  goto :eof
)
python -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
if not errorlevel 1 (
  for /f "usebackq delims=" %%i in (`python -c "import sys; print(sys.executable)"`) do set "PYEXE=%%i"
  goto :eof
)
if exist "%PYDIR%\python.exe" set "PYEXE=%PYDIR%\python.exe"
goto :eof

:install_python
set "DL=%TEMP%\divar-python-%PYVER%.exe"
echo        در حال دانلود پایتون (~۲۵ مگابایت)...
where curl >nul 2>nul
if not errorlevel 1 (
  curl -L --progress-bar -o "%DL%" "%PYURL%"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -Uri '%PYURL%' -OutFile '%DL%'"
)
if not exist "%DL%" (
  echo        [خطا] دانلود پایتون ناموفق — اینترنت را بررسی کنید.
  goto :eof
)
echo        نصب بی‌صدا (۱ تا ۳ دقیقه؛ پنجره‌ای باز نمی‌شود)...
"%DL%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1 Include_test=0
if exist "%PYDIR%\python.exe" set "PYEXE=%PYDIR%\python.exe"
del "%DL%" >nul 2>nul
goto :eof

:pyfail
echo.
echo  ═══ [خطای پایتون] ═══
echo  نصب خودکار پایتون ناموفق بود. راه دستی:
echo  1. از python.org/downloads نسخه 3.11 را دستی نصب کنید (تیک Add to PATH!)
echo  2. دوباره این فایل را اجرا کنید.
pause & exit /b 1

:pipfail
echo.
echo  ═══ [خطای نصب پیش‌نیازها] ═══
echo  دانلود کتابخانه‌ها ناموفق بود — اینترنت (یا فیلترشکن) را بررسی و دوباره اجرا کنید.
pause & exit /b 1
