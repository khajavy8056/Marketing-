# -*- coding: utf-8 -*-
"""Chromium اختصاصی برنامه — جدا از مرورگر و پروفایل کاربر.

Playwright در exe یک‌فایلی (PyInstaller) مرورگر را داخل Temp\\_MEI... می‌جوید
و آن پوشه با بستن برنامه پاک می‌شود. اینجا Chromium همیشه در پوشهٔ پایدار
برنامه نصب می‌شود:

  %LOCALAPPDATA%\\DivarMarketing\\app-chromium\\chromium-<rev>\\chrome-win\\chrome.exe

پروفایل لاگین هر اکانت جداست: accounts/<name>/chromium/
"""

from __future__ import annotations

import os
import ssl
import sys
import zipfile
from pathlib import Path
from typing import Callable, List, Optional
from urllib.request import Request, urlopen

from .paths import user_data_dir

APP_BROWSER_DIRNAME = "app-chromium"

# میزبان‌هایی که معمولاً از ایران بهتر جواب می‌دهند، بعد CDN رسمی Playwright
DOWNLOAD_HOSTS = (
    "https://cdn.npmmirror.com/binaries/playwright",
    "https://npmmirror.com/mirrors/playwright",
    "https://registry.npmmirror.com/-/binary/playwright",
    "https://cdn.playwright.dev",
    "https://playwright.azureedge.net",
)

LogFn = Callable[[str], None]


def browsers_dir() -> Path:
    override = os.environ.get("DIVAR_CHROMIUM_DIR")
    if override:
        return Path(override)
    return user_data_dir() / APP_BROWSER_DIRNAME


def apply_browser_env() -> Path:
    """قبل از import/start شدن Playwright صدا زده شود تا مسیر _MEI استفاده نشود."""
    dest = browsers_dir()
    dest.mkdir(parents=True, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(dest)
    # هرگز از مرورگر سیستم (channel=chrome/msedge) استفاده نکن
    os.environ.pop("PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD", None)
    return dest


def _is_bad_install_path(p: Path) -> bool:
    s = str(p).replace("\\", "/").lower()
    if "/_mei" in s or s.startswith("_mei"):
        return True
    # پوشهٔ استخراج موقت PyInstaller
    if "/temp/" in s and "_mei" in s:
        return True
    return False


def find_chrome(root: Optional[Path] = None) -> Optional[Path]:
    """chrome.exe فقط از پوشهٔ اختصاصی برنامه — نه Chrome/Edge کاربر."""
    root = Path(root) if root else browsers_dir()
    if not root.exists() or _is_bad_install_path(root):
        return None
    names = ("chrome.exe", "chrome", "chromium", "Chromium")
    for folder in sorted(root.glob("chromium-*"), reverse=True):
        if not folder.is_dir():
            continue
        for rel in (
            Path("chrome-win") / "chrome.exe",
            Path("chrome-win64") / "chrome.exe",
            Path("chrome-linux") / "chrome",
            Path("chrome-linux64") / "chrome",
            Path("chrome-mac") / "Chromium.app" / "Contents" / "MacOS" / "Chromium",
            Path("chrome-mac-arm64") / "Chromium.app" / "Contents" / "MacOS" / "Chromium",
        ):
            cand = folder / rel
            if cand.is_file() and not _is_bad_install_path(cand):
                return cand
        for name in names:
            for cand in folder.rglob(name):
                if cand.is_file() and cand.name.lower() in (
                    "chrome.exe", "chrome", "chromium",
                ) and "headless" not in str(cand).lower():
                    if not _is_bad_install_path(cand):
                        return cand
    return None


def executable_path() -> str:
    apply_browser_env()
    found = find_chrome()
    if not found:
        raise RuntimeError(
            "Chromium اختصاصی برنامه نصب نیست. نصب‌کننده باید آن را در "
            "پوشهٔ DivarMarketing\\app-chromium بگذارد — از Chrome/Edge سیستم استفاده نمی‌شود."
        )
    return str(found)


def _chromium_meta() -> dict:
    """revision و نام zip مطابق همان نسخهٔ Playwright بسته‌شده."""
    cands: List[Path] = []
    try:
        import playwright
        base = Path(playwright.__file__).resolve().parent
        cands.append(base / "driver" / "package" / "browsers.json")
    except Exception:
        pass
    if getattr(sys, "frozen", False):
        mei = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        cands.insert(0, mei / "playwright" / "driver" / "package" / "browsers.json")
    import json
    for p in cands:
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for b in data.get("browsers") or []:
            if b.get("name") == "chromium" and b.get("revision"):
                return {"revision": str(b["revision"]), "name": "chromium"}
    return {"revision": "1155", "name": "chromium"}


def _zip_name() -> str:
    if sys.platform == "win32":
        return "chromium-win64.zip"
    if sys.platform == "darwin":
        import platform
        return "chromium-mac-arm64.zip" if platform.machine() == "arm64" else "chromium-mac.zip"
    return "chromium-linux.zip"


def _ssl_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _download(url: str, dest: Path, log: LogFn) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = Request(url, headers={"User-Agent": "DivarMarketing/2.1.14"})
    log(f"Downloading {url}")
    with urlopen(req, context=_ssl_ctx(), timeout=90) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        n = 0
        last_pct = -1
        while True:
            chunk = r.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)
            n += len(chunk)
            if total:
                pct = int(n * 100 / total)
                if pct >= last_pct + 10:
                    log(f"  {pct}% ({n // (1024 * 1024)} MB)")
                    last_pct = pct
    if tmp.stat().st_size < 1_000_000:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"download too small: {url}")
    tmp.replace(dest)


def _extract_zip(zpath: Path, dest_folder: Path, log: LogFn) -> Path:
    if dest_folder.exists():
        import shutil
        shutil.rmtree(dest_folder, ignore_errors=True)
    dest_folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath, "r") as zf:
        zf.extractall(dest_folder)
    marker = dest_folder / "INSTALLATION_COMPLETE"
    marker.write_text("ok", encoding="utf-8")
    log(f"Extracted Chromium -> {dest_folder}")
    found = find_chrome(dest_folder.parent)
    if not found:
        raise RuntimeError("zip extracted but chrome.exe was not inside it")
    return found


def _install_via_driver(dest: Path, log: LogFn) -> Optional[Path]:
    apply_browser_env()
    try:
        from playwright._impl._driver import compute_driver_executable
    except Exception:
        return None
    try:
        driver = compute_driver_executable()
    except Exception:
        return None
    if isinstance(driver, (list, tuple)):
        cmd = [str(x) for x in driver]
    else:
        cmd = [str(driver)]
    if not cmd or not Path(cmd[0]).exists():
        return None
    import subprocess
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(dest)
    env["PYTHONUTF8"] = "1"
    for host in DOWNLOAD_HOSTS:
        env["PLAYWRIGHT_DOWNLOAD_HOST"] = host
        log(f"playwright driver install chromium (host={host})")
        try:
            r = subprocess.run(
                cmd + ["install", "chromium"],
                env=env, capture_output=True, text=True, timeout=900,
            )
        except Exception as e:
            log(f"  driver failed: {e}")
            continue
        if r.stdout:
            for line in r.stdout.splitlines()[-8:]:
                if line.strip():
                    log("  " + line.strip())
        if r.returncode == 0:
            found = find_chrome(dest)
            if found:
                return found
        log(f"  exit {r.returncode}")
    return None


def _install_via_zip(dest: Path, log: LogFn) -> Path:
    meta = _chromium_meta()
    rev = meta["revision"]
    zname = _zip_name()
    folder = dest / f"chromium-{rev}"
    zpath = dest / zname
    last_err = "no host"
    for host in DOWNLOAD_HOSTS:
        url = f"{host.rstrip('/')}/builds/chromium/{rev}/{zname}"
        try:
            _download(url, zpath, log)
            found = _extract_zip(zpath, folder, log)
            try:
                zpath.unlink()
            except Exception:
                pass
            return found
        except Exception as e:
            last_err = f"{url}: {e}"
            log(f"  failed: {e}")
            try:
                zpath.unlink(missing_ok=True)
            except Exception:
                pass
    raise RuntimeError(
        "نتوانست Chromium اختصاصی را دانلود کند (فیلتر/شبکه). "
        "نصب‌کننده را با اینترنت بدون فیلتر دوباره بزنید. " + last_err
    )


def ensure_installed(log: Optional[LogFn] = None, force: bool = False) -> Path:
    """اگر chrome.exe اختصاصی نباشد، از چند آینه دانلود و نصب می‌کند."""
    log = log or (lambda m: print(m, flush=True))
    dest = apply_browser_env()
    if not force:
        found = find_chrome(dest)
        if found:
            log(f"App Chromium ready: {found}")
            return found
    log(f"Installing app-only Chromium into {dest}")
    found = _install_via_driver(dest, log)
    if found:
        log(f"App Chromium ready: {found}")
        return found
    found = _install_via_zip(dest, log)
    log(f"App Chromium ready: {found}")
    return found
