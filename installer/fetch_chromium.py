# -*- coding: utf-8 -*-
"""Download a portable **Chromium** build (not Google Chrome, not Edge).

Chrome for Testing is Google Chrome. This installer rejects that product.
Sources are official Chromium snapshots, Playwright Chromium builds, and
ungoogled-chromium. We do not fork Chromium source.

After extract the exe must exist, look like Chromium, and be registered in
INSTALLED.json. A leftover chrome.exe is not enough to mark Installed.
"""
from __future__ import annotations

import hashlib
import json
import os
import ssl
import sys
import time
import zipfile
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.request import Request, urlopen

APP_ID = "DivarMarketing"
APP_BROWSER_DIRNAME = "app-chromium"
MARKER_NAME = "INSTALLED.json"

UNGOOGLED_TAG = "151.0.7922.173-1.1"
UNGOOGLED_ZIP = "ungoogled-chromium_%s_windows_x64.zip" % UNGOOGLED_TAG
UNGOOGLED_URL = (
    "https://github.com/ungoogled-software/ungoogled-chromium-windows/"
    "releases/download/%s/%s" % (UNGOOGLED_TAG, UNGOOGLED_ZIP)
)
UNGOOGLED_OLD = (
    "https://github.com/ungoogled-software/ungoogled-chromium-windows/"
    "releases/download/137.0.7151.68-1.1/"
    "ungoogled-chromium_137.0.7151.68-1.1_windows_x64.zip"
)
GITHUB_API = (
    "https://api.github.com/repos/ungoogled-software/"
    "ungoogled-chromium-windows/releases/latest"
)

# Playwright's chromium-* zip is Chromium, not Chrome for Testing.
PW_REV = "1148"
PW_WIN = "https://playwright.azureedge.net/builds/chromium/%s/chromium-win64.zip" % PW_REV
PW_WIN_CDN = "https://cdn.playwright.dev/dbazure/download/playwright/builds/chromium/%s/chromium-win64.zip" % PW_REV
PW_WIN_NPM = "https://cdn.npmmirror.com/binaries/playwright/builds/chromium/%s/chromium-win64.zip" % PW_REV
PW_LIN = "https://playwright.azureedge.net/builds/chromium/%s/chromium-linux.zip" % PW_REV
PW_LIN_NPM = "https://cdn.npmmirror.com/binaries/playwright/builds/chromium/%s/chromium-linux.zip" % PW_REV

# Official Chromium continuous snapshot (chrome-win.zip = Chromium).
SNAP_REV = "1313161"
SNAP_WIN = (
    "https://commondatastorage.googleapis.com/chromium-browser-snapshots/"
    "Win_x64/%s/chrome-win.zip" % SNAP_REV
)
SNAP_LIN = (
    "https://commondatastorage.googleapis.com/chromium-browser-snapshots/"
    "Linux_x64/%s/chrome-linux.zip" % SNAP_REV
)

PROBE_SEC = 6.0
CONNECT_SEC = 8.0
STALL_SEC = 12.0
SOURCE_MAX_SEC = 180.0
MIN_ZIP_BYTES = 8_000_000
CHROMIUM_PRODUCTS = frozenset({"chromium", "ungoogled-chromium"})

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


def _looks_like_google_chrome_path(p: Path) -> bool:
    s = str(p).replace("\\", "/").lower()
    if "chrome-for-testing" in s or "chrome-win64" in s or "chrome-linux64" in s:
        return True
    if "/google/chrome/" in s or "program files" in s:
        return True
    return False


def find_chrome(root: Optional[Path] = None) -> Optional[Path]:
    """Only look inside the app Chromium folder — never Program Files / Edge."""
    root = Path(root) if root else browsers_dir()
    if not root.exists() or _is_bad_install_path(root):
        return None
    rels = (
        Path("chrome-win") / "chrome.exe",
        Path("Chrome-bin") / "chrome.exe",
        Path("chrome.exe"),
        Path("chrome-linux") / "chrome",
    )
    folders = [root] + sorted(
        [p for p in root.iterdir() if p.is_dir()], reverse=True)
    for folder in folders:
        if _looks_like_google_chrome_path(folder):
            continue
        for rel in rels:
            cand = folder / rel
            if cand.is_file() and not _is_bad_install_path(cand):
                if "headless" in str(cand).lower():
                    continue
                if _looks_like_google_chrome_path(cand):
                    continue
                return cand
        direct = folder / "chrome.exe"
        if direct.is_file() and not _is_bad_install_path(direct):
            if not _looks_like_google_chrome_path(direct):
                return direct
    for cand in root.rglob("chrome.exe"):
        if cand.is_file() and "headless" not in str(cand).lower():
            if _is_bad_install_path(cand) or _looks_like_google_chrome_path(cand):
                continue
            return cand
    for cand in root.rglob("chrome"):
        if cand.is_file() and os.access(cand, os.X_OK):
            if "headless" in str(cand).lower() or _is_bad_install_path(cand):
                continue
            if _looks_like_google_chrome_path(cand):
                continue
            return cand
    return None


def marker_path(root: Optional[Path] = None) -> Path:
    return (Path(root) if root else browsers_dir()) / MARKER_NAME


def read_marker(root: Optional[Path] = None) -> Dict:
    p = marker_path(root)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_marker(root: Path, rec: Dict) -> None:
    rec = dict(rec)
    rec["verified"] = True
    rec["registered_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    marker_path(root).write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")


def is_ready(root: Optional[Path] = None) -> bool:
    root = Path(root) if root else browsers_dir()
    exe = find_chrome(root)
    if not exe or not exe.is_file():
        return False
    if exe.stat().st_size < 50_000:
        return False
    rec = read_marker(root)
    if rec.get("product") not in CHROMIUM_PRODUCTS:
        return False
    if rec.get("path") and not Path(str(rec["path"])).exists():
        return False
    return True


def executable_path() -> str:
    apply_browser_env()
    if not is_ready():
        raise RuntimeError(
            "App Chromium is not installed (or a Chrome/CFT leftover was found). "
            "Run the installer / panel download so a real Chromium is extracted "
            "into DivarMarketing\\app-chromium."
        )
    found = find_chrome()
    if not found:
        raise RuntimeError("App Chromium executable missing after register")
    return str(found)


def zip_product(zpath: Path) -> str:
    """Classify a browser zip. chrome-for-testing is Google Chrome — reject."""
    if not zipfile.is_zipfile(zpath):
        return "unknown"
    with zipfile.ZipFile(zpath, "r") as zf:
        names = zf.namelist()
        blob = " ".join(names).lower()
        about = ""
        for n in names:
            ln = n.lower()
            if ln.endswith("about") or ln.endswith("about.txt") or ln.endswith("version"):
                try:
                    about += " " + zf.read(n)[:4000].decode("utf-8", "replace").lower()
                except Exception:
                    pass
        text = blob + about
        if "chrome-for-testing" in text or "google chrome for testing" in text:
            return "chrome-for-testing"
        if "google chrome" in about and "chromium" not in about:
            return "google-chrome"
        if ("chrome-win64/" in blob or "chrome-linux64/" in blob) and "ungoogled" not in blob:
            return "chrome-for-testing"
        if "ungoogled" in blob:
            return "ungoogled-chromium"
        if "chrome-win/" in blob or "chrome-linux/" in blob:
            return "chromium"
        if any(n.lower().endswith("chrome.exe") or n.endswith("/chrome") or n.endswith("\\chrome")
               for n in names):
            return "chromium"
    return "unknown"


def assert_chromium_zip(zpath: Path) -> str:
    prod = zip_product(zpath)
    if prod not in CHROMIUM_PRODUCTS:
        raise RuntimeError(
            "downloaded binary is %s, not Chromium (Chrome/CFT rejected)" % prod
        )
    return prod


def _ssl_ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _get(url: str, timeout: float = CONNECT_SEC, headers: Optional[Dict] = None):
    hdrs = {
        "User-Agent": "DivarMarketing/2.1.17",
        "Accept": "*/*",
    }
    if headers:
        hdrs.update(headers)
    req = Request(url, headers=hdrs)
    return urlopen(req, context=_ssl_ctx(), timeout=timeout)


def _github_mirrors(url: str) -> List[str]:
    out = []
    if "github.com" in url or "githubusercontent.com" in url:
        out += [
            "https://ghproxy.net/" + url,
            "https://ghfast.top/" + url,
            "https://mirror.ghproxy.com/" + url,
            url.replace("https://github.com/", "https://kkgithub.com/"),
        ]
    out.append(url)
    return out


def sources(platform: Optional[str] = None) -> List[Dict[str, str]]:
    """Chromium-only sources. No Chrome for Testing."""
    plat = platform or sys.platform
    out: List[Dict[str, str]] = []
    if plat == "win32":
        out.append({"name": "pw-chromium-npm", "url": PW_WIN_NPM, "kind": "chromium"})
        out.append({"name": "pw-chromium-azure", "url": PW_WIN, "kind": "chromium"})
        out.append({"name": "pw-chromium-cdn", "url": PW_WIN_CDN, "kind": "chromium"})
        for url in _github_mirrors(UNGOOGLED_URL):
            name = "ungoogled"
            if "ghproxy.net" in url:
                name = "ungoogled-ghproxy"
            elif "ghfast" in url:
                name = "ungoogled-ghfast"
            elif "ghproxy.com" in url:
                name = "ungoogled-mirror"
            elif "kkgithub" in url:
                name = "ungoogled-kk"
            elif "github.com" in url:
                name = "ungoogled-github"
            out.append({"name": name, "url": url, "kind": "ungoogled-chromium"})
        out.append({"name": "ungoogled-old", "url": UNGOOGLED_OLD,
                    "kind": "ungoogled-chromium"})
        out.append({"name": "chromium-snapshot", "url": SNAP_WIN, "kind": "chromium"})
    else:
        out.append({"name": "pw-chromium-linux-npm", "url": PW_LIN_NPM, "kind": "chromium"})
        out.append({"name": "pw-chromium-linux", "url": PW_LIN, "kind": "chromium"})
        out.append({"name": "chromium-snapshot-linux", "url": SNAP_LIN, "kind": "chromium"})
    return out


def github_zip_urls() -> List[str]:
    urls: List[str] = []
    try:
        with _get(GITHUB_API, timeout=8) as r:
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
    if UNGOOGLED_URL not in urls:
        urls.append(UNGOOGLED_URL)
    if UNGOOGLED_OLD not in urls:
        urls.append(UNGOOGLED_OLD)
    expanded: List[str] = []
    for u in urls:
        for m in _github_mirrors(u):
            if m not in expanded:
                expanded.append(m)
    for extra in (PW_WIN_NPM, PW_WIN, PW_WIN_CDN, SNAP_WIN):
        if extra not in expanded:
            expanded.append(extra)
    return expanded


def probe_url(url: str, timeout: float = PROBE_SEC) -> bool:
    try:
        with _get(url, timeout=timeout, headers={"Range": "bytes=0-31"}) as r:
            chunk = r.read(32)
            return bool(chunk)
    except Exception:
        return False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def verify_zip(path: Path, expected_sha256: Optional[str] = None,
               min_bytes: int = MIN_ZIP_BYTES) -> None:
    size = path.stat().st_size if path.exists() else 0
    if size < min_bytes:
        raise RuntimeError("incomplete download (%d bytes)" % size)
    if expected_sha256:
        got = sha256_file(path)
        if got.lower() != expected_sha256.lower():
            raise RuntimeError("SHA256 mismatch")
    if not zipfile.is_zipfile(path):
        raise RuntimeError("not a zip (truncated or corrupt)")
    with zipfile.ZipFile(path, "r") as zf:
        bad = zf.testzip()
        if bad is not None:
            raise RuntimeError("zip CRC failed: " + str(bad))


def _cleanup(path: Path) -> None:
    for p in (path, path.with_suffix(path.suffix + ".part")):
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass


def _download(url: str, dest: Path, log: LogFn,
              progress: Optional[ProgressFn],
              expected_sha256: Optional[str] = None,
              min_bytes: int = MIN_ZIP_BYTES) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    _cleanup(tmp)
    log("Downloading " + url)
    t0 = time.time()
    last_byte = time.time()
    n = 0
    last_pct = -1
    last_report = 0.0
    with _get(url, timeout=CONNECT_SEC) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        if total:
            log("BYTES 0/%d" % total)
        while True:
            now = time.time()
            if now - last_byte > STALL_SEC:
                raise TimeoutError("download stalled (no data for %.0fs)" % STALL_SEC)
            if now - t0 > SOURCE_MAX_SEC:
                raise TimeoutError("source exceeded %.0fs" % SOURCE_MAX_SEC)
            try:
                chunk = r.read(256 * 1024)
            except Exception as e:
                raise TimeoutError(str(e)) from e
            if not chunk:
                break
            f.write(chunk)
            n += len(chunk)
            last_byte = time.time()
            elapsed = max(0.001, last_byte - t0)
            speed = n / elapsed
            pct = int(n * 100 / total) if total else min(99, n // (2 * 1024 * 1024))
            if pct >= last_pct + 1 or (last_byte - last_report) >= 1.0:
                last_pct = pct
                last_report = last_byte
                log("PROGRESS %d" % pct)
                log("BYTES %d/%d" % (n, total))
                log("SPEED %.2f MB/s" % (speed / (1024 * 1024)))
                log("  Chromium %d%% (%d MB)" % (pct, n // (1024 * 1024)))
                if progress:
                    progress(min(100, pct))
    size = tmp.stat().st_size if tmp.exists() else 0
    if size < min_bytes:
        _cleanup(tmp)
        raise RuntimeError("download too small (%d bytes): %s" % (size, url))
    if expected_sha256:
        got = sha256_file(tmp)
        if got.lower() != expected_sha256.lower():
            _cleanup(tmp)
            raise RuntimeError("SHA256 mismatch")
    tmp.replace(dest)
    log("PROGRESS 100")
    log("BYTES %d/%d" % (size, size if not total else total))
    log("DOWNLOAD_COMPLETED")
    if progress:
        progress(100)


def _extract_zip(zpath: Path, dest_folder: Path, log: LogFn) -> Path:
    prod = assert_chromium_zip(zpath)
    if dest_folder.exists():
        import shutil
        shutil.rmtree(dest_folder, ignore_errors=True)
    dest_folder.mkdir(parents=True, exist_ok=True)
    log("Extracting Chromium zip (%s) ..." % prod)
    with zipfile.ZipFile(zpath, "r") as zf:
        zf.extractall(dest_folder)
    found = find_chrome(dest_folder) or find_chrome(dest_folder.parent)
    if not found:
        raise RuntimeError("zip extracted but Chromium chrome.exe was not inside it")
    if found.stat().st_size < 50_000:
        raise RuntimeError("extracted executable is too small to be Chromium")
    rec = {
        "product": prod,
        "path": str(found),
        "source_zip": str(zpath.name),
    }
    write_marker(dest_folder.parent if dest_folder.name == "current" else dest_folder, rec)
    write_marker(dest_folder, rec)
    (dest_folder / "INSTALLATION_COMPLETE").write_text(prod, encoding="utf-8")
    log("Extracted Chromium -> " + str(found))
    log("REGISTERED product=" + prod)
    return found


def ensure_installed(log: Optional[LogFn] = None,
                     progress: Optional[ProgressFn] = None,
                     force: bool = False) -> Path:
    log = log or (lambda m: print(m, flush=True))
    dest = apply_browser_env()
    if not force and is_ready(dest):
        found = find_chrome(dest)
        log("App Chromium ready: " + str(found))
        if progress:
            progress(100)
        return found  # type: ignore[return-value]
    if find_chrome(dest) and not is_ready(dest):
        log("Leftover Chrome/CFT (or unmarked) install ignored — fetching Chromium")
    log("CHROMIUM_START")
    log("Installing app-only Chromium (not Chrome, not Edge) into " + str(dest))
    srcs = sources()
    extra = []
    try:
        extra = github_zip_urls()
    except Exception:
        extra = []
    seen = {s["url"] for s in srcs}
    for u in extra:
        if u not in seen:
            srcs.append({"name": "extra", "url": u, "kind": "chromium"})
            seen.add(u)
    zpath = dest / "chromium-download.zip"
    last_err = "no url"
    for src in srcs:
        name, url = src["name"], src["url"]
        if "chrome-for-testing" in url:
            log("SOURCE_FAIL %s rejected Chrome for Testing URL" % name)
            continue
        log("SOURCE " + name)
        log("SOURCE_URL " + url)
        if not probe_url(url, timeout=PROBE_SEC):
            reason = "host did not answer in %.0fs" % PROBE_SEC
            log("SOURCE_FAIL %s %s" % (name, reason))
            last_err = "%s: %s" % (url, reason)
            continue
        try:
            _download(url, zpath, log, progress,
                      expected_sha256=src.get("sha256") or None)
            verify_zip(zpath, expected_sha256=src.get("sha256") or None)
            prod = assert_chromium_zip(zpath)
            log("VALIDATED product=" + prod)
            found = _extract_zip(zpath, dest / "current", log)
            write_marker(dest, {"product": prod, "path": str(found), "source": name})
            try:
                zpath.unlink()
            except Exception:
                pass
            if not is_ready(dest):
                raise RuntimeError("extract finished but Chromium did not register")
            log("CHROMIUM_OK " + str(found))
            log("App Chromium ready: " + str(found))
            return found
        except Exception as e:
            last_err = "%s: %s" % (url, e)
            log("SOURCE_FAIL %s %s" % (name, e))
            _cleanup(zpath)
    raise RuntimeError(
        "Could not download Chromium (Chrome/CFT rejected; all Chromium sources failed). "
        + last_err
    )


if __name__ == "__main__":
    try:
        print("App Chromium:", ensure_installed())
    except Exception as e:
        print("ERROR:", e)
        sys.exit(1)
