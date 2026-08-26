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
from urllib.error import HTTPError, URLError
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
CONNECT_SEC = 20.0
STALL_SEC = 30.0
RESUME_TRIES = 12
RECONNECT_WAIT = 2.0
MIN_ZIP_BYTES = 8_000_000
CHROMIUM_PRODUCTS = frozenset({"chromium", "ungoogled-chromium"})
ZIP_NAME = "chromium-download.zip"

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
        "User-Agent": "DivarMarketing/2.1.18",
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
    for p in (path, path.with_suffix(path.suffix + ".part"),
              path.with_suffix(path.suffix + ".part.url")):
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass


def _part_paths(dest: Path) -> tuple:
    tmp = dest.with_suffix(dest.suffix + ".part")
    meta = dest.with_suffix(dest.suffix + ".part.url")
    return tmp, meta


def find_cached_zip(root: Path) -> Optional[Path]:
    """Reuse a Chromium zip already sitting in the dedicated install folder."""
    cands = [root / ZIP_NAME]
    try:
        cands.extend(sorted(root.glob("*.zip")))
    except Exception:
        pass
    seen = set()
    for p in cands:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        if not p.is_file():
            continue
        try:
            verify_zip(p)
            assert_chromium_zip(p)
            return p
        except Exception:
            continue
    return None


def _usable_existing(dest: Path, expected_sha256: Optional[str],
                     min_bytes: int) -> bool:
    if not dest.is_file() or dest.stat().st_size < min_bytes:
        return False
    try:
        if expected_sha256:
            if sha256_file(dest).lower() != expected_sha256.lower():
                return False
        verify_zip(dest, expected_sha256=expected_sha256, min_bytes=min_bytes)
        return True
    except Exception:
        return False


class DownloadManager:
    """Resume-capable downloader (HTTP Range + retry).

    Brief zero-speed or a short disconnect reconnects the SAME url and
    appends to the .part file in the install folder. It does not start
    over and does not jump to another source.
    """

    def __init__(self, log: LogFn, progress: Optional[ProgressFn] = None):
        self.log = log
        self.progress = progress

    def fetch(self, url: str, dest: Path,
              expected_sha256: Optional[str] = None,
              min_bytes: int = MIN_ZIP_BYTES) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if _usable_existing(dest, expected_sha256, min_bytes):
            self.log("REUSING existing zip " + str(dest))
            self.log("PROGRESS 100")
            self.log("DOWNLOAD_COMPLETED")
            if self.progress:
                self.progress(100)
            return
        tmp, meta = _part_paths(dest)
        n = 0
        if tmp.exists():
            saved = ""
            if meta.exists():
                try:
                    saved = meta.read_text(encoding="utf-8").strip()
                except Exception:
                    saved = ""
            if saved and saved != url:
                self.log("PARTIAL is from another source - starting a new file")
                _cleanup(dest)
                n = 0
            else:
                n = tmp.stat().st_size
                if n:
                    self.log("RESUME %d bytes from %s" % (n, tmp.name))
        try:
            meta.write_text(url, encoding="utf-8")
        except Exception:
            pass
        self.log("Downloading " + url)
        total = 0
        last_pct = -1
        last_report = 0.0
        t0 = time.time()
        got_any = False
        for attempt in range(1, RESUME_TRIES + 1):
            headers = {}
            if n > 0:
                headers["Range"] = "bytes=%d-" % n
                self.log("RESUME attempt %d at byte %d" % (attempt, n))
            try:
                r = _get(url, timeout=CONNECT_SEC, headers=headers or None)
            except HTTPError as e:
                if e.code == 416 and n >= min_bytes:
                    self.log("HTTP 416 - treating %d bytes as complete" % n)
                    break
                if e.code in (401, 403, 404, 410, 451):
                    raise RuntimeError("HTTP %s from %s" % (e.code, url)) from e
                self.log("RECONNECT %d/%d after HTTP %s" % (
                    attempt, RESUME_TRIES, e.code))
                if attempt >= RESUME_TRIES:
                    raise TimeoutError("reconnect failed: HTTP %s" % e.code) from e
                time.sleep(RECONNECT_WAIT * min(attempt, 5))
                continue
            except (URLError, TimeoutError, OSError) as e:
                self.log("RECONNECT %d/%d after connect error: %s" % (
                    attempt, RESUME_TRIES, e))
                if attempt >= RESUME_TRIES:
                    raise TimeoutError("reconnect failed: %s" % e) from e
                time.sleep(RECONNECT_WAIT * min(attempt, 5))
                continue
            status = int(getattr(r, "status", 200) or 200)
            cl = int(r.headers.get("Content-Length") or 0)
            crange = str(r.headers.get("Content-Range") or "")
            if status == 206 and "/" in crange:
                try:
                    total = int(crange.rsplit("/", 1)[-1])
                except ValueError:
                    total = total or (n + cl)
                mode = "ab"
            elif status == 200 and n > 0:
                self.log("server ignored Range — restarting this source from 0")
                n = 0
                mode = "wb"
                total = cl
            else:
                mode = "ab" if n else "wb"
                total = cl
            last_byte = time.time()
            stalled = False
            read_error = False
            try:
                with r, open(tmp, mode) as f:
                    if total:
                        self.log("BYTES %d/%d" % (n, total))
                    while True:
                        if time.time() - last_byte > STALL_SEC:
                            self.log("STALL kept %d bytes - reconnect same source" % n)
                            stalled = True
                            break
                        try:
                            chunk = r.read(256 * 1024)
                        except Exception as e:
                            self.log("READ fail, resume same source: %s" % e)
                            read_error = True
                            break
                        if not chunk:
                            break
                        f.write(chunk)
                        n += len(chunk)
                        got_any = True
                        last_byte = time.time()
                        elapsed = max(0.001, last_byte - t0)
                        speed = n / elapsed
                        pct = int(n * 100 / total) if total else min(
                            99, n // (2 * 1024 * 1024))
                        if pct >= last_pct + 1 or (last_byte - last_report) >= 1.0:
                            last_pct = pct
                            last_report = last_byte
                            self.log("PROGRESS %d" % pct)
                            self.log("BYTES %d/%d" % (n, total))
                            self.log("SPEED %.2f MB/s" % (speed / (1024 * 1024)))
                            self.log("  Chromium %d%% (%d MB)" % (
                                pct, n // (1024 * 1024)))
                            if self.progress:
                                self.progress(min(100, pct))
            except Exception as e:
                self.log("STREAM fail, resume same source: %s" % e)
                read_error = True
            size = tmp.stat().st_size if tmp.exists() else 0
            n = size
            done = size >= min_bytes and (not total or size >= total)
            if done:
                break
            if size == 0 and not got_any and not stalled and not read_error:
                _cleanup(dest)
                raise RuntimeError("download too small (0 bytes): %s" % url)
            if attempt >= RESUME_TRIES:
                raise TimeoutError(
                    "could not finish after %d reconnects (%d bytes kept)" % (
                        RESUME_TRIES, size))
            time.sleep(RECONNECT_WAIT)
        size = tmp.stat().st_size if tmp.exists() else 0
        if size < min_bytes:
            raise RuntimeError("download too small (%d bytes): %s" % (size, url))
        if expected_sha256:
            got = sha256_file(tmp)
            if got.lower() != expected_sha256.lower():
                _cleanup(dest)
                raise RuntimeError("SHA256 mismatch")
        tmp.replace(dest)
        try:
            meta.unlink()
        except Exception:
            pass
        self.log("PROGRESS 100")
        self.log("BYTES %d/%d" % (size, size if not total else total))
        self.log("DOWNLOAD_COMPLETED")
        if self.progress:
            self.progress(100)


def _download(url: str, dest: Path, log: LogFn,
              progress: Optional[ProgressFn],
              expected_sha256: Optional[str] = None,
              min_bytes: int = MIN_ZIP_BYTES) -> None:
    DownloadManager(log, progress).fetch(
        url, dest, expected_sha256=expected_sha256, min_bytes=min_bytes)


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
    log("Installing app-only Chromium into dedicated folder " + str(dest))
    zpath = dest / ZIP_NAME
    cached = find_cached_zip(dest)
    if cached:
        try:
            log("REUSING zip already in install folder: " + str(cached))
            verify_zip(cached)
            prod = assert_chromium_zip(cached)
            log("VALIDATED product=" + prod)
            found = _extract_zip(cached, dest / "current", log)
            write_marker(dest, {"product": prod, "path": str(found),
                                "source": "cached-zip"})
            if not is_ready(dest):
                raise RuntimeError("extract finished but Chromium did not register")
            log("CHROMIUM_OK " + str(found))
            log("App Chromium ready: " + str(found))
            if progress:
                progress(100)
            return found
        except Exception as e:
            log("cached zip not usable: %s" % e)
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
            if not is_ready(dest):
                raise RuntimeError("extract finished but Chromium did not register")
            log("CHROMIUM_OK " + str(found))
            log("App Chromium ready: " + str(found))
            return found
        except Exception as e:
            last_err = "%s: %s" % (url, e)
            log("SOURCE_FAIL %s %s" % (name, e))
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
