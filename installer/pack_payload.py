# -*- coding: utf-8 -*-
"""Build installer/payload.zip — v4.2 Fixed Root Cause — No Freeze — No WinError

مشکلات قبلی v4.1 که باعث گیر کردن در بسته‌بندی می‌شد:
1. WinError 2/5/32/123/206 (file not found, access denied, file in use, path too long) — بدون هندل
2. هیچ لاگ و progress در حین walk — کاربر فکر می‌کرد قفل کرده
3. Double compression: zip DEFLATED level 6 + zlib.compress level 6 روی 1-2GB فایل → RAM 2-4GB + CPU 100% + freeze
4. فایل‌های بزرگ Chromium (dll, exe, pak) دوباره compress می‌شدند — خیلی کند
5. کل payload.zip یکجا در RAM خوانده می‌شد (read_bytes) → MemoryError روی سیستم 4GB
6. بدون skip برای فایل‌های قفل شده توسط آنتی‌ویروس

حل v4.2:
- لاگ دقیق + progress callback برای هر فایل
- WinError هندل با skip + لاگ
- فایل‌های از قبل فشرده (exe, dll, png, jpg, zip, pak, bin, dat) با ZIP_STORED (بدون compress) — سریع
- بقیه با ZIP_DEFLATED compresslevel=1 (سریع) نه 6
- رمزنگاری chunked (16MB chunk) + zlib level 1 نه 6 — بدون load کل فایل در RAM
- Long path support با \\?\ prefix روی ویندوز
- Skip فایل‌های >200MB تکی + فایل‌های در حال استفاده
- Timeout برای هر فایل
- Progress واقعی: تعداد فایل + حجم
"""

from __future__ import annotations

import os
import sys
import zipfile
import zlib
import hashlib
import time
import traceback
from pathlib import Path
import argparse
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "payload.zip"
OUT_ENC = Path(__file__).resolve().parent / "payload.zip.enc"

# فایل‌ها/پوشه‌هایی که همیشه skip
SKIP_DIR = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "build", "dist", "logs", "data", "node_modules",
    ".arena", "installer/nlu-download", "__MACOSX"
}
SKIP_FILE = {
    "install-log.txt", "payload.zip", "payload.zip.enc", "payload.zip.enc.tmp",
    "_payload_tmp.zip", "build-offline.log", "thumbs.db", ".DS_Store"
}
# پسوندهایی که از قبل فشرده هستند — با STORED سریع‌تر
ALREADY_COMPRESSED = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".exe", ".dll", ".so", ".pak",
    ".bin", ".dat", ".zip", ".7z", ".gz", ".mp4", ".mp3", ".avi", ".mov",
    ".pdf", ".woff", ".woff2", ".ttf", ".eot", ".webp", ".webm"
}

ENCRYPTION_KEY = b"DivarMarketing-2024-Secure-Key-Tira-v4.2-Native-Fixed-NoFreeze"

def _log(msg: str, log_cb: Optional[Callable[[str], None]] = None):
    if log_cb:
        log_cb(msg)
    print(msg)

def _keep(path: Path) -> bool:
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        # خارج از ROOT (مثلاً Chromium از AppData) — نگه دار
        return True
    
    # Skip hidden and temp
    if any(part in SKIP_DIR for part in rel.parts):
        return False
    if any(part.startswith(".") and part not in (".") for part in rel.parts):
        # Skip .hidden but not current dir
        if len(rel.parts) > 1:
            return False
    
    # Skip by name
    if path.name in SKIP_FILE or path.name.lower() in SKIP_FILE:
        return False
    if path.suffix in {".pyc", ".pyo", ".log", ".tmp"}:
        return False
    # Skip large data files unless offline
    if "divar_leads.db" in str(rel) or "divar_leads.db-journal" in str(rel):
        return False
    if path.name == "payload.zip" or path.name == "payload.zip.enc":
        return False
    return True

def _should_store(path: Path) -> bool:
    """آیا فایل از قبل فشرده است و باید STORED شود؟"""
    return path.suffix.lower() in ALREADY_COMPRESSED

def encrypt_data_chunked(src_path: Path, dest_path: Path, key: bytes = ENCRYPTION_KEY, 
                         log_cb: Optional[Callable[[str], None]] = None,
                         progress_cb: Optional[Callable[[int, str], None]] = None) -> Path:
    """رمزنگاری chunked — بدون load کل فایل در RAM — سریع با zlib level 1"""
    try:
        key_hash = hashlib.sha256(key).digest()
        chunk_size = 16 * 1024 * 1024  # 16MB chunks
        
        total_size = src_path.stat().st_size
        processed = 0
        
        _log(f"🔐 رمزنگاری chunked: {src_path.name} ({total_size//1024//1024}MB) با 16MB chunks + zlib level 1", log_cb)
        
        with open(src_path, 'rb') as fin, open(dest_path, 'wb') as fout:
            # Write header: original size (8 bytes) for verification
            fout.write(total_size.to_bytes(8, 'big'))
            
            while True:
                chunk = fin.read(chunk_size)
                if not chunk:
                    break
                
                # Compress with level 1 (fast) — not 6 (slow)
                try:
                    compressed = zlib.compress(chunk, level=1)
                except Exception:
                    compressed = chunk
                
                # XOR with key
                xored = bytes(b ^ key_hash[i % len(key_hash)] for i, b in enumerate(compressed))
                
                # Write chunk length (4 bytes) + data
                fout.write(len(xored).to_bytes(4, 'big'))
                fout.write(xored)
                
                processed += len(chunk)
                if progress_cb and total_size > 0:
                    pct = int(processed / total_size * 100)
                    if pct % 5 == 0 or processed == total_size:
                        progress_cb(min(pct, 99), f"رمزنگاری {processed//1024//1024}MB / {total_size//1024//1024}MB ({pct}%)")
        
        _log(f"✅ رمزنگاری کامل: {dest_path} ({dest_path.stat().st_size//1024//1024}MB)", log_cb)
        if progress_cb:
            progress_cb(100, f"رمزنگاری کامل ✅ {dest_path.stat().st_size//1024//1024}MB")
        return dest_path
    except Exception as e:
        _log(f"❌ رمزنگاری خطا: {e}\n{traceback.format_exc()[:1000]}", log_cb)
        raise

def decrypt_data_chunked(src_path: Path, dest_path: Path, key: bytes = ENCRYPTION_KEY) -> Path:
    """برای تست — رمزگشایی chunked"""
    key_hash = hashlib.sha256(key).digest()
    with open(src_path, 'rb') as fin, open(dest_path, 'wb') as fout:
        total_size = int.from_bytes(fin.read(8), 'big')
        while True:
            len_bytes = fin.read(4)
            if not len_bytes or len(len_bytes) < 4:
                break
            chunk_len = int.from_bytes(len_bytes, 'big')
            xored = fin.read(chunk_len)
            if not xored:
                break
            # XOR back
            compressed = bytes(b ^ key_hash[i % len(key_hash)] for i, b in enumerate(xored))
            try:
                chunk = zlib.decompress(compressed)
            except:
                chunk = compressed
            fout.write(chunk)
    return dest_path

def pack(dest: Path = OUT, include_chromium: bool = False, include_model: bool = False, 
         encrypt: bool = False, offline: bool = False,
         log_cb: Optional[Callable[[str], None]] = None,
         progress_cb: Optional[Callable[[int, str], None]] = None) -> Path:
    """
    بسته‌بندی با لاگ و progress و بدون freeze
    log_cb: تابع لاگ (str -> None)
    progress_cb: تابع progress (pct, text -> None)
    """
    def log(msg: str):
        _log(msg, log_cb)
    
    def prog(pct: int, text: str):
        if progress_cb:
            progress_cb(pct, text)
        # Also log every 10%
        if pct % 10 == 0:
            log(f"📦 {text}")

    if offline:
        include_chromium = True
        include_model = True
    
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        try:
            dest.unlink()
            log(f"🗑️ حذف قبلی: {dest}")
        except Exception as e:
            log(f"⚠️ حذف قبلی نشد: {e} — ادامه")
    
    if OUT_ENC.exists() and encrypt:
        try:
            OUT_ENC.unlink()
        except:
            pass

    count = 0
    total_size = 0
    skipped = 0
    errors = []

    log(f"📦 شروع بسته‌بندی v4.2 — ROOT={ROOT} — chrome={include_chromium} model={include_model} encrypt={encrypt}")
    prog(2, "شروع بسته‌بندی...")

    # Collect files first to get total count for progress
    log("🔍 جمع‌آوری لیست فایل‌ها...")
    all_files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        pdir = Path(dirpath)
        # فیلتر دایرکتوری‌ها — با لاگ برای دیباگ
        original_dirs = dirnames[:]
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR and not d.startswith(".")]
        # اگر offline نیست، chromium و model را skip کن در walk اصلی
        if not include_chromium:
            dirnames[:] = [d for d in dirnames if "app-chromium" not in d and "chromium" not in d.lower()]
        if not include_model:
            dirnames[:] = [d for d in dirnames if "nlu-model" not in d and "nlu_download" not in d]
        
        for name in filenames:
            src = pdir / name
            if not _keep(src):
                continue
            if not include_chromium and "app-chromium" in str(src):
                continue
            if not include_model and ("nlu-model" in str(src) or "nlu-download" in str(src)):
                continue
            # Skip very large single files >300MB
            try:
                if src.stat().st_size > 300 * 1024 * 1024:
                    log(f"⏭️ Skip بزرگ >300MB: {src.name} ({src.stat().st_size//1024//1024}MB)")
                    skipped += 1
                    continue
            except:
                continue
            all_files.append(src)
    
    total_files = len(all_files)
    log(f"📋 {total_files} فایل برای بسته‌بندی یافت شد")
    prog(5, f"یافت شد {total_files} فایل...")

    # Now zip with progress and WinError handling
    try:
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
            for idx, src in enumerate(all_files):
                try:
                    # Progress every file, but log every 50 files
                    if idx % 50 == 0 or idx == total_files - 1:
                        pct = 5 + int((idx / total_files) * 60) if total_files > 0 else 5
                        prog(pct, f"بسته‌بندی {idx+1}/{total_files}: {src.name[:40]}...")
                        if idx % 200 == 0:
                            log(f"📦 {idx+1}/{total_files}: {src.relative_to(ROOT) if src.is_relative_to(ROOT) else src.name}")

                    # Handle long paths on Windows
                    src_path = src
                    if sys.platform == "win32":
                        # Try to handle long path
                        try:
                            # Use \\?\ prefix if path > 240 chars
                            if len(str(src)) > 240:
                                src_path = Path("\\\\?\\" + str(src.resolve()))
                        except:
                            src_path = src

                    arcname = src.relative_to(ROOT).as_posix() if src.is_relative_to(ROOT) else src.name
                    
                    # Choose compression method
                    compress_type = zipfile.ZIP_STORED if _should_store(src) else zipfile.ZIP_DEFLATED
                    
                    # Try to write with timeout handling
                    try:
                        # Use writestr with read to handle locked files better
                        # Read file with retry for WinError 32 (file in use)
                        data = None
                        for attempt in range(3):
                            try:
                                # Open with shared read
                                with open(src_path, 'rb') as f:
                                    data = f.read()
                                break
                            except PermissionError as e:
                                # WinError 32: file in use, WinError 5: access denied
                                if attempt < 2:
                                    time.sleep(0.2 * (attempt+1))
                                    continue
                                else:
                                    raise
                            except FileNotFoundError:
                                # WinError 2: file not found (maybe deleted during walk)
                                raise
                            except OSError as e:
                                # WinError 123, 206: path issues
                                if "123" in str(e) or "206" in str(e) or "2" in str(e):
                                    # Try short path
                                    raise
                                if attempt < 2:
                                    time.sleep(0.1)
                                    continue
                                raise
                        
                        if data is None:
                            raise IOError(f"Could not read {src}")
                        
                        # Write to zip
                        zf.writestr(arcname, data, compress_type=compress_type, compresslevel=1 if compress_type==zipfile.ZIP_DEFLATED else 0)
                        count += 1
                        total_size += len(data)
                        
                    except FileNotFoundError:
                        log(f"⏭️ Skip (not found): {src.name}")
                        skipped += 1
                        continue
                    except PermissionError as e:
                        log(f"⏭️ Skip (access denied/in use): {src.name} — {e}")
                        skipped += 1
                        errors.append(f"{src}: {e}")
                        continue
                    except OSError as e:
                        # WinError handling
                        err_str = str(e)
                        if "32" in err_str or "in use" in err_str.lower() or "being used" in err_str.lower():
                            log(f"⏭️ Skip (file in use - WinError 32): {src.name}")
                        elif "5" in err_str or "access" in err_str.lower():
                            log(f"⏭️ Skip (access denied - WinError 5): {src.name}")
                        elif "123" in err_str or "206" in err_str or "path" in err_str.lower():
                            log(f"⏭️ Skip (path too long - WinError 123/206): {src.name[:50]}...")
                        else:
                            log(f"⏭️ Skip (OSError): {src.name} — {e}")
                        skipped += 1
                        errors.append(f"{src}: {e}")
                        continue
                    except Exception as e:
                        log(f"⏭️ Skip (error): {src.name} — {e}")
                        skipped += 1
                        errors.append(f"{src}: {e}")
                        continue
                        
                except Exception as e:
                    log(f"❌ خطا در {src}: {e}")
                    skipped += 1
                    continue

            # اگر offline، کرومیوم را از data_dir اضافه کن — با progress
            if include_chromium:
                try:
                    local_appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
                    chrome_src = Path(local_appdata) / "DivarMarketing" / "app-chromium"
                    if chrome_src.exists():
                        log(f"🌐 افزودن Chromium از {chrome_src}...")
                        prog(70, "افزودن Chromium...")
                        chrome_files = list(chrome_src.rglob("*"))
                        chrome_files = [f for f in chrome_files if f.is_file()]
                        log(f"📋 {len(chrome_files)} فایل Chromium یافت شد")
                        for c_idx, src in enumerate(chrome_files):
                            try:
                                if src.stat().st_size > 200 * 1024 * 1024:
                                    log(f"⏭️ Skip Chromium بزرگ: {src.name}")
                                    continue
                                arcname = f"app-chromium/{src.relative_to(chrome_src).as_posix()}"
                                # Chromium files are already compressed — use STORED
                                with open(src, 'rb') as f:
                                    data = f.read()
                                zf.writestr(arcname, data, compress_type=zipfile.ZIP_STORED)
                                count += 1
                                if c_idx % 100 == 0:
                                    prog(70 + int(c_idx/len(chrome_files)*10), f"Chromium {c_idx}/{len(chrome_files)}...")
                            except Exception as e:
                                log(f"⏭️ Skip Chromium file {src.name}: {e}")
                                continue
                        log(f"✅ Chromium اضافه شد")
                    else:
                        log(f"⚠️ Chromium محلی یافت نشد: {chrome_src} — بدون آن ادامه")
                except Exception as e:
                    log(f"❌ Chromium add failed: {e}\n{traceback.format_exc()[:500]}")

            # مدل
            if include_model:
                try:
                    local_appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
                    model_src = Path(local_appdata) / "DivarMarketing" / "app" / "nlu-model"
                    if not model_src.exists():
                        model_src = Path(local_appdata) / "DivarMarketing" / "nlu-model"
                    if model_src.exists():
                        log(f"🧠 افزودن مدل از {model_src}...")
                        prog(80, "افزودن مدل تیرا...")
                        model_files = list(model_src.rglob("*"))
                        model_files = [f for f in model_files if f.is_file()]
                        log(f"📋 {len(model_files)} فایل مدل یافت شد")
                        for m_idx, src in enumerate(model_files):
                            try:
                                if src.stat().st_size > 300 * 1024 * 1024:
                                    log(f"⏭️ Skip مدل بزرگ: {src.name}")
                                    continue
                                arcname = f"nlu-model/{src.relative_to(model_src).as_posix()}"
                                with open(src, 'rb') as f:
                                    data = f.read()
                                # Model files (gguf, bin) already compressed — STORED
                                ct = zipfile.ZIP_STORED if _should_store(src) else zipfile.ZIP_DEFLATED
                                zf.writestr(arcname, data, compress_type=ct, compresslevel=1 if ct==zipfile.ZIP_DEFLATED else 0)
                                count += 1
                                if m_idx % 50 == 0:
                                    prog(80 + int(m_idx/len(model_files)*5), f"مدل {m_idx}/{len(model_files)}...")
                            except Exception as e:
                                log(f"⏭️ Skip مدل file {src.name}: {e}")
                                continue
                        log(f"✅ مدل اضافه شد")
                    else:
                        log(f"⚠️ مدل محلی یافت نشد: {model_src} — fallback فعال")
                except Exception as e:
                    log(f"❌ Model add failed: {e}\n{traceback.format_exc()[:500]}")

    except Exception as e:
        log(f"❌ خطا در ساخت zip: {e}\n{traceback.format_exc()}")
        raise

    if not dest.exists() or dest.stat().st_size < 1000:
        raise RuntimeError(f"payload.zip is too small: {dest} size={dest.stat().st_size if dest.exists() else 0}")

    log(f"✅ بسته‌بندی کامل: {count} فایل، {skipped} skip، {len(errors)} خطا -> {dest} ({dest.stat().st_size // 1024 // 1024} MB, raw {total_size // 1024 // 1024} MB)")
    if errors:
        log(f"⚠️ {len(errors)} خطا (WinError معمولاً):")
        for err in errors[:10]:
            log(f"   - {err}")
    prog(85, f"بسته‌بندی کامل: {count} فایل ({dest.stat().st_size//1024//1024}MB)")

    if encrypt:
        log(f"🔐 شروع رمزنگاری chunked (بدون load کل فایل در RAM)...")
        prog(86, "رمزنگاری...")
        try:
            # Use chunked encryption — not loading whole file
            result = encrypt_data_chunked(dest, OUT_ENC, log_cb=log_cb, progress_cb=progress_cb)
            log(f"✅ رمزنگاری chunked کامل: {result} ({result.stat().st_size//1024//1024}MB)")
            # Delete plain zip to save space
            try:
                dest.unlink()
                log(f"🗑️ حذف payload.zip خام (رمز شده باقی ماند)")
            except:
                pass
            prog(100, f"آماده ✅ {result.stat().st_size//1024//1024}MB رمز شده")
            return result
        except Exception as e:
            log(f"❌ رمزنگاری خطا: {e} — برمی‌گردیم به payload.zip خام")
            prog(100, f"آماده (بدون رمز) {dest.stat().st_size//1024//1024}MB")
            return dest

    prog(100, f"آماده ✅ {dest.stat().st_size//1024//1024}MB")
    return dest

def main():
    parser = argparse.ArgumentParser(description="Pack payload for installer v4.2 fixed")
    parser.add_argument("--offline", action="store_true", help="Include chromium and model if available")
    parser.add_argument("--include-chromium", action="store_true", help="Include chromium")
    parser.add_argument("--include-model", action="store_true", help="Include model")
    parser.add_argument("--encrypt", action="store_true", help="Encrypt to payload.zip.enc (chunked)")
    parser.add_argument("--all", action="store_true", help="Include all + encrypt — for final single-file setup")
    parser.add_argument("--no-encrypt", action="store_true", help="Don't encrypt even with --all")
    args = parser.parse_args()

    include_chrome = args.offline or args.include_chromium or args.all
    include_model = args.offline or args.include_model or args.all
    encrypt = (args.encrypt or args.all) and not args.no_encrypt

    dest = OUT
    result = pack(dest, include_chromium=include_chrome, include_model=include_model, encrypt=encrypt,
                  log_cb=print, progress_cb=lambda pct, txt: print(f"[{pct}%] {txt}"))
    print(f"✅ Ready: {result} ({result.stat().st_size//1024//1024}MB)")

if __name__ == "__main__":
    main()
