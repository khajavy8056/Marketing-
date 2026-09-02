# -*- coding: utf-8 -*-
"""Build installer/payload.zip — every file the Setup EXE carries.
نسخه نهایی v3.8:
- همه فایل‌های سورس + مارکتینگ + اینستالر
- اگر --offline یا --include-all باشد، کرومیوم و مدل هم داخل payload می‌آیند
- رمزنگاری با SHA256 XOR + zlib برای فایل تکی Setup.exe
- یک فایل تکی رمز شده payload.zip.enc می‌سازد که داخل Setup.exe می‌رود
"""

from __future__ import annotations

import os
import sys
import zipfile
import zlib
import hashlib
from pathlib import Path
import argparse

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "payload.zip"
OUT_ENC = Path(__file__).resolve().parent / "payload.zip.enc"

SKIP_DIR = {
    ".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "build", "dist", "logs", "data", "node_modules",
    ".arena", "installer/nlu-download", "app-chromium"
}
SKIP_FILE = {"install-log.txt", "payload.zip", "payload.zip.enc", "payload.zip.enc.tmp"}

ENCRYPTION_KEY = b"DivarMarketing-2024-Secure-Key-Tira-v3.9-Final-Ultimate"

def _keep(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    # Skip hidden and temp
    if any(part in SKIP_DIR for part in rel.parts):
        return False
    # Skip by name
    if path.name in SKIP_FILE or path.suffix in {".pyc", ".pyo"}:
        return False
    # Skip large data files unless offline
    if "data/divar_leads.db" in str(rel):
        return False
    return True

def encrypt_data(data: bytes, key: bytes = ENCRYPTION_KEY) -> bytes:
    compressed = zlib.compress(data, level=6)
    key_hash = hashlib.sha256(key).digest()
    return bytes(b ^ key_hash[i % len(key_hash)] for i, b in enumerate(compressed))

def pack(dest: Path = OUT, include_chromium: bool = False, include_model: bool = False, encrypt: bool = False, offline: bool = False) -> Path:
    # سازگاری با فراخوانی قدیمی pack(offline=True)
    if offline:
        include_chromium = True
        include_model = True
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    if OUT_ENC.exists() and encrypt:
        OUT_ENC.unlink()

    count = 0
    total_size = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # سورس اصلی
        for dirpath, dirnames, filenames in os.walk(ROOT):
            pdir = Path(dirpath)
            # فیلتر دایرکتوری‌ها
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIR and not d.startswith(".")]
            # اگر offline نیست، chromium و model را skip کن (بعداً جدا اضافه می‌کنیم اگر خواسته)
            if not include_chromium and "app-chromium" in str(pdir):
                continue
            if not include_model and "nlu-model" in str(pdir):
                continue
            for name in filenames:
                src = pdir / name
                if not _keep(src):
                    continue
                # Skip chromium files unless requested
                if not include_chromium and "app-chromium" in str(src):
                    continue
                if not include_model and ("nlu-model" in str(src) or "nlu-download" in str(src)):
                    continue
                try:
                    arcname = src.relative_to(ROOT).as_posix()
                    zf.write(src, arcname)
                    count += 1
                    total_size += src.stat().st_size
                except Exception as e:
                    print(f"Skip {src}: {e}")
                    continue
        
        # اگر offline، کرومیوم را از data_dir اضافه کن
        if include_chromium:
            try:
                local_appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
                chrome_src = Path(local_appdata) / "DivarMarketing" / "app-chromium"
                if chrome_src.exists():
                    for dirpath, _, filenames in os.walk(chrome_src):
                        pdir = Path(dirpath)
                        for name in filenames:
                            src = pdir / name
                            if src.stat().st_size > 100_000_000:  # skip huge files >100MB single?
                                continue
                            arcname = f"app-chromium/{src.relative_to(chrome_src).as_posix()}"
                            try:
                                zf.write(src, arcname)
                                count += 1
                            except Exception:
                                pass
                    print(f"Added Chromium from {chrome_src}")
            except Exception as e:
                print(f"Chromium add failed: {e}")

        # مدل
        if include_model:
            try:
                local_appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
                model_src = Path(local_appdata) / "DivarMarketing" / "app" / "nlu-model"
                if not model_src.exists():
                    model_src = Path(local_appdata) / "DivarMarketing" / "nlu-model"
                if model_src.exists():
                    for dirpath, _, filenames in os.walk(model_src):
                        pdir = Path(dirpath)
                        for name in filenames:
                            src = pdir / name
                            arcname = f"nlu-model/{src.relative_to(model_src).as_posix()}"
                            try:
                                zf.write(src, arcname)
                                count += 1
                            except Exception:
                                pass
                    print(f"Added model from {model_src}")
            except Exception as e:
                print(f"Model add failed: {e}")

    if not dest.exists() or dest.stat().st_size < 1000:
        raise RuntimeError("payload.zip is too small")

    print(f"Packed {count} files -> {dest} ({dest.stat().st_size // 1024 // 1024} MB, raw {total_size // 1024 // 1024} MB)")

    if encrypt:
        data = dest.read_bytes()
        enc = encrypt_data(data)
        OUT_ENC.write_bytes(enc)
        print(f"Encrypted -> {OUT_ENC} ({OUT_ENC.stat().st_size // 1024 // 1024} MB) — رمزنگاری شده برای Setup.exe تکی")
        return OUT_ENC

    return dest

def main():
    parser = argparse.ArgumentParser(description="Pack payload for installer")
    parser.add_argument("--offline", action="store_true", help="Include chromium and model if available")
    parser.add_argument("--include-chromium", action="store_true", help="Include chromium")
    parser.add_argument("--include-model", action="store_true", help="Include model")
    parser.add_argument("--encrypt", action="store_true", help="Encrypt to payload.zip.enc")
    parser.add_argument("--all", action="store_true", help="Include all + encrypt — for final single-file setup")
    args = parser.parse_args()

    include_chrome = args.offline or args.include_chromium or args.all
    include_model = args.offline or args.include_model or args.all
    encrypt = args.encrypt or args.all

    # اگر --all، همه چیز + رمزنگاری
    dest = OUT
    result = pack(dest, include_chromium=include_chrome, include_model=include_model, encrypt=encrypt)
    print(f"✅ Ready: {result}")

if __name__ == "__main__":
    main()
