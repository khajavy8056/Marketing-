# -*- coding: utf-8 -*-
"""Download portable Chromium into the app folder (not the user's browser).

Open-source builds (ungoogled-chromium) from GitHub, with mirrors.
Never uses Playwright CDN (that hangs/fails in filtered networks).
Prints PROGRESS <0-100> so the installer bar can move.
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import time
import zipfile
from pathlib import Path
from typing import Callable, List, Optional
from urllib.request import Request, urlopen

APP_ID = "DivarMarketing"
APP_BROWSER_DIRNAME = "app-chromium"

# Pinned GitHub zip (Windows x64 portable). Latest is resolved via API first.
PINNED_GITHUB_ZIP = (
    "https://github.com/ungoogled-software/ungoogled-chromium-windows/"
    "releases/download/137.0.7151.68-1.1/"
    "ungoogled-chromium_137.0.7151.68-1.1_windows_x64.zip"
)
GITHUB_API = (
    "https://api.github.com/repos/ungoogled-software/"
    "ungoogled-chromium-windows/releases/latest"
)
CFT_MIRROR = (
    "https://cdn.npmmirror.com/binaries/chrome-for-testing/"
    "131.0.6778.204/win64/chrome-win64.zip"
)

LogFn = Callable[[str], None]
ProgressFn = Callable[[int], None]


def browsers_dir() -> Path:
    override = os.environ.get("DIVAR_CHROMIUM_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(
            Path.home() / "AppData" / "Local")
        return Path(base) / APP_ID / APP_BROWSER_DIRNAME
    xdg = os.environ.get("XDG_DATA_HOME")
    root = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return root / "divar-marketing" / APP_BROWSER_DIRNAME


def apply_browser_env() -> Path:
    dest = browsers_dir()
    dest.mkdir(parents=True, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(dest)
    os.environ["DIVAR_CHROMIUM_DIR"] = str(dest)
    os.environ.pop("PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD", None)
    return dest


def _is_bad_install_path(p: Path) -> bool:
    s = str(p).replace("\\", "/").lower()
    return "/_mei" in s or s.startswith("_mei")


def find_chrome(root: Optional[Path] = None) -> Optional[Path]:
    root = Path(root) if root else browsers_dir()
    if not root.exists() or _is_bad_install_path(root):
        return None
    rels = (
        Path("chrome-win") / "chrome.exe",
        Path("chrome-win64") / "chrome.exe",
        Path("Chrome-bin") / "chrome.exe",
        Path("chrome.exe"),
        Path("chrome-linux") / "chrome",
        Path("chrome-linux64") / "chrome",
    )
    folders = [root] + sorted(
        [p for p in root.iterdir() if p.is_dir()], reverse=True)
    for folder in folders:
        for rel in rels:
            cand = folder / rel
            if cand.is_file() and not _is_bad_install_path(cand):
                if "headless" in str(cand).lower():
                    continue
                return cand
        direct = folder / "chrome.exe"
        if direct.is_file() and not _is_bad_install_path(direct):
            return direct
    for cand in root.rglob("chrome.exe"):
        if cand.is_file() and "headless" not in str(cand).lower():
            if not _is_bad_install_path(cand):
                return cand
    for cand in root.rglob("chrome"):
        if cand.is_file() and "headless" not in str(cand).lower():
            if not _is_bad_install_path(cand):
                return cand
    return None


def executable_path() -> str:
    apply_browser_env()
    found = find_chrome()
    if not found:
        raise RuntimeError(
            "App Chromium is not installed. Run the installer again "
            "(it downloads ungoogled-chromium into DivarMarketing\\app-chromium)."
        )
    return str(found)


def _ssl_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _get(url: str, timeout: float = 20):
    req = Request(url, headers={
        "User-Agent": "DivarMarketing/2.1.15",
        "Accept": "*/*",
    })
    return urlopen(req, context=_ssl_ctx(), timeout=timeout)


def _mirror(url: str) -> List[str]:
    out = [url]
    if "github.com" in url or "githubusercontent.com" in url:
        out += [
            "https://ghproxy.net/" + url,
            "https://ghfast.top/" + url,
            "https://mirror.ghproxy.com/" + url,
        ]
    return out


def github_zip_urls() -> List[str]:
    urls: List[str] = []
    try:
        with _get(GITHUB_API, timeout=12) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
        for asset in data.get("assets") or []:
            name = str(asset.get("name") or "").lower()
            href = asset.get("browser_download_url") or ""
            if href and name.endswith(".zip") and "windows" in name and (
                    "x64" in name or "win64" in name):
                urls.append(str(href))
                break
    except Exception:
        pass
    if PINNED_GITHUB_ZIP not in urls:
        urls.append(PINNED_GITHUB_ZIP)
    expanded: List[str] = []
    for u in urls:
        for m in _mirror(u):
            if m not in expanded:
                expanded.append(m)
    if CFT_MIRROR not in expanded:
        expanded.append(CFT_MIRROR)
    return expanded


def _download(url: str, dest: Path, log: LogFn, progress: Optional[ProgressFn]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    log("Downloading " + url)
    t0 = time.time()
    last_byte = time.time()
    n = 0
    last_pct = -1
    with _get(url, timeout=25) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        while True:
            if time.time() - last_byte > 25:
                raise TimeoutError("download stalled (no data for 25s)")
            if time.time() - t0 > 480:
                raise TimeoutError("download exceeded 8 minutes")
            try:
                chunk = r.read(256 * 1024)
            except Exception as e:
                raise TimeoutError(str(e)) from e
            if not chunk:
                break
            f.write(chunk)
            n += len(chunk)
            last_byte = time.time()
            pct = int(n * 100 / total) if total else min(99, n // (2 * 1024 * 1024))
            if pct >= last_pct + 1:
                last_pct = pct
                log("PROGRESS %d" % pct)
                log("  Chromium %d%% (%d MB)" % (pct, n // (1024 * 1024)))
                if progress:
                    progress(min(100, pct))
    size = tmp.stat().st_size if tmp.exists() else 0
    if size < 8_000_000:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("download too small (%d bytes): %s" % (size, url))
    tmp.replace(dest)
    log("PROGRESS 100")
    if progress:
        progress(100)


def _extract_zip(zpath: Path, dest_folder: Path, log: LogFn) -> Path:
    if dest_folder.exists():
        import shutil
        shutil.rmtree(dest_folder, ignore_errors=True)
    dest_folder.mkdir(parents=True, exist_ok=True)
    log("Extracting Chromium zip ...")
    with zipfile.ZipFile(zpath, "r") as zf:
        zf.extractall(dest_folder)
    (dest_folder / "INSTALLATION_COMPLETE").write_text("ok", encoding="utf-8")
    found = find_chrome(dest_folder) or find_chrome(dest_folder.parent)
    if not found:
        raise RuntimeError("zip extracted but chrome.exe was not inside it")
    log("Extracted Chromium -> " + str(found))
    return found


def ensure_installed(log: Optional[LogFn] = None,
                     progress: Optional[ProgressFn] = None,
                     force: bool = False) -> Path:
    log = log or (lambda m: print(m, flush=True))
    dest = apply_browser_env()
    if not force:
        found = find_chrome(dest)
        if found:
            log("App Chromium ready: " + str(found))
            if progress:
                progress(100)
            return found
    log("Installing app-only Chromium (ungoogled, GitHub) into " + str(dest))
    urls = github_zip_urls()
    zpath = dest / "chromium-download.zip"
    last_err = "no url"
    for url in urls:
        try:
            _download(url, zpath, log, progress)
            found = _extract_zip(zpath, dest / "current", log)
            try:
                zpath.unlink()
            except Exception:
                pass
            log("App Chromium ready: " + str(found))
            return found
        except Exception as e:
            last_err = "%s: %s" % (url, e)
            log("  failed: " + str(e))
            try:
                zpath.unlink(missing_ok=True)
            except Exception:
                pass
    raise RuntimeError(
        "Could not download app Chromium. Check internet (GitHub). " + last_err
    )


if __name__ == "__main__":
    try:
        print("App Chromium:", ensure_installed())
    except Exception as e:
        print("ERROR:", e)
        sys.exit(1)
