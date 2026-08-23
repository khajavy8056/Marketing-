# -*- coding: utf-8 -*-
"""مسیر پایدار دادهٔ کاربر — تنظیمات بعد از بستن/باز کردن و نصب دوباره می‌ماند.

دیتابیس، اکانت‌ها، قالب‌ها، تلگرام و ملی‌پیامک در پوشهٔ ثابت کاربر ذخیره
می‌شوند نه کنار هر Extract جدید:
  ویندوز:  %LOCALAPPDATA%\\KhajavyLead
  لینوکس:  ~/.local/share/khajavy-lead

متغیرهای DIVAR_DB_PATH / DIVAR_ACCOUNTS_DIR اگر از قبل باشند دست نمی‌خورند
(تست‌ها و مسیر سفارشی).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


APP_DIR_NAME = "KhajavyLead"


def user_data_dir() -> Path:
    override = os.environ.get("DIVAR_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_DIR_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "khajavy-lead"
    return Path.home() / ".local" / "share" / "khajavy-lead"


def _copy_if_missing(src: Path, dst: Path) -> None:
    if not src.exists() or dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)


def migrate_legacy(dest: Path, cwd: Path | None = None) -> None:
    """اگر پوشهٔ پایدار خالی است، data/ کنار برنامه را یک‌بار منتقل می‌کند."""
    root = cwd or Path.cwd()
    legacy = root / "data"
    if not legacy.exists():
        return
    _copy_if_missing(legacy / "divar_leads.db", dest / "divar_leads.db")
    acc_src, acc_dst = legacy / "accounts", dest / "accounts"
    if acc_src.is_dir():
        acc_dst.mkdir(parents=True, exist_ok=True)
        for item in acc_src.iterdir():
            target = acc_dst / item.name
            if not target.exists():
                if item.is_dir():
                    shutil.copytree(item, target)
                else:
                    shutil.copy2(item, target)
    cfg = root / "config.json"
    _copy_if_missing(cfg, dest / "config.json")


def apply_runtime_paths() -> Path:
    """پوشهٔ پایدار را می‌سازد و متغیرهای محیطی پیش‌فرض را می‌گذارد."""
    dest = user_data_dir()
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "accounts").mkdir(exist_ok=True)
    (dest / "logs").mkdir(exist_ok=True)
    migrate_legacy(dest)
    os.environ.setdefault("DIVAR_DATA_DIR", str(dest))
    os.environ.setdefault("DIVAR_DB_PATH", str(dest / "divar_leads.db"))
    os.environ.setdefault("DIVAR_ACCOUNTS_DIR", str(dest / "accounts"))
    os.environ.setdefault("DIVAR_LOG_DIR", str(dest / "logs"))
    os.environ.setdefault("DIVAR_CONFIG_PATH", str(dest / "config.json"))
    return dest
