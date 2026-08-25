# -*- coding: utf-8 -*-
"""باز کردن دیوار با سشن همان اکانت برنامه (نه تب مهمان).

دیوار داخل iframe پنل باز نمی‌شود (refused to connect). تب معمولی هم
با اکانت برنامه لاگین نیست. این ماژول Edge/Chrome را با پروفایل همان
اکانت باز می‌کند و کوکی/توکن ذخیره‌شده را تزریق می‌کند تا پازل واقعی
همان حساب دیده شود.
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


def persistent_profile_dir(session_path: str) -> Path:
    """یک پروفایل مرورگر دائمی کنار session.json همین اکانت — پاک نمی‌شود."""
    return Path(session_path).resolve().parent / "browser-profile"


def merge_session_cookies(session_path: str, cookies: List[Dict[str, Any]]) -> int:
    """کوکی‌های حل‌شدهٔ دیوار را از مرورگر به session.json برمی‌گرداند."""
    from .auth_session import merge_into_session_file
    p = Path(session_path)
    data: Dict[str, Any] = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}
    full: List[Dict[str, Any]] = []
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
        full.append({
            "name": name, "value": str(val),
            "domain": domain or ".divar.ir",
            "path": ck.get("path") or "/",
            "secure": True,
            "httpOnly": bool(ck.get("httpOnly", True)),
        })
        n += 1
    merge_into_session_file(
        session_path,
        str(data.get("phone") or ""),
        str(data.get("token") or ""),
        {"cookies_full": full},
    )
    return n


def _cleanup_old_temp_profiles(session_path: str) -> None:
    parent = Path(session_path).resolve().parent
    import shutil
    try:
        for p in parent.glob("puzzle-live-*"):
            shutil.rmtree(p, ignore_errors=True)
    except Exception:
        pass


def cookies_from_session(session_path: str) -> List[Dict[str, Any]]:
    """کوکی‌هایی که باید روی divar.ir و api.divar.ir ست شوند تا سایت لاگین باشد."""
    from .auth_session import cookies_for_browser
    return cookies_for_browser(session_path)


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


def _cdp_set_cookies(ws_url: str, cookies: List[Dict[str, Any]],
                     start_url: str, session_path: str = "") -> None:
    sock = _ws_connect(ws_url)
    try:
        i = 1
        _ws_send(sock, json.dumps({"id": i, "method": "Network.enable"}))
        i += 1
        _ws_send(sock, json.dumps({"id": i, "method": "Page.enable"}))
        from .auth_session import cdp_cookie_params, localstorage_script
        if session_path:
            i += 1
            _ws_send(sock, json.dumps({
                "id": i, "method": "Page.addScriptToEvaluateOnNewDocument",
                "params": {"source": localstorage_script(session_path)}}))
        for ck in cookies:
            for params in cdp_cookie_params(ck):
                i += 1
                _ws_send(sock, json.dumps({"id": i, "method": "Network.setCookie",
                                           "params": params}))
        i += 1
        _ws_send(sock, json.dumps({
            "id": i, "method": "Page.navigate",
            "params": {"url": start_url}}))
        time.sleep(0.4)
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _http_get_local(port: int, path: str, timeout: float = 1.8) -> str:
    """GET روی 127.0.0.1 — هرگز از پروکسی سیستم استفاده نمی‌کند.

    urlopen در ویندوز اگر HTTP_PROXY ست باشد به 127.0.0.1 هم از پروکسی
    می‌رود و با «timed out» می‌میرد (خطای زندهٔ پازل).
    """
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
            while True:
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    break
                if not chunk:
                    break
                buf += chunk
                if b"\r\n\r\n" in buf or len(buf) > 2_000_000:
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
    """Edge/Chrome را با کوکی همان اکانت باز می‌کند. فرآیند همین‌جا می‌ماند تا مرورگر بالا بیاید."""
    browser = find_browser()
    if not browser:
        raise RuntimeError("Edge/Chrome پیدا نشد — برای پازل همان اکانت لازم است")
    cookies = cookies_from_session(session_path)
    if not cookies:
        raise RuntimeError("سشن این اکانت خالی است — دوباره لاگین کنید")
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
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws = _wait_cdp(port, tries=100, profile=profile, proc=proc)
    _cdp_set_cookies(ws, cookies, start_url, session_path)
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
        _ws_send(sock, "")  # ignore empty; ping handled loosely
        return None
    if opcode in (0x8, 0xA):
        return None
    if opcode != 0x1:
        return None
    return data.decode("utf-8", errors="replace")


class CdpClient:
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


class PuzzleLive:
    """سشن دیوار همین اکانت — تصویر داخل پاپ‌آپ پنل، بدون iframe."""

    def __init__(self) -> None:
        self.proc: Optional[subprocess.Popen] = None
        self.cdp: Optional[CdpClient] = None
        self.profile: Optional[Path] = None
        self.session_path: str = ""
        self.last_jpeg = b""
        self.last_err = ""
        self.lock = __import__("threading").Lock()

    def start(self, session_path: str, start_url: str = "https://divar.ir") -> None:
        browsers = find_browsers()
        if not browsers:
            raise RuntimeError("Edge یا Chrome روی این رایانه پیدا نشد")
        cookies = cookies_from_session(session_path)
        if not cookies:
            raise RuntimeError("سشن این اکانت خالی است — دوباره لاگین کنید")
        self.session_path = session_path
        _cleanup_old_temp_profiles(session_path)
        # همان پروفایل دائمی اکانت — نه پوشهٔ موقت puzzle-live.
        # کوکی حل‌شده اینجا می‌ماند و بعد به session.json برمی‌گردد.
        profile = persistent_profile_dir(session_path)
        profile.mkdir(parents=True, exist_ok=True)
        self.profile = profile
        _clear_stale_locks(profile)
        last = ""
        for browser in browsers:
            # پورت ۰: خود Edge/Chrome پورت واقعی را در DevToolsActivePort می‌نویسد.
            # پورت ازپیش‌گرفته‌شده در ویندوز اغلب نادیده گرفته می‌شد → پاسخ خالی CDP.
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
                self._inject_login_then_open(cookies, start_url)
                self._wait_ready()
                self._nudge_window()
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

    def _inject_login_then_open(self, cookies: List[Dict[str, Any]],
                                start_url: str) -> None:
        """اول کوکی/localStorage، بعد Navigate — تا دیوار از اول لاگین باشد."""
        from .auth_session import cdp_cookie_params, localstorage_script
        if not self.cdp:
            return
        self.cdp.call("Network.enable")
        self.cdp.call("Page.enable")
        try:
            self.cdp.call("Runtime.enable")
        except Exception:
            pass
        try:
            self.cdp.call("Page.addScriptToEvaluateOnNewDocument", {
                "source": localstorage_script(self.session_path),
            })
        except Exception:
            pass
        for ck in cookies:
            for params in cdp_cookie_params(ck):
                try:
                    self.cdp.call("Network.setCookie", params)
                except Exception:
                    try:
                        self.cdp.call("Network.setCookie", {
                            "name": params["name"], "value": params["value"],
                            "url": params.get("url") or "https://divar.ir/",
                            "path": "/", "secure": True,
                        })
                    except Exception:
                        pass
        self.cdp.call("Page.navigate", {"url": start_url}, timeout=20)

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

    def harvest_cookies(self) -> int:
        """کوکی دیوار همین پروفایل را به session.json برمی‌گرداند."""
        if not self.cdp or not self.session_path:
            return 0
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
        return merge_session_cookies(self.session_path, cookies)

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
        try:
            self.harvest_cookies()
        except Exception:
            pass
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
    """از پنل صدا زده می‌شود — فرآیند جدا تا GUI گیر نکند."""
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
