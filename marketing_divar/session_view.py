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
from urllib.request import urlopen


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


def find_browser() -> Optional[str]:
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
        ]
    else:
        cands += ["microsoft-edge", "msedge", "google-chrome", "chromium",
                  "chromium-browser"]
    for c in cands:
        if not c:
            continue
        if os.path.isfile(c):
            return c
        from shutil import which
        w = which(c)
        if w:
            return w
    return None


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


def _wait_cdp(port: int, tries: int = 40) -> str:
    url = f"http://127.0.0.1:{port}/json/version"
    last = ""
    for _ in range(tries):
        try:
            with urlopen(url, timeout=1.0) as r:
                data = json.loads(r.read().decode())
            ws = data.get("webSocketDebuggerUrl") or ""
            if ws:
                return ws
        except Exception as e:
            last = str(e)
        time.sleep(0.25)
    raise RuntimeError(f"browser CDP not ready: {last}")


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
    ws = _wait_cdp(port)
    _cdp_set_cookies(ws, cookies, start_url)
    return f"opened {browser} as session {Path(session_path).parent.name}"


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
