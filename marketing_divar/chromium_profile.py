# -*- coding: utf-8 -*-
"""پروفایل پایدار Chromium برای هر اکانت دیوار.

پنجره با خودِ chrome.exe اختصاصی باز می‌شود (نه Playwright thread، نه Edge).
سشن تزریق نمی‌شود. user-data-dir همان accounts/<name>/chromium/ است.
صفحهٔ اول همیشه https://divar.ir/s/tehran است.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

HOME_URL = "https://divar.ir/s/tehran"
META_NAME = "account.json"
CHROMIUM_DIR = "chromium"

_LIVE: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()

_LOGIN_COOKIE_HINTS = (
    "sRefreshToken", "sAccessToken", "sFrontToken",
    "st-refresh-token", "st-access-token", "front-token",
)


def _clog(stage: str, msg: str, level: str = "info") -> None:
    try:
        from . import logging_util
        logging_util.log(level, "[chromium:%s] %s" % (stage, msg))
    except Exception:
        print("[chromium:%s] %s" % (stage, msg), flush=True)


def safe_name(raw: str) -> str:
    t = str(raw or "").strip()
    t = re.sub(r'[<>:"/\\|?*]', "-", t)
    t = re.sub(r"\s+", "-", t)
    t = t.strip(".-")
    if not t:
        raise ValueError("نام اکانت خالی است")
    return t[:80]


def account_dir(accounts_dir: str, name: str) -> Path:
    return Path(accounts_dir) / safe_name(name)


def chromium_dir(accounts_dir: str, name: str) -> Path:
    return account_dir(accounts_dir, name) / CHROMIUM_DIR


def meta_path(accounts_dir: str, name: str) -> Path:
    return account_dir(accounts_dir, name) / META_NAME


def load_meta(accounts_dir: str, name: str) -> Dict[str, Any]:
    p = meta_path(accounts_dir, name)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_meta(accounts_dir: str, name: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    name = safe_name(name)
    d = account_dir(accounts_dir, name)
    d.mkdir(parents=True, exist_ok=True)
    rec = load_meta(accounts_dir, name)
    rec.update(extra or {})
    rec["name"] = name
    rec["home_url"] = HOME_URL
    rec["chromium_dir"] = str(chromium_dir(accounts_dir, name))
    rec["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    meta_path(accounts_dir, name).write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return rec


def profile_ready(accounts_dir: str, name: str) -> bool:
    rec = load_meta(accounts_dir, name)
    if rec.get("profile_ready"):
        return True
    return False


def cookies_look_logged_in(cookies: List[Dict[str, Any]]) -> bool:
    names = set()
    for c in cookies or []:
        if not isinstance(c, dict):
            continue
        domain = str(c.get("domain") or "")
        if domain and "divar.ir" not in domain.lower():
            continue
        names.add(str(c.get("name") or ""))
    return any(n in names for n in _LOGIN_COOKIE_HINTS)


def launch_kwargs(user_data: Path, headless: bool = False) -> Dict[str, Any]:
    """همیشه Chromium اختصاصی برنامه — نه Chrome/Edge کاربر."""
    from .app_chromium import apply_browser_env, executable_path
    apply_browser_env()
    user_data.mkdir(parents=True, exist_ok=True)
    exe = executable_path()
    return {
        "user_data_dir": str(user_data),
        "executable_path": exe,
        "headless": bool(headless),
        "viewport": {"width": 1100, "height": 800},
        "locale": "fa-IR",
        "timezone_id": "Asia/Tehran",
        "ignore_https_errors": False,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--noerrdialogs",
        ],
        "ignore_default_args": ["--enable-automation"],
    }


def _clear_locks(profile: Path) -> None:
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie",
                 "lockfile"):
        p = profile / name
        try:
            if p.exists() or p.is_symlink():
                p.unlink()
        except Exception:
            pass


def close_live(name: str) -> None:
    name = safe_name(name)
    with _LOCK:
        live = _LIVE.pop(name, None)
    if not live:
        return
    proc = live.get("proc")
    if proc is not None:
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=8)
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except Exception:
                    proc.kill()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    stop = live.get("stop")
    try:
        if stop is not None:
            stop.set()
    except Exception:
        pass
    for key in ("context", "pw"):
        obj = live.get(key)
        try:
            if obj is None:
                continue
            if key == "context":
                obj.close()
            else:
                obj.stop()
        except Exception:
            pass


def is_open(name: str) -> bool:
    try:
        name = safe_name(name)
    except ValueError:
        return False
    with _LOCK:
        live = _LIVE.get(name)
        proc = live.get("proc") if live else None
    if proc is not None:
        try:
            if proc.poll() is None:
                return True
        except Exception:
            pass
        with _LOCK:
            cur = _LIVE.get(name)
            if cur and cur.get("proc") is proc:
                _LIVE.pop(name, None)
        return False
    with _LOCK:
        return name in _LIVE


def _spawn_chromium(exe: str, profile: Path, url: str) -> subprocess.Popen:
    profile.mkdir(parents=True, exist_ok=True)
    _clear_locks(profile)
    err = profile / "browser.err"
    err_f = open(err, "ab")
    cmd = [
        exe,
        "--user-data-dir=" + str(profile),
        "--remote-debugging-port=0",
        "--remote-debugging-address=127.0.0.1",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--disable-features=Translate",
        "--new-window",
        url or HOME_URL,
    ]
    kw: Dict[str, Any] = {"stdout": subprocess.DEVNULL, "stderr": err_f}
    if sys.platform == "win32":
        kw["creationflags"] = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    return subprocess.Popen(cmd, **kw)


def open_profile(accounts_dir: str, name: str, url: str = HOME_URL) -> Dict[str, Any]:
    """Chromium همان اکانت را باز می‌کند — صفحهٔ تهران."""
    from .app_chromium import apply_browser_env, ensure_installed, is_ready
    name = safe_name(name)
    apply_browser_env()
    _clog("open", "start name=%s" % name)
    if not is_ready():
        _clog("open", "chromium not registered — downloading", "warning")
        try:
            ensure_installed()
        except Exception as e:
            _clog("open", "download failed: %s" % e, "error")
            raise RuntimeError(
                "Chromium اختصاصی نصب نشد (مرحله دانلود/ثبت). Edge باز نمی‌شود. %s" % e
            ) from e
    if not is_ready():
        raise RuntimeError("Chromium دانلود شد ولی ثبت/نصب نشد — Installed نیست")
    from .app_chromium import executable_path
    try:
        exe = executable_path()
    except Exception as e:
        _clog("open", "executable: %s" % e, "error")
        raise RuntimeError("مرحله executable: %s" % e) from e
    close_live(name)
    prof = chromium_dir(accounts_dir, name)
    prof.mkdir(parents=True, exist_ok=True)
    save_meta(accounts_dir, name, {
        "status": "opening", "last_url": url or HOME_URL, "exe": exe,
        "last_error": "",
    })
    try:
        proc = _spawn_chromium(exe, prof, url or HOME_URL)
    except Exception as e:
        _clog("open", "spawn failed: %s" % e, "error")
        save_meta(accounts_dir, name, {"status": "error", "last_error": str(e)})
        raise RuntimeError("مرحله launch: Chromium اجرا نشد — %s" % e) from e
    time.sleep(0.6)
    if proc.poll() is not None:
        hint = ""
        try:
            hint = (prof / "browser.err").read_text(encoding="utf-8", errors="replace")[-240:]
        except Exception:
            pass
        msg = "Chromium بلافاصله بسته شد (exit %s)%s" % (
            proc.returncode, (": " + hint if hint else ""))
        _clog("open", msg, "error")
        save_meta(accounts_dir, name, {"status": "error", "last_error": msg})
        raise RuntimeError("مرحله launch: " + msg)
    with _LOCK:
        _LIVE[name] = {"proc": proc, "exe": exe, "profile": str(prof),
                       "url": url or HOME_URL, "opened_at": time.time()}
    save_meta(accounts_dir, name, {"status": "open", "last_error": ""})
    _clog("open", "ok exe=%s profile=%s" % (exe, prof))
    return {"ok": True, "name": name, "url": url or HOME_URL, "exe": exe,
            "message": "Chromium اختصاصی باز شد — اگر لازم است در همان پنجره لاگین کنید"}


def _cookies_from_cdp(profile: Path, proc: Optional[subprocess.Popen]) -> List[Dict[str, Any]]:
    from .session_view import CdpClient, _wait_cdp
    ws = _wait_cdp(0, tries=40, profile=profile, proc=proc)
    cdp = CdpClient(ws)
    try:
        cdp.call("Network.enable")
        try:
            r = cdp.call("Network.getCookies", {
                "urls": ["https://divar.ir", "https://api.divar.ir",
                         "https://www.divar.ir"],
            }, timeout=6)
            return list(r.get("cookies") or [])
        except Exception:
            r = cdp.call("Network.getAllCookies", timeout=6)
            return list(r.get("cookies") or [])
    finally:
        try:
            cdp.close()
        except Exception:
            pass


def _cookies_from_live(name: str) -> List[Dict[str, Any]]:
    with _LOCK:
        live = _LIVE.get(name) or {}
        ctx = live.get("context")
        proc = live.get("proc")
        profile = live.get("profile")
    if ctx is not None:
        try:
            return list(ctx.cookies())
        except Exception as e:
            _clog("cookies", "playwright cookies failed: %s" % e, "warning")
    if profile:
        try:
            return _cookies_from_cdp(Path(profile), proc)
        except Exception as e:
            _clog("cookies", "cdp failed: %s" % e, "warning")
            return []
    return []


def harvest_to_session(accounts_dir: str, name: str,
                       cookies: List[Dict[str, Any]]) -> None:
    """کوکی‌های پروفایل را کنار JWT اکانت می‌گذارد (شماره‌گیری API جداست)."""
    from .auth_session import merge_into_session_file
    d = account_dir(accounts_dir, name)
    session = d / "session.json"
    token = ""
    if session.exists():
        try:
            token = str(json.loads(session.read_text(encoding="utf-8")).get("token") or "")
        except Exception:
            token = ""
    full = []
    phone = load_meta(accounts_dir, name).get("phone") or ""
    for c in cookies or []:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        domain = str(c.get("domain") or "")
        if domain and "divar.ir" not in domain.lower():
            continue
        full.append({
            "name": c.get("name"), "value": c.get("value"),
            "domain": domain or ".divar.ir",
            "path": c.get("path") or "/",
            "httpOnly": bool(c.get("httpOnly", False)),
            "secure": True,
        })
        if str(c.get("name")) in ("token", "sAccessToken") and not token:
            val = str(c.get("value") or "")
            if val.count(".") >= 2:
                token = val
    merge_into_session_file(str(session), str(phone), token, {"cookies_full": full})


def save_profile(accounts_dir: str, name: str) -> Dict[str, Any]:
    """بعد از لاگین کاربر: کوکی همان پنجرهٔ باز را می‌خواند و می‌بندد."""
    name = safe_name(name)
    used_live = is_open(name)
    _clog("save", "start name=%s window_open=%s" % (name, used_live))
    if not used_live:
        rec = save_meta(accounts_dir, name, {
            "profile_ready": False,
            "status": "login_required",
            "last_error": "window_not_open",
        })
        _clog("save", "window not open — refuse throwaway launch", "warning")
        return {"ok": False, "ready": False, **rec,
                "stage": "window",
                "message": "پنجره Chromium این اکانت باز نیست. اول «باز کردن دیوار» را بزنید، لاگین کنید، بعد ذخیره."}
    cookies = _cookies_from_live(name)
    ok = cookies_look_logged_in(cookies)
    harvest_to_session(accounts_dir, name, cookies)
    rec = save_meta(accounts_dir, name, {
        "profile_ready": bool(ok),
        "status": "ready" if ok else "login_required",
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S") if ok else "",
        "cookie_count": len(cookies or []),
        "from_open_window": used_live,
        "last_error": "" if ok else "login_not_detected",
    })
    if not ok:
        _clog("save", "login not detected cookie_count=%s" % len(cookies or []), "warning")
        return {"ok": False, "ready": False, **rec, "stage": "login",
                "message": "لاگین دیوار در این پروفایل دیده نشد. در همان پنجره Chromium وارد شوید، بعد ذخیره را بزنید. پنجره بسته نشد."}
    close_live(name)
    rec = save_meta(accounts_dir, name, {
        "status": "ready", "closed_after_save": True, "last_error": "",
    })
    _clog("save", "ok closed window")
    return {"ok": True, "ready": True, **rec, "stage": "saved",
            "message": "پروفایل ذخیره شد و پنجره بسته شد. «باز کردن دیوار» همان حساب لاگین‌شده را می‌آورد."}


def create_and_open(accounts_dir: str, name: str, phone: str = "") -> Dict[str, Any]:
    name = safe_name(name)
    chromium_dir(accounts_dir, name).mkdir(parents=True, exist_ok=True)
    save_meta(accounts_dir, name, {
        "profile_ready": False,
        "status": "created",
        "phone": phone or "",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_error": "",
    })
    opened = open_profile(accounts_dir, name, HOME_URL)
    opened["message"] = (
        "پروفایل ساخته شد و Chromium روی تهران باز است. "
        "در همان پنجره لاگین کنید، بعد «ذخیره پروفایل» را بزنید."
    )
    return opened


def update_profile(accounts_dir: str, name: str) -> Dict[str, Any]:
    name = safe_name(name)
    if not is_open(name):
        open_profile(accounts_dir, name, HOME_URL)
        return {"ok": True, "running": True, "stage": "opened",
                "message": "پنجره باز شد. لاگین را تازه کنید، بعد دوباره ذخیره پروفایل را بزنید."}
    return save_profile(accounts_dir, name)


def delete_profile(accounts_dir: str, name: str) -> Dict[str, Any]:
    import shutil
    name = safe_name(name)
    close_live(name)
    d = account_dir(accounts_dir, name)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    return {"ok": True, "message": f"پروفایل «{name}» حذف شد"}


def snapshot_fields(accounts_dir: str, name: str) -> Dict[str, Any]:
    rec = load_meta(accounts_dir, name)
    ready = bool(rec.get("profile_ready"))
    return {
        "profile_ready": ready,
        "profile_status": rec.get("status") or ("ready" if ready else "none"),
        "profile_saved_at": rec.get("saved_at") or "",
        "profile_open": is_open(name) if rec else False,
        "phone": rec.get("phone") or "",
        "home_url": HOME_URL,
        "last_error": rec.get("last_error") or "",
    }
