# -*- coding: utf-8 -*-
"""دانلود و اجرای مدل محلی درک متن (Qwen 1.5B GGUF + llama.cpp).

فایل داخل گیت نیست. هنگام نصب کنار فایل نصبی دانلود می‌شود (nlu-download)
و کنار برنامه نصب می‌شود (nlu-model). اگر نباشد برنامه کار می‌کند؛
فقط جواب مبهم «نیاز به خواندن» می‌شود.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .paths import user_data_dir


def program_dir() -> Path:
    """پوشه نصب برنامه (کنار main.py یا exe)."""
    override = os.environ.get("DIVAR_APP_DIR")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[1]


def download_cache_dir() -> Path:
    """محل موقت دانلود — کنار فایل نصبی / Setup."""
    override = os.environ.get("DIVAR_NLU_DOWNLOAD")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "nlu-download"
    return program_dir() / "nlu-download"

LogFn = Callable[[str], None]

MODEL_NAME = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
MARKER = "INSTALLED.json"

# آینه‌های HuggingFace — اگر یکی قطع شد بعدی (ایران: hf-mirror)
GGUF_URLS = (
    "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"
    "qwen2.5-1.5b-instruct-q4_k_m.gguf",
    "https://hf-mirror.com/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"
    "qwen2.5-1.5b-instruct-q4_k_m.gguf",
    "https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"
    "Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
    "https://hf-mirror.com/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"
    "Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
    "https://huggingface.co/QuantFactory/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"
    "Qwen2.5-1.5B-Instruct.Q4_K_M.gguf",
    "https://hf-mirror.com/QuantFactory/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"
    "Qwen2.5-1.5B-Instruct.Q4_K_M.gguf",
)

# باینری پیش‌ساخته llama.cpp ویندوز (cpu)
# b4179 آخرین ساخت پایدار Win10 21H2 (issue #11479)؛ بعد ggml-org / ggerganov
LLAMA_ZIP_URLS = (
    "https://github.com/ggerganov/llama.cpp/releases/download/b4179/"
    "llama-b4179-bin-win-avx2-x64.zip",
    "https://github.com/ggml-org/llama.cpp/releases/download/b4179/"
    "llama-b4179-bin-win-avx2-x64.zip",
    "https://github.com/ggerganov/llama.cpp/releases/download/b4381/"
    "llama-b4381-bin-win-avx2-x64.zip",
    "https://github.com/ggml-org/llama.cpp/releases/download/b4381/"
    "llama-b4381-bin-win-avx2-x64.zip",
    "https://github.com/ggerganov/llama.cpp/releases/download/b3600/"
    "llama-b3600-bin-win-avx2-x64.zip",
)

_STATUS: Dict[str, Any] = {
    "installed": False, "running": False, "percent": 0,
    "error": "", "note": "", "path": "", "ready": False,
}
_LOCK = threading.Lock()


def model_dir() -> Path:
    """محل نصب مدل = محل نصب برنامه (nlu-model کنار فایل‌های برنامه)."""
    override = os.environ.get("DIVAR_NLU_DIR")
    if override:
        return Path(override)
    return program_dir() / "nlu-model"


def gguf_path() -> Path:
    return model_dir() / MODEL_NAME


def llama_exe() -> Optional[Path]:
    root = model_dir()
    names = ("llama-cli.exe", "llama-cli", "main.exe", "llama.exe")
    for n in names:
        p = root / n
        if p.is_file():
            return p
    try:
        for p in root.rglob("llama-cli.exe"):
            return p
        for p in root.rglob("llama-cli"):
            return p
        for p in root.rglob("main.exe"):
            return p
    except Exception:
        pass
    return None


def backend_name() -> str:
    """نام موتور فعال: llama.cpp-binary | llama-cpp-python | fallback-smart."""
    try:
        if (model_dir() / "DUMMY").is_file():
            return "fallback-smart"
    except Exception:
        pass
    if llama_exe() is not None:
        return "llama.cpp-binary"
    try:
        import llama_cpp  # noqa: F401
        return "llama-cpp-python"
    except Exception:
        pass
    return "fallback-smart"


def ensure_dummy_model_for_test(size: int = 10 * 1024 * 1024) -> Path:
    """مدل تستی ~10MB + نشانگر DUMMY تا is_ready بدون llama.cpp True شود."""
    d = model_dir()
    d.mkdir(parents=True, exist_ok=True)
    g = gguf_path()
    if (not g.is_file()) or g.stat().st_size < 1000:
        blob = b"GGUF" + (b"\0" * max(0, int(size) - 4))
        g.write_bytes(blob)
    (d / "DUMMY").write_text("dummy-fallback-smart\n", encoding="utf-8")
    marker = {
        "product": "dummy-fallback-smart",
        "gguf": str(g),
        "ready": True,
        "backend": "fallback-smart",
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        (d / MARKER).write_text(json.dumps(marker, ensure_ascii=False, indent=2),
                                encoding="utf-8")
    except Exception:
        pass
    return g


def is_ready() -> bool:
    g = gguf_path()
    if not g.is_file():
        return False
    try:
        if (model_dir() / "DUMMY").is_file():
            return True
    except Exception:
        pass
    if g.stat().st_size < 50_000_000:
        return False
    if sys.platform == "win32":
        return llama_exe() is not None
    # لینوکس: اگر باینری نبود فقط قاعده؛ تمرکز محصول ویندوز است
    return llama_exe() is not None


def status() -> Dict[str, Any]:
    with _LOCK:
        out = dict(_STATUS)
    ready = is_ready()
    out["installed"] = ready
    out["ready"] = ready
    out["backend"] = backend_name()
    out["model"] = MODEL_NAME
    out["install_dir"] = str(model_dir())
    out["download_dir"] = str(download_cache_dir())
    out["role"] = "analyze_replies_listings_vehicles_images"
    if ready:
        out["path"] = str(gguf_path())
        out["percent"] = out.get("percent") or 100
        out["note"] = out.get("note") or "آماده"
    elif not out.get("note"):
        out["note"] = ("مدل محلی نیست — هنگام نصب کنار فایل نصبی دانلود و "
                       "کنار برنامه نصب می‌شود")
    return out


def _download(url: str, dest: Path, log: Optional[LogFn],
              progress: Optional[Callable[[int], None]]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    already = part.stat().st_size if part.exists() else 0
    headers = {}
    if already:
        headers["Range"] = "bytes=%d-" % already
    try:
        import urllib.request
        req = urllib.request.Request(url, headers=headers)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=40) as resp:
            total = already + int(resp.headers.get("Content-Length") or 0)
            mode = "ab" if already else "wb"
            written = already
            t0 = time.time()
            with open(part, mode) as f:
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    written += len(chunk)
                    if total:
                        pct = int(written * 100 / total)
                        if progress:
                            progress(min(99, pct))
                        with _LOCK:
                            _STATUS["percent"] = min(99, pct)
                            _STATUS["note"] = "دانلود %s%%" % pct
                    if log and time.time() - t0 > 2:
                        log("NLU %d / %d" % (written, total or 0))
                        t0 = time.time()
        part.replace(dest)
    except Exception:
        raise


def _extract_zip(zpath: Path, dest: Path, log: Optional[LogFn]) -> None:
    import zipfile
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath, "r") as z:
        z.extractall(dest)
    if log:
        log("NLU unzip ok")


def _file_ok(p: Path, min_size: int = 50_000_000) -> bool:
    try:
        return p.is_file() and p.stat().st_size >= min_size
    except OSError:
        return False


def _copy_if_needed(src: Path, dest: Path, log: Optional[LogFn] = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() == dest.resolve():
        return
    shutil.copy2(src, dest)
    if log:
        log("NLU copied cache -> " + str(dest))


def ensure_installed(log: Optional[LogFn] = None,
                     progress: Optional[Callable[[int], None]] = None,
                     force: bool = False) -> Path:
    d = model_dir()
    d.mkdir(parents=True, exist_ok=True)
    cache = download_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        _STATUS["running"] = True
        _STATUS["error"] = ""
        _STATUS["note"] = "شروع دانلود مدل"
        _STATUS["percent"] = 0
    if log:
        log("NLU_START")
    try:
        g = gguf_path()
        cached = cache / MODEL_NAME
        if force or not _file_ok(g):
            if not force and _file_ok(cached):
                if log:
                    log("NLU using cached model " + str(cached))
                _copy_if_needed(cached, g, log)
            else:
                last = None
                for url in GGUF_URLS:
                    try:
                        if log:
                            log("NLU model " + url)
                        _download(url, cached, log, progress)
                        last = None
                        break
                    except Exception as e:
                        last = e
                        if log:
                            log("NLU model fail: %s" % e)
                if last and not _file_ok(cached):
                    raise last
                if _file_ok(cached):
                    _copy_if_needed(cached, g, log)
        if sys.platform == "win32" and llama_exe() is None:
            zpath = cache / "llama.zip"
            last = None
            for url in LLAMA_ZIP_URLS:
                try:
                    if log:
                        log("NLU llama.cpp " + url)
                    _download(url, zpath, log, progress)
                    _extract_zip(zpath, d, log)
                    last = None
                    break
                except Exception as e:
                    last = e
            if last and llama_exe() is None:
                if log:
                    log("NLU llama.cpp optional fail: %s" % last)
        marker = {
            "product": "qwen2.5-1.5b-instruct-q4_k_m",
            "gguf": str(g),
            "ready": is_ready(),
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        (d / MARKER).write_text(json.dumps(marker, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        with _LOCK:
            _STATUS["installed"] = is_ready()
            _STATUS["ready"] = is_ready()
            _STATUS["percent"] = 100
            _STATUS["path"] = str(g)
            _STATUS["note"] = "آماده" if is_ready() else "مدل هست؛ موتور llama پیدا نشد"
        return g
    except Exception as e:
        with _LOCK:
            _STATUS["error"] = str(e)
            _STATUS["note"] = "ناموفق"
        raise
    finally:
        with _LOCK:
            _STATUS["running"] = False


def start_install_async(small: bool = False) -> Dict[str, Any]:
    if small:
        try:
            ensure_dummy_model_for_test()
        except Exception:
            pass
        return status()
    with _LOCK:
        if _STATUS.get("running"):
            return status()
        _STATUS["running"] = True

    def work() -> None:
        try:
            ensure_installed()
        except Exception:
            pass

    threading.Thread(target=work, daemon=True).start()
    return status()


def _fallback_smart_json(prompt: str) -> str:
    """طبقه‌بند قاعده‌ای وقتی مدل واقعی نیست (DUMMY / بدون llama)."""
    p = prompt or ""
    intent = "unclear"
    conf = 0.55
    summary = "تحلیل fallback هوشمند"
    if any(w in p for w in ("فروخته", "فروختم", "رفته", "موجود نیست", "تمام شد")):
        intent, conf, summary = "gone", 0.9, "آگهی دیگر موجود نیست"
    elif any(w in p for w in ("بیعانه", "کارت به کارت", "شبا")):
        intent, conf, summary = "scam_deposit", 0.9, "درخواست بیعانه"
    elif any(w in p for w in ("معیوب", "شکسته", "تعمیر")):
        intent, conf, summary = "defect_admit", 0.85, "کالا معیوب/تعمیری"
    elif any(w in p for w in ("میلیون", "تومان", "قیمت")):
        intent, conf, summary = "price_quote", 0.8, "قیمت اعلام شد"
    elif "سلام" in p and len(p) < 80:
        intent, conf, summary = "greeting", 0.7, "سلام"
    return json.dumps({
        "intent": intent, "confidence": conf, "price_toman": None,
        "condition": "unknown", "wants_deposit": intent == "scam_deposit",
        "summary_fa": summary,
    }, ensure_ascii=False)


def infer_json(prompt: str, timeout: int = 45) -> str:
    """یک استنتاج کوتاه. اگر موتور نباشد fallback-smart."""
    dummy = False
    try:
        dummy = (model_dir() / "DUMMY").is_file()
    except Exception:
        dummy = False
    if dummy or not is_ready():
        return _fallback_smart_json(prompt)
    exe = llama_exe()
    g = gguf_path()
    if not exe or not g.is_file():
        return _fallback_smart_json(prompt)
    cmd = [
        str(exe), "-m", str(g),
        "-n", "180", "-c", "512",
        "--temp", "0.1", "-p", prompt,
        "-no-cnv",
    ]
    try:
        r = subprocess.run(
            cmd, capture_output=True, timeout=timeout,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if sys.platform == "win32" else 0)
        out = (r.stdout or b"").decode("utf-8", errors="replace")
        err = (r.stderr or b"").decode("utf-8", errors="replace")
        return (out or err)[-4000:]
    except Exception:
        return ""


def vision_exe() -> Optional[Path]:
    root = model_dir()
    names = ("llama-mtmd.exe", "llama-llava.exe", "llava-cli.exe")
    for n in names:
        p = root / n
        if p.is_file():
            return p
    try:
        for n in names:
            for p in root.rglob(n):
                return p
    except Exception:
        pass
    return None


def infer_vision(prompt: str, image_path: str, timeout: int = 60) -> str:
    """اگر باینری بینایی محلی باشد تصویر را می‌خواند؛ وگرنه خالی."""
    exe = vision_exe()
    g = gguf_path()
    img = Path(image_path)
    if not exe or not g.is_file() or not img.is_file():
        return ""
    mmproj = None
    try:
        for p in model_dir().rglob("*mmproj*"):
            mmproj = p
            break
    except Exception:
        mmproj = None
    cmd = [str(exe), "-m", str(g), "--image", str(img),
           "-n", "120", "-p", prompt, "-no-cnv"]
    if mmproj:
        cmd.extend(["--mmproj", str(mmproj)])
    try:
        r = subprocess.run(
            cmd, capture_output=True, timeout=timeout,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if sys.platform == "win32" else 0)
        out = (r.stdout or b"").decode("utf-8", errors="replace")
        return (out or "")[-4000:]
    except Exception:
        return ""
