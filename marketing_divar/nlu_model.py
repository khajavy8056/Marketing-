# -*- coding: utf-8 -*-
"""دانلود و اجرای مدل محلی درک متن (Qwen 1.5B GGUF + llama.cpp).

فایل داخل گیت نیست. یک‌بار مثل Chromium به پوشهٔ پایدار کاربر می‌رود:
  Windows: %LOCALAPPDATA%\\DivarMarketing\\nlu-model\\
اگر نباشد برنامه کار می‌کند؛ فقط جواب مبهم «نیاز به خواندن» می‌شود.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .paths import user_data_dir

LogFn = Callable[[str], None]

MODEL_NAME = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
MARKER = "INSTALLED.json"

# آینه‌های HuggingFace — اگر یکی قطع شد بعدی
GGUF_URLS = (
    "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"
    "qwen2.5-1.5b-instruct-q4_k_m.gguf",
    "https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"
    "Qwen2.5-1.5B-Instruct-Q4_K_M.gguf",
)

# باینری پیش‌ساخته llama.cpp ویندوز (cpu)
LLAMA_ZIP_URLS = (
    "https://github.com/ggerganov/llama.cpp/releases/download/b4381/"
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
    override = os.environ.get("DIVAR_NLU_DIR")
    if override:
        return Path(override)
    return user_data_dir() / "nlu-model"


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


def is_ready() -> bool:
    g = gguf_path()
    if not g.is_file() or g.stat().st_size < 50_000_000:
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
    out["model"] = MODEL_NAME
    if ready:
        out["path"] = str(gguf_path())
        out["percent"] = out.get("percent") or 100
        out["note"] = out.get("note") or "آماده"
    elif not out.get("note"):
        out["note"] = "مدل محلی نیست — یک‌بار دانلود می‌شود و در پوشه پایدار می‌ماند"
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


def ensure_installed(log: Optional[LogFn] = None,
                     progress: Optional[Callable[[int], None]] = None,
                     force: bool = False) -> Path:
    d = model_dir()
    d.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        _STATUS["running"] = True
        _STATUS["error"] = ""
        _STATUS["note"] = "شروع دانلود مدل"
        _STATUS["percent"] = 0
    try:
        g = gguf_path()
        if force or not g.is_file() or g.stat().st_size < 50_000_000:
            last = None
            for url in GGUF_URLS:
                try:
                    if log:
                        log("NLU model " + url)
                    _download(url, g, log, progress)
                    last = None
                    break
                except Exception as e:
                    last = e
                    if log:
                        log("NLU model fail: %s" % e)
            if last:
                raise last
        if sys.platform == "win32" and llama_exe() is None:
            zpath = d / "llama.zip"
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


def start_install_async() -> Dict[str, Any]:
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


def infer_json(prompt: str, timeout: int = 45) -> str:
    """یک استنتاج کوتاه. اگر موتور نباشد رشته خالی."""
    if not is_ready():
        return ""
    exe = llama_exe()
    g = gguf_path()
    if not exe or not g.is_file():
        return ""
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
