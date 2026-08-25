# -*- coding: utf-8 -*-
"""باز کردن دیوار با سشن همان اکانت برنامه (نه تب مهمان) — با پشتیبانی از localStorage.

دیوار داخل iframe پنل باز نمی‌شود (refused to connect). تب معمولی هم
با اکانت برنامه لاگین نیست. این ماژول:
1. کوکی‌ها و localStorage سشن را از فایل سشن می‌خواند
2. مرورگر را با CDP (Chrome DevTools Protocol) باز می‌کند
3. هم کوکی‌ها و هم localStorage را تزریق می‌کند
4. به صفحهٔ محصول (کپچا) ناویگیت می‌کند

تضمین می‌شود که پس از باز شدن مرورگر:
- همان اکانت لاگین است (نه تب مهمان)
- همان محصول با کپچا نمایش داده می‌شود
- اپراتور فقط کپچا را حل می‌کند، ربات خودکار کاری نمی‌کند
"""

from __future__ import annotations

import json
import os
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

# ─── لاگ تگ‌های متمرکز ─────────────────────────────────────────────
_LOG_TAG_AUTH = "[AUTH]"
_LOG_TAG_SESSION = "[SESSION]"
_LOG_TAG_BROWSER = "[BROWSER]"
_LOG_TAG_CAPTCHA = "[CAPTCHA]"
_LOG_TAG_ACCOUNT = "[ACCOUNT]"


def _sv_log(level: str, tag: str, message: str) -> None:
    """لاگ متمرکز برای Authentication/Session/Browser/CAPTCHA/Account."""
    try:
        from .logging_util import log
        log(level, f"{tag} {message}")
    except Exception:
        pass


# ═══ کلیدهای localStorage که SPA دیوار برای احراز هویت استفاده می‌کند ═══
_DIVAR_STORAGE_KEYS = frozenset({
    "sAccessToken",
    "sFrontToken",
    "token",
    "refresh_token",
    "user_phone",
    "user_id",
})


def persistent_profile_dir(session_path: str) -> Path:
    """یک پروفایل مرورگر دائمی کنار session.json همین اکانت — پاک نمی‌شود."""
    return Path(session_path).resolve().parent / "browser-profile"


def _atomic_write(target_path: Path, data: Dict[str, Any]) -> None:
    """نوشتن اتمی فایل سشن (.tmp -> validate -> rename).

    اگر پروسه هنگام Write Crash کند، سشن قبلی از بین نمی‌رود.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(".session.tmp")
    try:
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8")
        # validate JSON by re-reading
        json.loads(tmp_path.read_text(encoding="utf-8"))
        tmp_path.rename(target_path)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        raise


def _merge_session_data(session_path: str,
                        cookies: List[Dict[str, Any]],
                        local_storage: Optional[Dict[str, str]] = None) -> int:
    """کوکی‌های حل‌شده و localStorage را به session.json برمی‌گرداند.

    Returns: تعداد کوکی‌های جدید اضافه‌شده
    """
    p = Path(session_path)
    data: Dict[str, Any] = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}

    jar = data.get("cookies") or {}
    if not isinstance(jar, dict):
        jar = {}
    n = 0
    for ck in cookies or []:
        if not isinstance(ck, dict):
            continue
        name = str(ck.get("name") or "")
        val = ck.get("value")
        domain = str(ck.get("domain") or "")
        if not name or val is None:
            continue
        if domain and "divar.ir" not in domain.lower():
            continue
        jar[name] = str(val)
        n += 1
    data["cookies"] = jar
    if not data.get("token"):
        data["token"] = jar.get("sAccessToken") or jar.get("token") or ""

    # Merge localStorage state
    if local_storage is not None:
        existing_storage = data.get("localStorage", {})
        if not isinstance(existing_storage, dict):
            existing_storage = {}
        for k, v in local_storage.items():
            if v is not None:
                existing_storage[k] = v
        data["localStorage"] = existing_storage

    # Atomic write
    _atomic_write(p, data)
    return n


def _get_local_storage_from_session(session_path: str) -> Dict[str, str]:
    """دریافت localStorage ذخیره‌شده در فایل سشن."""
    p = Path(session_path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        ls = data.get("localStorage") or {}
        return dict(ls) if isinstance(ls, dict) else {}
    except Exception:
        return {}


def merge_session_cookies(session_path: str, cookies: List[Dict[str, Any]]) -> int:
    """Legacy backward-compatible wrapper — calls _merge_session_data with no localStorage."""
    return _merge_session_data(session_path, cookies, None)


def _cleanup_old_temp_profiles(session_path: str) -> None:
    parent = Path(session_path).resolve().parent
    import shutil
    try:
        for p in parent.glob("puzzle-live-*"):
            shutil.rmtree(p, ignore_errors=True)
    except Exception:
        pass


def cookies_from_session(session_path: str) -> List[Dict[str, Any]]:
    """کوکی‌هایی که باید روی divar.ir ست شوند تا همان لاگین برنامه باشد.

    Returns: لیست دیکشنری‌های کوکی برای CDP Network.setCookie
    """
    p = Path(session_path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    token = str(data.get("token") or "")
    raw = data.get("cookies") or {}
    if not isinstance(raw, dict):
        raw = {}
    names_seen = set()
    out: List[Dict[str, Any]] = []

    def add(name: str, value: str) -> None:
        if not name or value is None or name in names_seen:
            return
        names_seen.add(name)
        out.append({"name": str(name), "value": str(value),
                    "domain": ".divar.ir", "path": "/", "secure": True})

    for k, v in raw.items():
        add(str(k), str(v))
    if token:
        add("token", token)
        add("sAccessToken", token)
    return out


def localStorage_from_session(session_path: str) -> Dict[str, str]:
    """localStorage‌ای که باید تزریق شود تا SPA دیوار لاگین را تشخیص دهد.

    برنامه SPA دیوار (React) بعد از لود صفحه، localStorage را چک می‌کند.
    اگر توکن‌های JWT/احراز هویت در localStorage نباشند، صفحه لاگین را نشان می‌دهد
    حتی اگر کوکی‌ها درست باشند. این تابع localStorage را از فایل سشن می‌خواند
    یا در صورت نبودن، از کوکی‌ها/توکن مقادیر پیش‌فرض می‌سازد.
    """
    p = Path(session_path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

    # First check if localStorage was saved explicitly
    saved_ls = data.get("localStorage") or {}
    if isinstance(saved_ls, dict) and saved_ls:
        return dict(saved_ls)

    # Otherwise reconstruct from token/cookies
    token = str(data.get("token") or "")
    cookies = data.get("cookies") or {}
    if not isinstance(cookies, dict):
        cookies = {}

    ls: Dict[str, str] = {}
    sAccess = cookies.get("sAccessToken") or token or ""
    sFront = cookies.get("sFrontToken") or ""

    if sAccess:
        ls["sAccessToken"] = sAccess
    if sFront:
        ls["sFrontToken"] = sFront
    if token and "sAccessToken" not in ls:
        ls["sAccessToken"] = token
    if token:
        ls["token"] = token

    return ls


def _inject_local_storage(cdp_client: "CdpClient", ls_items: Dict[str, str]) -> int:
    """تزریق localStorage به مرورگر از طریق CDP.

    SPAهای مدرن (مانند دیوار) بعد از بارگذاری صفحه، localStorage را برای
    تشخیص لاگین چک می‌کنند. این تابع قبل از ناویگیت به صفحه، آیتم‌های
    localStorage را ست می‌کند تا SPA کاربر را لاگین‌شده تشخیص دهد.

    Returns: تعداد آیتم‌های تزریق‌شده
    """
    n = 0
    for key, value in ls_items.items():
        if not key or value is None:
            continue
        # Sanitize: escape quotes for JS
        safe_key = key.replace("\\", "\\\\").replace("'", "\\'")
        safe_val = str(value).replace("\\", "\\\\").replace("'", "\\'")
        expr = f"localStorage.setItem('{safe_key}', '{safe_val}')"
        try:
            cdp_client.call("Runtime.evaluate", {
                "expression": expr,
                "returnByValue": True,
            }, timeout=2)
            n += 1
        except Exception:
            pass
    return n


def find_browsers() -> List[str]:
    env = os.environ.get("DIVAR_BROWSER") or ""
    cands = [env] if env else []
    if sys.platform == "win32":
        pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        pfx = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        cands += [
            os.path.join(pfx, r"Microsoft\Edge\Application\msedge.exe"),
            os.path.join(pf, r"Microsoft\Edge\Application\msedge.exe"),
            os.path.join(local, r"Microsoft\Edge\Application\msedge.exe"),
            os.path.join(pf, r"Google\Chrome\Application\chrome.exe"),
            os.path.join(pfx, r"Google\Chrome\Application\chrome.exe"),
            os.path.join(local, r"Google\Chrome\Application\chrome.exe"),
        ]
    else:
        cands += ["microsoft-edge", "msedge", "google-chrome", "chromium",
                  "chromium-browser", "google-chrome-stable"]
    out: List[str] = []
    seen = set()
    from shutil import which
    for c in cands:
        if not c:
            continue
        path = c if os.path.isfile(c) else which(c)
        if not path:
            continue
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def find_browser() -> Optional[str]:
    found = find_browsers()
    return found[0] if found else None


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _ws_connect(ws_url: str, timeout: float = 8.0) -> socket.socket:
    u = urlparse(ws_url)
    host = u.hostname or "127.0.0.1"
    port = u.port or (443 if u.scheme == "wss" else 80)
    path = u.path + (("?" + u.query) if u.query else "")
    key = __import__("base64").b64encode(os.urandom(16)).decode()
    req = (f"GET {path or '/'} HTTP/1.1\r\n"
           f"Host: {host}:{port}\r\n"
           "Upgrade: websocket\r\nConnection: Upgrade\r\n"
           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
    sock = socket.create_connection((host, port), timeout=timeout)
    sock.sendall(req.encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    if b"101" not in buf.split(b"\r\n", 1)[0]:
        sock.close()
        raise RuntimeError("CDP websocket handshake failed")
    return sock


def _ws_send(sock: socket.socket, text: str) -> None:
    data = text.encode("utf-8")
    mask = os.urandom(4)
    header = bytearray([0x81])
    n = len(data)
    if n < 126:
        header.append(0x80 | n)
    elif n < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", n))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", n))
    header.extend(mask)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    sock.sendall(header + masked)


def _http_get_local(port: int, path: str, timeout: float = 1.8) -> str:
    """GET روی 127.0.0.1 — هرگز از پروکسی سیستم استفاده نمی‌کند."""
    if int(port) <= 0:
        raise RuntimeError("پورت دیباگ هنوز صفر است")
    last = "پاسخ خالی از CDP"
    for _ in range(3):
        sock = None
        try:
            sock = socket.create_connection(("127.0.0.1", int(port)),
                                            timeout=timeout)
            req = (f"GET {path} HTTP/1.0\r\n"
                   f"Host: 127.0.0.1:{int(port)}\r\n"
                   "Connection: close\r\n\r\n")
            sock.sendall(req.encode("ascii"))
            sock.settimeout(timeout)
            buf = b""
            expected = None
            while True:
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    break
                if not chunk:
                    break
                buf += chunk
                if len(buf) > 2_000_000:
                    break
                if b"\r\n\r\n" not in buf:
                    continue
                head, body = buf.split(b"\r\n\r\n", 1)
                if expected is None:
                    expected = 0
                    for line in head.split(b"\r\n")[1:]:
                        if line.lower().startswith(b"content-length:"):
                            try:
                                expected = int(line.split(b":", 1)[1].strip())
                            except (ValueError, IndexError):
                                expected = 0
                            break
                if expected and len(body) >= expected:
                    break
        except OSError as e:
            last = str(e)
            time.sleep(0.15)
            continue
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
        if b"\r\n\r\n" not in (buf if "buf" in locals() else b""):
            last = "پاسخ خالی از CDP"
            time.sleep(0.15)
            continue
        head, body = buf.split(b"\r\n\r\n", 1)
        status = head.split(b"\r\n", 1)[0]
        if b"200" not in status:
            last = status.decode("ascii", errors="replace")[:80]
            time.sleep(0.15)
            continue
        return body.decode("utf-8", errors="replace")
    raise RuntimeError(last)


def _devtools_port_file(profile: Path) -> int:
    p = Path(profile) / "DevToolsActivePort"
    if not p.exists():
        return 0
    try:
        line = p.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        return int(line.strip())
    except Exception:
        return 0


def _page_ws_from_list(port: int) -> str:
    body = _http_get_local(port, "/json/list")
    tabs = json.loads(body or "[]")
    if not isinstance(tabs, list):
        return ""
    for t in tabs:
        if not isinstance(t, dict):
            continue
        if t.get("type") not in ("page", "webview", None):
            continue
        ws = t.get("webSocketDebuggerUrl") or ""
        if ws:
            return str(ws)
    for t in tabs:
        if isinstance(t, dict) and t.get("webSocketDebuggerUrl"):
            return str(t["webSocketDebuggerUrl"])
    return ""


def _clear_stale_locks(profile: Path) -> None:
    """قفل باقی‌ماندهٔ Edge قبلی باعث می‌شود پورت دیباگ نادیده گرفته شود."""
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie",
                 "lockfile", "DevToolsActivePort"):
        p = Path(profile) / name
        try:
            if p.exists() or p.is_symlink():
                p.unlink()
        except Exception:
            pass


def _tail_text(path: Path, n: int = 400) -> str:
    try:
        raw = Path(path).read_bytes()
    except Exception:
        return ""
    return raw[-n:].decode("utf-8", errors="replace").strip()


def _wait_cdp(port: int, tries: int = 80, profile: Optional[Path] = None,
              proc: Optional[subprocess.Popen] = None) -> str:
    last = ""
    use_port = int(port)
    for _ in range(tries):
        if proc is not None and proc.poll() is not None:
            hint = ""
            if profile:
                hint = _tail_text(Path(profile) / "browser.err")
            raise RuntimeError(
                "مرورگر پازل بسته شد قبل از آماده شدن"
                + (f" — {hint[:180]}" if hint else "")
            )
        if profile:
            file_port = _devtools_port_file(profile)
            if file_port:
                use_port = file_port
        if use_port <= 0:
            time.sleep(0.2)
            continue
        try:
            ws = _page_ws_from_list(use_port)
            if ws:
                return ws
        except Exception as e:
            last = str(e)
        try:
            data = json.loads(_http_get_local(use_port, "/json/version"))
            ws = data.get("webSocketDebuggerUrl") or ""
            if ws:
                return str(ws)
        except Exception as e:
            last = str(e)
        time.sleep(0.25)
    raise RuntimeError(
        "مرورگر روی رایانه برای پازل آماده نشد"
        + (f" ({last})" if last else "")
    )


def _kill_proc(proc: Optional[subprocess.Popen]) -> None:
    if not proc or proc.poll() is not None:
        return
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=8)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        return
    try:
        proc.terminate()
        proc.wait(timeout=2)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _browser_cmd(browser: str, profile: Path, port: int) -> List[str]:
    return [
        browser,
        f"--user-data-dir={str(profile)}",
        f"--remote-debugging-port={int(port)}",
        "--remote-debugging-address=127.0.0.1",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--disable-popup-blocking",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-backgrounding-occluded-windows",
        "--disable-features=Translate,MediaRouter",
        "--disable-hang-monitor",
        "--metrics-recording-only",
        "--force-device-scale-factor=1",
        "--window-size=900,720",
        "--window-position=60,40",
        "--new-window",
        "about:blank",
    ]


def run_logged_in_browser(session_path: str, start_url: str = "https://divar.ir") -> str:
    """Edge/Chrome را با کوکی + localStorage همان اکانت باز می‌کند.

    این تابع هم کوکی‌ها و هم localStorage را تزریق می‌کند تا SPA دیوار
    کاربر را لاگین‌شده تشخیص دهد.
    """
    _sv_log("info", _LOG_TAG_SESSION, f"باز کردن مرورگر با سشن {session_path}")
    browser = find_browser()
    if not browser:
        raise RuntimeError("Edge/Chrome پیدا نشد — برای پازل همان اکانت لازم است")
    cookies = cookies_from_session(session_path)
    if not cookies:
        raise RuntimeError("سشن این اکانت خالی است — دوباره لاگین کنید")
    ls_items = localStorage_from_session(session_path)
    if not ls_items:
        _sv_log("warning", _LOG_TAG_AUTH,
                "localStorage در سشن خالی است — لاگین ممکن است کار نکند")
    profile = persistent_profile_dir(session_path)
    profile.mkdir(parents=True, exist_ok=True)
    _clear_stale_locks(profile)
    port = 0
    cmd = [
        browser,
        f"--user-data-dir={str(profile)}",
        "--remote-debugging-port=0",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        f"--app={start_url}",
    ]
    _sv_log("info", _LOG_TAG_BROWSER, f"لانچ مرورگر برای {Path(session_path).parent.name}")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws = _wait_cdp(port, tries=100, profile=profile, proc=proc)
    cdp = CdpClient(ws)
    try:
        cdp.call("Network.enable")
        cdp.call("Page.enable")
        try:
            cdp.call("Runtime.enable")
        except Exception:
            pass
        for ck in cookies:
            try:
                cdp.call("Network.setCookie", {
                    "name": ck["name"], "value": ck["value"],
                    "domain": ck.get("domain") or ".divar.ir",
                    "path": ck.get("path") or "/",
                    "secure": True,
                    "httpOnly": ck["name"] != "sFrontToken",
                })
            except Exception:
                pass
        # تزریق localStorage قبل از ناویگیت — حیاتی برای SPA
        n_ls = _inject_local_storage(cdp, ls_items)
        _sv_log("info", _LOG_TAG_AUTH, f"{n_ls} آیتم localStorage تزریق شد")
        cdp.call("Page.navigate", {"url": start_url}, timeout=20)
        time.sleep(0.8)
    finally:
        try:
            cdp.close()
        except Exception:
            pass
    _sv_log("success", _LOG_TAG_SESSION, f"مرورگر با سشن {Path(session_path).parent.name} باز شد")
    return f"opened {browser} as session {Path(session_path).parent.name}"


def _recv_n(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise RuntimeError("CDP socket closed")
        buf += chunk
    return buf


def _ws_recv(sock: socket.socket, timeout: float = 8.0) -> Optional[str]:
    sock.settimeout(timeout)
    hdr = _recv_n(sock, 2)
    opcode = hdr[0] & 0x0F
    ln = hdr[1] & 0x7F
    masked = bool(hdr[1] & 0x80)
    if ln == 126:
        ln = struct.unpack("!H", _recv_n(sock, 2))[0]
    elif ln == 127:
        ln = struct.unpack("!Q", _recv_n(sock, 8))[0]
    mask = _recv_n(sock, 4) if masked else b""
    data = _recv_n(sock, ln)
    if mask:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    if opcode == 0x9:
        _ws_send(sock, "")
        return None
    if opcode in (0x8, 0xA):
        return None
    if opcode != 0x1:
        return None
    return data.decode("utf-8", errors="replace")


class CdpClient:
    """کلاینت CDP (Chrome DevTools Protocol) از طریق WebSocket."""

    def __init__(self, ws_url: str):
        self.sock = _ws_connect(ws_url)
        self._n = 0

    def call(self, method: str, params: Optional[Dict[str, Any]] = None,
             timeout: float = 10.0) -> Dict[str, Any]:
        self._n += 1
        mid = self._n
        _ws_send(self.sock, json.dumps(
            {"id": mid, "method": method, "params": params or {}}))
        t0 = time.time()
        while time.time() - t0 < timeout:
            left = timeout - (time.time() - t0)
            try:
                raw = _ws_recv(self.sock, timeout=max(0.2, left))
            except socket.timeout:
                continue
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except ValueError:
                continue
            if data.get("id") != mid:
                continue
            if data.get("error"):
                raise RuntimeError(str(data["error"])[:180])
            return data.get("result") or {}
        raise TimeoutError(method)

    def close(self) -> None:
        try:
            self.sock.close()
        except Exception:
            pass


# ─── Session validation helpers ───────────────────────────────────

def validate_session(session_path: str) -> Dict[str, Any]:
    """اعتبارسنجی کامل سشن.

    بررسی می‌کند:
    - فایل وجود دارد
    - JSON معتبر است
    - توکن وجود دارد
    - localStorage (در صورت نیاز) وجود دارد

    Returns: {"valid": bool, "has_token": bool, "has_ls": bool, "detail": str}
    """
    p = Path(session_path)
    if not p.exists():
        return {"valid": False, "detail": "فایل سشن وجود ندارد"}

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        return {"valid": False, "detail": f"JSON نامعتبر: {e}"}

    token = data.get("token") or data.get("cookies", {}).get("sAccessToken") or ""
    if not token:
        return {"valid": False, "detail": "توکن لاگین وجود ندارد"}

    has_ls = bool(data.get("localStorage"))
    return {
        "valid": True,
        "has_token": bool(token),
        "has_ls": has_ls,
        "detail": f"توکن موجود ({len(token)} کاراکتر)" +
                  (", localStorage موجود" if has_ls else ", localStorage موجود نیست — ممکن است SPA لاگین را تشخیص ندهد"),
    }


# ─── PuzzleLive with localStorage support ───────────────────────

class PuzzleLive:
    """سشن دیوار همین اکانت — تصویر داخل پاپ‌آپ پنل، بدون iframe.

    این کلاس:
    1. مرورگر را با پروفایل دائمی اکانت باز می‌کند
    2. کوکی‌ها و localStorage را تزریق می‌کند
    3. به URL موردنظر ناویگیت می‌کند
    4. منتظر می‌ماند تا اپراتور کپچا را حل کند
    5. سپس کوکی‌ها و localStorage به‌روزشده را برمی‌گرداند
    """

    def __init__(self) -> None:
        self.proc: Optional[subprocess.Popen] = None
        self.cdp: Optional[CdpClient] = None
        self.profile: Optional[Path] = None
        self.session_path: str = ""
        self.last_jpeg = b""
        self.last_err = ""
        self.lock = __import__("threading").Lock()

    def start(self, session_path: str, start_url: str = "https://divar.ir") -> None:
        """مرورگر را باز می‌کند و کوکی+localStorage را تزری می‌کند.

        Args:
            session_path: مسیر فایل session.json اکانت
            start_ur: URL مقصد (محصول با کپچا)
        """
        _sv_log("info", _LOG_TAG_SESSION, f"PuzzleLive.start({session_path}, {start_url})")
        browsers = find_browsers()
        if not browsers:
            raise RuntimeError("Edge یا Chrome روی این رایانه پیدا نشد")

        cookies = cookies_from_session(session_path)
        if not cookies:
            raise RuntimeError("سشن این اکانت خالی است — دوباره لاگین کنید")

        ls_items = localStorage_from_session(session_path)
        if not ls_items:
            _sv_log("warning", _LOG_TAG_AUTH, "localStorage خالی است")
        else:
            _sv_log("info", _LOG_TAG_AUTH, f"{len(ls_items)} آیتم localStorage از فایل سشن خوانده شد")

        # Validate the start_url — never use root URL for product pages
        if not start_url or start_url == "about:blank":
            _sv_log("error", _LOG_TAG_CAPTCHA, "start_url نامعتبر است")
            raise RuntimeError("URL مقصد نامعتبر است")
        if start_url in ("https://divar.ir", "https://www.divar.ir", "https://divar.ir/"):
            _sv_log("warning", _LOG_TAG_CAPTCHA,
                    "start_url به ریشه دیوار اشاره دارد — ممکن است محصول مشخص نباشد")

        _sv_log("info", _LOG_TAG_CAPTCHA, f"باز شدن مرورگر برای URL: {start_url}")

        self.session_path = session_path
        _cleanup_old_temp_profiles(session_path)

        # همان پروفایل دائمی اکانت
        profile = persistent_profile_dir(session_path)
        profile.mkdir(parents=True, exist_ok=True)
        self.profile = profile
        _clear_stale_locks(profile)

        last = ""
        for browser in browsers:
            port = 0
            cmd = _browser_cmd(browser, profile, port)
            err_log = profile / "browser.err"
            err_f = open(err_log, "wb")
            try:
                self.proc = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=err_f)
            except Exception as e:
                try:
                    err_f.close()
                except Exception:
                    pass
                last = str(e)
                continue
            try:
                err_f.close()
            except Exception:
                pass
            try:
                ws = _wait_cdp(port, tries=100, profile=profile, proc=self.proc)
            except Exception as e:
                last = str(e)
                hint = _tail_text(err_log)
                if hint:
                    last = f"{last} | {hint[:160]}"
                _kill_proc(self.proc)
                self.proc = None
                continue

            self.cdp = CdpClient(ws)
            try:
                self.cdp.call("Network.enable")
                self.cdp.call("Page.enable")
                try:
                    self.cdp.call("Runtime.enable")
                except Exception:
                    pass

                # 1) کوکی‌ها را تزریق کن
                for ck in cookies:
                    try:
                        self.cdp.call("Network.setCookie", {
                            "name": ck["name"], "value": ck["value"],
                            "domain": ck.get("domain") or ".divar.ir",
                            "path": ck.get("path") or "/",
                            "secure": True,
                            "httpOnly": ck["name"] != "sFrontToken",
                        })
                    except Exception:
                        pass

                # 2) localStorage را تزریق کن (بعد از کوکی‌ها، قبل از ناویگیت)
                n_ls = _inject_local_storage(self.cdp, ls_items)
                _sv_log("info", _LOG_TAG_AUTH, f"{n_ls} آیتم localStorage تزریق شد")
                if n_ls == 0 and ls_items:
                    _sv_log("warning", _LOG_TAG_AUTH,
                            "localStorage تزریق نشد — ممکن است SPA لاگین را تشخیص ندهد")

                # 3) به URL مقصد ناویگیت کن
                self.cdp.call("Page.navigate", {"url": start_url}, timeout=20)
                self._wait_ready()
                self._nudge_window()

                _sv_log("success", _LOG_TAG_CAPTCHA, f"مرورگر برای {start_url} باز شد")
            except Exception as e:
                last = str(e)
                try:
                    self.cdp.close()
                except Exception:
                    pass
                self.cdp = None
                _kill_proc(self.proc)
                self.proc = None
                continue
            return

        raise RuntimeError(
            "پازل روی رایانه باز نشد. پروکسی/وی‌پی‌ان سیستم را برای این برنامه "
            "خاموش کنید، Edge/Chrome را ببندید و دوباره «نمایش پازل» را بزنید"
            + (f" — {last}" if last else "")
        )

    def _wait_ready(self) -> None:
        if not self.cdp:
            return
        for _ in range(25):
            try:
                r = self.cdp.call("Runtime.evaluate", {
                    "expression": "document.readyState",
                    "returnByValue": True,
                }, timeout=2)
                if (r.get("result") or {}).get("value") == "complete":
                    break
            except Exception:
                pass
            time.sleep(0.25)
        time.sleep(0.8)

    def _nudge_window(self) -> None:
        """پنجره را کوچک نگه می‌دارد تا صفحه رنگ شود (مینیمایز = تصویر سیاه)."""
        if not self.cdp:
            return
        try:
            win = self.cdp.call("Browser.getWindowForTarget", timeout=3)
            wid = win.get("windowId")
            if wid:
                self.cdp.call("Browser.setWindowBounds", {
                    "windowId": wid,
                    "bounds": {"left": 40, "top": 40, "width": 900, "height": 720,
                               "windowState": "normal"},
                }, timeout=3)
        except Exception:
            pass

    def harvest_state(self) -> int:
        """کوکی‌ها و localStorage را از مرورگر جمع‌آوری کرده و در فایل سشن ذخیره می‌کند.

        Returns: تعداد آیتم‌های ذخیره‌شده
        """
        if not self.cdp or not self.session_path:
            return 0

        # 1) Get cookies
        cookies: List[Dict[str, Any]] = []
        try:
            r = self.cdp.call("Network.getCookies", {
                "urls": ["https://divar.ir", "https://api.divar.ir",
                         "https://www.divar.ir"],
            }, timeout=5)
            cookies = list(r.get("cookies") or [])
        except Exception:
            cookies = []
        if not cookies:
            try:
                r = self.cdp.call("Network.getAllCookies", timeout=5)
                cookies = list(r.get("cookies") or [])
            except Exception:
                return 0

        # 2) Get localStorage
        ls = {}
        try:
            r = self.cdp.call("Runtime.evaluate", {
                "expression": "JSON.stringify(window.localStorage)",
                "returnByValue": True,
            }, timeout=5)
            val = r.get("result", {}).get("value")
            if val and isinstance(val, str):
                parsed = json.loads(val)
                if isinstance(parsed, dict):
                    ls = parsed
        except Exception:
            pass

        # 3) Save to session file atomically
        return _merge_session_data(self.session_path, cookies, ls)

    def harvest_cookies(self) -> int:
        """Legacy: only cookies. Use harvest_state() instead."""
        return self.harvest_state()

    def screenshot(self) -> bytes:
        if not self.cdp:
            raise RuntimeError("پازل باز نیست")
        with self.lock:
            r = self.cdp.call("Page.captureScreenshot",
                              {"format": "jpeg", "quality": 72})
        raw = r.get("data") or ""
        import base64
        self.last_jpeg = base64.b64decode(raw)
        return self.last_jpeg

    def click(self, nx: float, ny: float) -> None:
        if not self.cdp:
            raise RuntimeError("پازل باز نیست")
        nx = min(max(float(nx), 0.0), 1.0)
        ny = min(max(float(ny), 0.0), 1.0)
        with self.lock:
            met = self.cdp.call("Page.getLayoutMetrics")
            box = (met.get("cssVisualViewport")
                   or met.get("layoutViewport") or {})
            w = float(box.get("clientWidth") or 900)
            h = float(box.get("clientHeight") or 700)
            x, y = nx * w, ny * h
            for typ in ("mousePressed", "mouseReleased"):
                self.cdp.call("Input.dispatchMouseEvent", {
                    "type": typ, "x": x, "y": y,
                    "button": "left", "clickCount": 1})

    def type_text(self, text: str) -> None:
        if not self.cdp:
            raise RuntimeError("پازل باز نیست")
        with self.lock:
            if text == "\n" or text == "Enter":
                self.cdp.call("Input.dispatchKeyEvent",
                              {"type": "keyDown", "key": "Enter", "code": "Enter",
                               "windowsVirtualKeyCode": 13})
                self.cdp.call("Input.dispatchKeyEvent",
                              {"type": "keyUp", "key": "Enter", "code": "Enter",
                               "windowsVirtualKeyCode": 13})
                return
            for ch in str(text)[:80]:
                self.cdp.call("Input.dispatchKeyEvent",
                              {"type": "keyDown", "text": ch})
                self.cdp.call("Input.dispatchKeyEvent",
                              {"type": "keyUp", "text": ch})

    def stop(self) -> None:
        _sv_log("info", _LOG_TAG_SESSION, "PuzzleLive.stop() — ذخیره و بستن")
        # اول state را ذخیره کن، بعد ببند
        try:
            n = self.harvest_state()
            if n:
                _sv_log("info", _LOG_TAG_SESSION, f"{n} آیتم state ذخیره شد")
        except Exception as e:
            _sv_log("warning", _LOG_TAG_SESSION, f"خطا در ذخیره state: {e}")
        try:
            if self.cdp:
                self.cdp.close()
        except Exception:
            pass
        self.cdp = None
        _kill_proc(self.proc)
        self.proc = None
        if self.profile and "puzzle-live-" in Path(self.profile).name:
            self._wipe_profile()
        self.profile = None

    def _wipe_profile(self) -> None:
        """فقط پوشهٔ موقت puzzle-live-* را پاک می‌کند — session.json اکانت نمی‌رود."""
        p = self.profile
        self.profile = None
        if not p:
            return
        try:
            if "puzzle-live-" not in Path(p).name:
                return
        except Exception:
            return
        import shutil
        time.sleep(0.15)
        try:
            shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass


def launch_account_browser(session_path: str, name: str = "") -> Tuple[bool, str]:
    """از پنل صدا زده می‌شود — فرآیند جدا تا GUI گیر نکند.

    این تابع یک فرآیند جداگانه راه می‌اندازد که مرورگر را با سشن همان
    اکانت باز می‌کند. برای نمایش پازل/کپچا به اپراتور استفاده می‌شود.
    """
    _sv_log("info", _LOG_TAG_CAPTCHA, f"launch_account_browser({session_path}, {name})")
    session_path = str(session_path)
    if not Path(session_path).exists():
        return False, "سشن این اکانت پیدا نشد"
    if not cookies_from_session(session_path):
        return False, "سشن این اکانت خالی است — دوباره لاگین کنید"
    if not find_browser():
        return False, "Edge یا Chrome روی این رایانه پیدا نشد — پازل همین اکانت به آن نیاز دارد"
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--session-view", session_path]
    else:
        cmd = [sys.executable, "-m", "marketing_divar.session_view", session_path]
    kw: Dict[str, Any] = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kw["creationflags"] = (
            int(getattr(subprocess, "DETACHED_PROCESS", 0))
            | int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)))
    else:
        kw["start_new_session"] = True
    try:
        subprocess.Popen(cmd, **kw)
    except Exception as e:
        return False, f"نتوانست پنجره را باز کند: {e}"
    who = name or Path(session_path).parent.name
    return True, f"پنجرهٔ دیوار با اکانت «{who}» باز شد — پازل را همان‌جا حل کنید"


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: session_view SESSION.json")
        return 2
    try:
        print(run_logged_in_browser(args[0]))
        return 0
    except Exception as e:
        print(f"session_view failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())