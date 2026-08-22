#!/usr/bin/env bash
# اجرای رابط وب روی سیستم داخل ایران
set -e
pip install -r requirements.txt
python3 -m marketing_divar.web
