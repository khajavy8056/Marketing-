# -*- coding: utf-8 -*-
"""🧠 تیرا — Build installer/payload.zip
- حالت عادی: فقط سورس
- حالت آفلاین (--offline): سورس + Chromium + مدل Qwen (1-2GB) برای نصب بدون دانلود
"""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "payload.zip"

SKIP_DIR = {
    ".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "build", "dist", "logs", "data", "node_modules",
    "nlu-download",  # کش دانلود موقت
}
SKIP_FILE = {"install-log.txt", "payload.zip"}
SKIP_EXT = {".pyc", ".pyo", ".part", ".tmp"}

def _keep(path: Path) -> bool:
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return False
    if any(part in SKIP_DIR for part in rel.parts):
        return False
    if path.name in SKIP_FILE:
        return False
    if path.suffix in SKIP_EXT:
        return False
    # فایل‌های حجیم مدل و کرومیوم فقط در حالت آفلاین
    if not getattr(_keep, "offline", False):
        # در حالت عادی، nlu-model و app-chromium را نادیده بگیر (چون دانلود می‌شوند)
        if "nlu-model" in rel.parts or "app-chromium" in rel.parts:
            return False
    return True

def _get_data_dirs():
    """پوشه‌های داده کاربر که ممکن است Chromium و مدل آنجا باشند"""
    dirs = []
    try:
        from marketing_divar.paths import user_data_dir
        ud = user_data_dir()
        dirs.append(ud)
    except Exception:
        pass
    # LOCALAPPDATA
    try:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        dirs.append(Path(base) / "DivarMarketing")
    except Exception:
        pass
    # همچنین پوشه‌های محلی کنار پروژه
    dirs.append(ROOT / "nlu-model")
    dirs.append(ROOT / "app-chromium")
    return dirs

def pack(dest: Path = OUT, offline: bool = False) -> Path:
    _keep.offline = offline
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    count = 0
    total_size = 0

    print(f"📦 Packing {'OFFLINE (with Chromium+Model)' if offline else 'ONLINE (source only)'} -> {dest}")

    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. سورس اصلی
        for dirpath, dirnames, filenames in os.walk(ROOT):
            pdir = Path(dirpath)
            # فیلتر پوشه‌ها
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIR and not d.startswith(".")]
            for name in filenames:
                src = pdir / name
                if not _keep(src):
                    continue
                try:
                    arc = src.relative_to(ROOT).as_posix()
                    zf.write(src, arc)
                    count += 1
                    total_size += src.stat().st_size
                    if count % 100 == 0:
                        print(f"  ... {count} files, {total_size // 1024 // 1024} MB")
                except Exception as e:
                    print(f"  skip {src}: {e}")

        # 2. اگر آفلاین: Chromium و مدل را هم اضافه کن
        if offline:
            print("📥 Adding Chromium and Model for offline installer...")
            data_dirs = _get_data_dirs()
            added = 0
            for d in data_dirs:
                if not d.exists():
                    continue
                # Chromium
                chrome_dir = d / "app-chromium" if d.name != "app-chromium" else d
                if chrome_dir.exists() and chrome_dir.is_dir():
                    for dirpath, dirnames, filenames in os.walk(chrome_dir):
                        for fn in filenames:
                            src = Path(dirpath) / fn
                            if src.suffix in {".part", ".tmp"}:
                                continue
                            try:
                                # ذخیره با مسیر نسبی: app-chromium/...
                                arc = f"app-chromium/{src.relative_to(chrome_dir).as_posix()}"
                                zf.write(src, arc)
                                added += 1
                                total_size += src.stat().st_size
                            except Exception:
                                pass
                    print(f"  + Chromium from {chrome_dir}: {added} files")
                # Model
                model_dir = d / "nlu-model" if d.name != "nlu-model" else d
                if model_dir.exists() and model_dir.is_dir():
                    for dirpath, dirnames, filenames in os.walk(model_dir):
                        for fn in filenames:
                            if fn == "INSTALLED.json":
                                continue
                            if fn.endswith(".part"):
                                continue
                            src = Path(dirpath) / fn
                            try:
                                arc = f"nlu-model/{src.relative_to(model_dir).as_posix()}"
                                zf.write(src, arc)
                                added += 1
                                total_size += src.stat().st_size
                                if src.stat().st_size > 10_000_000:
                                    print(f"  + Model file: {fn} {src.stat().st_size // 1024 // 1024} MB")
                            except Exception:
                                pass
                    print(f"  + Model from {model_dir}")

            # همچنین اگر dist/DivarMarketing.exe وجود دارد، اضافه کن (برای آفلاین)
            exe = ROOT / "dist" / "DivarMarketing.exe"
            if exe.exists():
                zf.write(exe, "DivarMarketing.exe")
                count += 1
                print(f"  + Main exe: {exe.stat().st_size // 1024 // 1024} MB")

    if dest.stat().st_size < 1000:
        raise RuntimeError("payload.zip is too small")

    print(f"✅ Packed {count} files -> {dest} ({dest.stat().st_size // 1024 // 1024} MB, raw {total_size // 1024 // 1024} MB)")
    if offline:
        print(f"📦 Offline payload ready - includes Chromium+Model, no download needed at install")
    else:
        print(f"📦 Online payload - Chromium+Model will be downloaded at install with DownloadManager")
    return dest

if __name__ == "__main__":
    offline = "--offline" in sys.argv
    pack(offline=offline)
