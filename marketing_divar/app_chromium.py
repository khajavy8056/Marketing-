# -*- coding: utf-8 -*-
"""Chromium اختصاصی برنامه — جدا از مرورگر و پروفایل کاربر.

دانلود از GitHub (ungoogled-chromium)، نه CDN فیلترشدهٔ Playwright.
پوشه: %LOCALAPPDATA%\\DivarMarketing\\app-chromium
پروفایل لاگین هر اکانت جداست: accounts/<name>/chromium/
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Callable, Optional

from .paths import user_data_dir

LogFn = Callable[[str], None]
ProgressFn = Callable[[int], None]


def _load_fetch():
    cands = []
    here = Path(__file__).resolve()
    cands.append(here.parents[1] / "installer" / "fetch_chromium.py")
    if getattr(sys, "frozen", False):
        mei = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        cands.extend([
            mei / "fetch_chromium.py",
            mei / "installer" / "fetch_chromium.py",
            Path(sys.executable).parent / "fetch_chromium.py",
        ])
    for p in cands:
        if p.exists():
            spec = importlib.util.spec_from_file_location("divar_fetch_chromium", p)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
    raise RuntimeError("installer/fetch_chromium.py missing")


_fc = _load_fetch()


def browsers_dir() -> Path:
    override = __import__("os").environ.get("DIVAR_CHROMIUM_DIR")
    if override:
        return Path(override)
    return user_data_dir() / "app-chromium"


def apply_browser_env() -> Path:
    dest = browsers_dir()
    dest.mkdir(parents=True, exist_ok=True)
    import os
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(dest)
    os.environ["DIVAR_CHROMIUM_DIR"] = str(dest)
    os.environ.pop("PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD", None)
    return dest


def find_chrome(root: Optional[Path] = None):
    return _fc.find_chrome(root or browsers_dir())


def executable_path() -> str:
    apply_browser_env()
    found = find_chrome()
    if not found:
        raise RuntimeError(
            "Chromium اختصاصی برنامه نصب نیست. نصب‌کننده باید ungoogled-chromium "
            "را در پوشهٔ DivarMarketing\\app-chromium بگذارد."
        )
    return str(found)


def _extract_zip(zpath, dest_folder, log):
    return _fc._extract_zip(zpath, dest_folder, log)


def github_zip_urls():
    return _fc.github_zip_urls()


def ensure_installed(log: Optional[LogFn] = None,
                     progress: Optional[ProgressFn] = None,
                     force: bool = False) -> Path:
    apply_browser_env()
    return _fc.ensure_installed(log=log, progress=progress, force=force)
