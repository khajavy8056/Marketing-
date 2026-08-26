# -*- coding: utf-8 -*-
"""Chromium اختصاصی برنامه — نه Chrome گوگل، نه Edge سیستم.

دانلود فقط باینری Chromium (snapshot / Playwright Chromium / ungoogled).
Chrome for Testing رد می‌شود. Installed فقط بعد از extract + ثبت INSTALLED.json.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Dict, Optional

from .paths import user_data_dir

LogFn = Callable[[str], None]
ProgressFn = Callable[[int], None]

_STATUS: Dict[str, object] = {
    "installed": False,
    "path": "",
    "running": False,
    "percent": 0,
    "bytes": 0,
    "total": 0,
    "speed": "",
    "source": "",
    "error": "",
    "note": "",
    "product": "",
}
_LOCK = threading.Lock()


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
    override = os.environ.get("DIVAR_CHROMIUM_DIR")
    if override:
        return Path(override)
    return user_data_dir() / "app-chromium"


def apply_browser_env() -> Path:
    dest = browsers_dir()
    dest.mkdir(parents=True, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(dest)
    os.environ["DIVAR_CHROMIUM_DIR"] = str(dest)
    os.environ.pop("PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD", None)
    return dest


def find_chrome(root: Optional[Path] = None):
    return _fc.find_chrome(root or browsers_dir())


def is_ready(root: Optional[Path] = None) -> bool:
    return bool(_fc.is_ready(root or browsers_dir()))


def executable_path() -> str:
    apply_browser_env()
    if not is_ready():
        raise RuntimeError(
            "Chromium اختصاصی نصب/ثبت نشده. Chrome گوگل و Edge سیستم استفاده نمی‌شوند. "
            "از پنل «شروع دانلود Chromium» را بزنید."
        )
    found = find_chrome()
    if not found:
        raise RuntimeError("فایل Chromium بعد از ثبت پیدا نشد")
    return str(found)


def _extract_zip(zpath, dest_folder, log):
    return _fc._extract_zip(zpath, dest_folder, log)


def github_zip_urls():
    return _fc.github_zip_urls()


def _parse_log(msg: str) -> None:
    line = str(msg or "").strip()
    with _LOCK:
        if line.startswith("PROGRESS "):
            try:
                _STATUS["percent"] = max(0, min(100, int(line.split()[1])))
            except Exception:
                pass
        elif line.startswith("BYTES "):
            try:
                part = line.split()[1]
                a, b = part.split("/", 1)
                _STATUS["bytes"] = int(a)
                _STATUS["total"] = int(b)
            except Exception:
                pass
        elif line.startswith("SPEED "):
            _STATUS["speed"] = line[6:].strip()
        elif line.startswith("SOURCE ") and not line.startswith("SOURCE_"):
            _STATUS["source"] = line[7:].strip()
            _STATUS["note"] = "source " + str(_STATUS["source"])
        elif line.startswith("SOURCE_FAIL "):
            _STATUS["note"] = line
        elif line.startswith("VALIDATED "):
            _STATUS["note"] = line
        elif line.startswith("REGISTERED "):
            _STATUS["note"] = line
        elif line.startswith("DOWNLOAD_COMPLETED"):
            _STATUS["percent"] = 100
            _STATUS["note"] = "Completed"
        elif line.startswith("CHROMIUM_OK "):
            _STATUS["path"] = line[12:].strip()
            _STATUS["installed"] = True
            _STATUS["percent"] = 100
            _STATUS["note"] = "Completed"
            _STATUS["error"] = ""


def status() -> Dict[str, object]:
    apply_browser_env()
    ready = is_ready()
    found = find_chrome() if ready else None
    rec = {}
    try:
        rec = _fc.read_marker(browsers_dir())
    except Exception:
        rec = {}
    with _LOCK:
        out = dict(_STATUS)
    out["installed"] = bool(ready)
    out["product"] = rec.get("product") or ""
    if found:
        out["path"] = str(found)
        if not out.get("percent"):
            out["percent"] = 100
            out["note"] = out.get("note") or "Completed"
    elif out.get("note") in ("Completed",) and not ready:
        out["note"] = "downloaded but not registered Chromium"
    return out


def ensure_installed(log: Optional[LogFn] = None,
                     progress: Optional[ProgressFn] = None,
                     force: bool = False) -> Path:
    apply_browser_env()

    def wrapped(msg: str) -> None:
        _parse_log(msg)
        if log:
            log(msg)
        else:
            print(msg, flush=True)

    def on_pct(p: int) -> None:
        with _LOCK:
            _STATUS["percent"] = int(p)
        if progress:
            progress(p)

    with _LOCK:
        _STATUS["running"] = True
        _STATUS["error"] = ""
        _STATUS["note"] = "started"
    try:
        found = _fc.ensure_installed(log=wrapped, progress=on_pct, force=force)
        with _LOCK:
            _STATUS["installed"] = True
            _STATUS["path"] = str(found)
            _STATUS["percent"] = 100
            _STATUS["note"] = "Completed"
        return found
    except Exception as e:
        with _LOCK:
            _STATUS["error"] = str(e)
            _STATUS["note"] = "failed"
        raise
    finally:
        with _LOCK:
            _STATUS["running"] = False


def start_install_async() -> Dict[str, object]:
    with _LOCK:
        if _STATUS.get("running"):
            return status()
        _STATUS["running"] = True
        _STATUS["error"] = ""
        _STATUS["note"] = "started"
        _STATUS["percent"] = 0

    def work() -> None:
        try:
            ensure_installed()
        except Exception:
            pass

    threading.Thread(target=work, daemon=True).start()
    return status()


def open_in_app_chromium(url: str, profile_dir: Optional[Path] = None,
                         extra_args: Optional[list] = None) -> Dict[str, object]:
    """Open a URL in the app Chromium only. Never Edge/Chrome/default browser."""
    apply_browser_env()
    if not is_ready():
        return {"ok": False, "stage": "executable",
                "message": "Chromium اختصاصی نصب نیست — Edge/Chrome سیستم باز نمی‌شود."}
    exe = executable_path()
    prof = Path(profile_dir) if profile_dir else (browsers_dir() / "panel-ui")
    prof.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(exe),
        "--user-data-dir=" + str(prof),
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
    ]
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(str(url))
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        return {"ok": False, "stage": "launch", "message": str(e), "exe": exe}
    return {"ok": True, "exe": exe, "profile": str(prof), "url": url}
