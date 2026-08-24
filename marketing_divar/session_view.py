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


def cookies_from_session(session_path: str) -> List[Dict[str, Any]]:
    """کوکی‌هایی که باید روی divar.ir ست شوند تا همان لاگین برنامه باشد."""
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
                     start_url: str) -> None:
    sock = _ws_connect(ws_url)
    try:
        i = 1
        _ws_send(sock, json.dumps({"id": i, "method": "Network.enable"}))
        for ck in cookies:
            i += 1
            params = {"name": ck["name"], "value": ck["value"],
                      "domain": ck.get("domain") or ".divar.ir",
                      "path": ck.get("path") or "/",
                      "secure": True, "httpOnly": ck["name"] != "sFrontToken"}
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


def _http_get_local(port: int, path: str, timeout: float = 1.2) -> str:
    """GET روی 127.0.0.1 — هرگز از پروکسی سیستم استفاده نمی‌کند.

    urlopen در ویندوز اگر HTTP_PROXY ست باشد به 127.0.0.1 هم از پروکسی
    می‌رود و با «timed out» می‌میرد (خطای زندهٔ پازل).
    """
    sock = socket.create_connection(("127.0.0.1", int(port)), timeout=timeout)
    try:
        req = (f"GET {path} HTTP/1.1\r\n"
               f"Host: 127.0.0.1:{int(port)}\r\n"
               "Connection: close\r\n\r\n")
        sock.sendall(req.encode("ascii"))
        sock.settimeout(timeout)
        buf = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
            if len(buf) > 2_000_000:
                break
    finally:
        try:
            sock.close()
        except Exception:
            pass
    if b"\r\n\r\n" not in buf:
        raise RuntimeError("پاسخ خالی از CDP")
    head, body = buf.split(b"\r\n\r\n", 1)
    status = head.split(b"\r\n", 1)[0]
    if b"200" not in status:
        raise RuntimeError(status.decode("ascii", errors="replace")[:80])
    return body.decode("utf-8", errors="replace")


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


def _wait_cdp(port: int, tries: int = 80, profile: Optional[Path] = None) -> str:
    last = ""
    use_port = int(port)
    for _ in range(tries):
        if profile:
            file_port = _devtools_port_file(profile)
            if file_port:
                use_port = file_port
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
        f"--user-data-dir={profile}",
        f"--remote-debugging-port={port}",
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
    profile = Path(session_path).resolve().parent / "edge-profile"
    profile.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    cmd = [
        browser,
        f"--user-data-dir={profile}",
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        f"--app={start_url}",
    ]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws = _wait_cdp(port, profile=profile)
    _cdp_set_cookies(ws, cookies, start_url)
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
        # پروفایل جدا — اگر Edge قبلی همان edge-profile را گرفته باشد
        # --remote-debugging-port نادیده گرفته می‌شود و CDP timeout می‌شود.
        stamp = str(os.getpid()) + "-" + str(int(time.time()))
        profile = Path(session_path).resolve().parent / f"puzzle-live-{stamp}"
        profile.mkdir(parents=True, exist_ok=True)
        self.profile = profile
        last = ""
        for browser in browsers:
            port = _free_port()
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
                ws = _wait_cdp(port, tries=90, profile=profile)
            except Exception as e:
                last = str(e)
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
                for ck in cookies:
                    self.cdp.call("Network.setCookie", {
                        "name": ck["name"], "value": ck["value"],
                        "domain": ck.get("domain") or ".divar.ir",
                        "path": ck.get("path") or "/",
                        "secure": True,
                        "httpOnly": ck["name"] != "sFrontToken",
                    })
                self.cdp.call("Page.navigate", {"url": start_url}, timeout=20)
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
            if self.cdp:
                self.cdp.close()
        except Exception:
            pass
        self.cdp = None
        _kill_proc(self.proc)
        self.proc = None
        self._wipe_profile()

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
