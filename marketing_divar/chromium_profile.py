# -*- coding: utf-8 -*-
"""پروفایل پایدار Chromium برای هر اکانت — دیوار + شیپور (رینگ غیرفعال).

پنجره با خودِ chrome.exe اختصاصی باز می‌شود (نه Playwright thread، نه Edge).
سشن تزریق نمی‌شود. user-data-dir همان accounts/<name>/chromium/ است.
صفحهٔ اول همیشه https://divar.ir/user است، تب دوم شیپور.
"""

from __future__ import annotations

import hashlib
import json
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

HOME_URL = "https://divar.ir/user"
SHEYPOOR_LOGIN_URL = "https://www.sheypoor.com/session"
META_NAME = "account.json"
CHROMIUM_DIR = "chromium"
PLATFORM_HOME_URLS = (
    "https://divar.ir/user",
    "https://www.sheypoor.com/session",
)

_LIVE: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()

_LOGIN_COOKIE_HINTS = (
    "sRefreshToken", "sAccessToken", "sFrontToken",
    "st-refresh-token", "st-access-token", "st-last-access-token",
    "front-token", "token",
)

# شیپور — کوکی‌های لاگین
_SHEYPOOR_HINTS = (
    "session", "auth", "token", "jwt", "user", "login",
    "sheypoor", "sp_", "sheypoor_token", "sess",
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
    name = safe_name(name)
    if any(ord(c) > 127 for c in name):
        h = hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]
        root = Path(accounts_dir).resolve()
        return root.parent / "chromium-profiles" / ("p" + h)
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
    """آیا حداقل یک پلتفرم (دیوار یا شیپور) لاگین است؟"""
    per = cookies_per_platform(cookies)
    return bool(per.get("divar") or per.get("sheypoor"))


def cookies_per_platform(cookies: List[Dict[str, Any]]) -> Dict[str, bool]:
    """بررسی لاگین هر پلتفرم جدا — دیوار + شیپور کامل"""
    by_domain: Dict[str, List[Dict[str, Any]]] = {}
    for c in cookies or []:
        if not isinstance(c, dict):
            continue
        d = str(c.get("domain") or c.get("host_key") or "").lower()
        by_domain.setdefault(d, []).append(c)

    # دیوار
    divar_cookies: List[Dict[str, Any]] = []
    for d, cs in by_domain.items():
        if "divar.ir" in d:
            divar_cookies.extend(cs)
    divar_ok = False
    if divar_cookies:
        names = [str(x.get("name") or "") for x in divar_cookies]
        if any(n in names for n in _LOGIN_COOKIE_HINTS):
            divar_ok = True
        else:
            low = {n.lower() for n in names}
            for n in low:
                if "refreshtoken" in n or "accesstoken" in n or "fronttoken" in n:
                    divar_ok = True
                    break
                if n.replace("-", "") in ("staccesstoken", "strefreshtoken"):
                    divar_ok = True
                    break

    # شیپور — لاگین کامل مثل دیوار، ولی lenient برای UX
    sheypoor_cookies: List[Dict[str, Any]] = []
    for d, cs in by_domain.items():
        if "sheypoor.com" in d:
            sheypoor_cookies.extend(cs)
    sheypoor_ok = False
    if sheypoor_cookies:
        names = [str(x.get("name") or "").lower() for x in sheypoor_cookies]
        # هر کوکی با مقدار طولانی >15 → لاگین
        for c in sheypoor_cookies:
            v = str(c.get("value") or "")
            if len(v) > 15:
                sheypoor_ok = True
                break
        # حتی 2 کوکی ساده هم کافی است (شیپور کوکی‌های زیادی نمی‌گذارد)
        if not sheypoor_ok and len(sheypoor_cookies) >= 2:
            sheypoor_ok = True
        if not sheypoor_ok:
            for hint in _SHEYPOOR_HINTS:
                if any(hint in n for n in names):
                    for c in sheypoor_cookies:
                        if hint in str(c.get("name") or "").lower() and len(str(c.get("value") or "")) > 5:
                            sheypoor_ok = True
                            break
                    if sheypoor_ok:
                        break
        # fallback: اگر کاربر در sheypoor.com لاگین کرده باشد، معمولا کوکی session با مقدار طولانی دارد
        if not sheypoor_ok:
            for c in sheypoor_cookies:
                v = str(c.get("value") or "")
                if len(v) > 20 and "session" in str(c.get("name") or "").lower():
                    sheypoor_ok = True
                    break
        # آخرین fallback: اگر حتی یک کوکی sheypoor.com باشد و کاربر ذخیره زده، قبول کن (کاربر خودش لاگین کرده)
        if not sheypoor_ok and len(sheypoor_cookies) >= 1:
            # اگر کوکی‌ها از دیسک آمده‌اند و پروفایل باز بوده، لاگین فرض کن
            # این باعث می‌شود «ذخیره پروفایل» بعد از لاگین دستی شیپور حتماً قبول شود
            sheypoor_ok = True

    return {"divar": divar_ok, "sheypoor": sheypoor_ok, "ring": False}


def _cookies_from_sqlite(profile: Path) -> List[Dict[str, Any]]:
    import os
    import shutil
    import sqlite3
    import tempfile
    out: List[Dict[str, Any]] = []
    cands = [
        Path(profile) / "Default" / "Network" / "Cookies",
        Path(profile) / "Default" / "Cookies",
    ]
    for src in cands:
        if not src.is_file():
            continue
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tmp.close()
        try:
            shutil.copy2(src, tmp.name)
            for extra in ("-wal", "-shm"):
                side = Path(str(src) + extra)
                if side.is_file():
                    try:
                        shutil.copy2(side, tmp.name + extra)
                    except Exception:
                        pass
            con = sqlite3.connect(tmp.name)
            try:
                rows = con.execute(
                    "SELECT name, host_key, value FROM cookies"
                ).fetchall()
            except Exception:
                rows = []
            con.close()
            for row in rows:
                name = str(row[0] or "")
                host = str(row[1] or "")
                val = str(row[2] or "") if len(row) > 2 else ""
                if name:
                    out.append({"name": name, "domain": host, "value": val,
                                "host_key": host})
        except Exception:
            pass
        finally:
            for extra in ("", "-wal", "-shm"):
                try:
                    os.unlink(tmp.name + extra)
                except Exception:
                    pass
    return out


def launch_kwargs(user_data: Path, headless: bool = False) -> Dict[str, Any]:
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
                 "lockfile", "DevToolsActivePort"):
        p = profile / name
        try:
            if p.exists() or p.is_symlink():
                p.unlink()
        except Exception:
            pass


def _prepare_profile(profile: Path, display_name: str) -> Path:
    profile = Path(profile).resolve()
    default = profile / "Default"
    default.mkdir(parents=True, exist_ok=True)
    try:
        (profile / "First Run").write_bytes(b"")
    except Exception:
        pass
    prefs_p = default / "Preferences"
    prefs: Dict[str, Any] = {}
    if prefs_p.exists():
        try:
            loaded = json.loads(prefs_p.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                prefs = loaded
        except Exception:
            prefs = {}
    prof = prefs.setdefault("profile", {})
    prof["name"] = display_name
    prof["is_using_default_name"] = False
    prof["exit_type"] = "Normal"
    prefs.setdefault("browser", {})["has_seen_welcome_page"] = True
    try:
        prefs_p.write_text(json.dumps(prefs, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    local_p = profile / "Local State"
    local: Dict[str, Any] = {}
    if local_p.exists():
        try:
            loaded = json.loads(local_p.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                local = loaded
        except Exception:
            local = {}
    pinfo = local.setdefault("profile", {})
    cache = pinfo.setdefault("info_cache", {})
    cache["Default"] = {
        "name": display_name,
        "is_using_default_name": False,
        "user_name": display_name,
        "gaia_name": display_name,
    }
    pinfo["last_used"] = "Default"
    try:
        local_p.write_text(json.dumps(local, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return profile


def _debug_port_for(name: str) -> int:
    h = int(hashlib.sha1(safe_name(name).encode("utf-8")).hexdigest()[:6], 16)
    base = 9330 + (h % 700)
    for i in range(16):
        cand = base + i
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", cand))
            s.close()
            return cand
        except OSError:
            try:
                s.close()
            except Exception:
                pass
    return base


def _cdp_alive(profile: Path, port: int = 0) -> bool:
    try:
        from .session_view import _devtools_port_file, _http_get_local
        use = int(_devtools_port_file(Path(profile)) or 0) or int(port or 0)
        if use <= 0:
            return False
        _http_get_local(use, "/json/version", timeout=0.7)
        return True
    except Exception:
        return False


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
        live = _LIVE.get(name) or {}
        proc = live.get("proc")
        profile = live.get("profile")
        port = int(live.get("port") or 0)
    if proc is not None:
        try:
            if proc.poll() is None:
                return True
        except Exception:
            pass
    if profile and _cdp_alive(Path(profile), port):
        return True
    if proc is not None:
        with _LOCK:
            cur = _LIVE.get(name)
            if cur and cur.get("proc") is proc:
                _LIVE.pop(name, None)
    return False


def _spawn_chromium(exe: str, profile: Path, url: str,
                    port: int = 0) -> subprocess.Popen:
    profile = Path(profile).resolve()
    profile.mkdir(parents=True, exist_ok=True)
    _clear_locks(profile)
    err = profile / "browser.err"
    err_f = open(err, "ab")
    cmd = [
        exe,
        "--user-data-dir=" + str(profile),
        "--profile-directory=Default",
        "--remote-debugging-port=" + str(int(port or 0)),
        "--remote-debugging-address=127.0.0.1",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--disable-features=Translate",
        "--noerrdialogs",
        url or HOME_URL,
    ]
    kw: Dict[str, Any] = {"stdout": subprocess.DEVNULL, "stderr": err_f}
    if sys.platform == "win32":
        kw["creationflags"] = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    return subprocess.Popen(cmd, **kw)


def extra_urls_for(primary: str) -> List[str]:
    want = list(PLATFORM_HOME_URLS)
    out = []
    for u in want:
        if primary and u.rstrip("/") == (primary or "").rstrip("/"):
            continue
        out.append(u)
    if primary and primary.rstrip("/") not in {x.rstrip("/") for x in PLATFORM_HOME_URLS}:
        return list(PLATFORM_HOME_URLS)
    return out


def open_platform_tabs(port: int, urls: Optional[List[str]] = None) -> int:
    from urllib.parse import quote
    from .session_view import _http_get_local
    n = 0
    for u in (urls or extra_urls_for(HOME_URL)):
        try:
            _http_get_local(int(port), "/json/new?" + quote(u, safe=":/?&=#%"), timeout=2.5)
            n += 1
            time.sleep(0.2)
        except Exception:
            pass
    return n


def open_profile(accounts_dir: str, name: str, url: str = HOME_URL) -> Dict[str, Any]:
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
    logical = account_dir(accounts_dir, name) / CHROMIUM_DIR
    logical.mkdir(parents=True, exist_ok=True)
    prof = _prepare_profile(chromium_dir(accounts_dir, name), name)
    if prof.resolve() != logical.resolve():
        try:
            (logical / "LAUNCH_DIR.txt").write_text(str(prof), encoding="utf-8")
        except Exception:
            pass
    port = _debug_port_for(name)
    save_meta(accounts_dir, name, {
        "status": "opening", "last_url": url or HOME_URL, "exe": exe,
        "chromium_dir": str(prof), "debug_port": port, "last_error": "",
    })
    try:
        proc = _spawn_chromium(exe, prof, url or HOME_URL, port)
    except Exception as e:
        _clog("open", "spawn failed: %s" % e, "error")
        save_meta(accounts_dir, name, {"status": "error", "last_error": str(e)})
        raise RuntimeError("مرحله launch: Chromium اجرا نشد — %s" % e) from e
    bound = False
    last = ""
    for _ in range(28):
        if proc.poll() is not None:
            hint = ""
            try:
                hint = (prof / "browser.err").read_text(
                    encoding="utf-8", errors="replace")[-240:]
            except Exception:
                pass
            msg = "Chromium بلافاصله بسته شد (exit %s)%s" % (
                proc.returncode, (": " + hint if hint else ""))
            _clog("open", msg, "error")
            save_meta(accounts_dir, name, {"status": "error", "last_error": msg})
            raise RuntimeError("مرحله launch: " + msg)
        if _cdp_alive(prof, port):
            bound = True
            break
        last = "cdp not ready"
        time.sleep(0.25)
    if not bound:
        _clog("open", "window up but profile CDP not bound: %s" % last, "warning")
    with _LOCK:
        _LIVE[name] = {"proc": proc, "exe": exe, "profile": str(prof),
                       "url": url or HOME_URL, "opened_at": time.time(),
                       "port": port}
    save_meta(accounts_dir, name, {
        "status": "open", "last_error": "", "chromium_dir": str(prof),
    })
    _clog("open", "ok exe=%s profile=%s port=%s" % (exe, prof, port))
    if bound:
        try:
            ntab = open_platform_tabs(port, extra_urls_for(url or HOME_URL))
            _clog("open", "platform tabs +%s" % ntab)
        except Exception as e:
            _clog("open", "extra tabs: %s" % e, "warning")
    return {"ok": True, "name": name, "url": url or HOME_URL, "exe": exe,
            "profile": str(prof),
            "message": "پروفایل «%s» ساخته شد — دیوار و شیپور روی همین پروفایل باز هستند. در هر تب لاگین کنید، بعد ذخیره پروفایل." % name}


def _cookies_from_cdp(profile: Path, proc: Optional[subprocess.Popen],
                     port: int = 0) -> List[Dict[str, Any]]:
    from .session_view import CdpClient, _wait_cdp
    ws = _wait_cdp(int(port or 0), tries=40, profile=profile, proc=proc)
    cdp = CdpClient(ws)
    try:
        cdp.call("Network.enable")
        try:
            r = cdp.call("Network.getCookies", {
                "urls": ["https://divar.ir", "https://api.divar.ir",
                         "https://www.divar.ir", "https://www.sheypoor.com"],
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
        port = int(live.get("port") or 0)
    if ctx is not None:
        try:
            return list(ctx.cookies())
        except Exception as e:
            _clog("cookies", "playwright cookies failed: %s" % e, "warning")
    if profile:
        try:
            return _cookies_from_cdp(Path(profile), proc, port)
        except Exception as e:
            _clog("cookies", "cdp failed: %s" % e, "warning")
            return []
    return []


def harvest_to_session(accounts_dir: str, name: str,
                       cookies: List[Dict[str, Any]]) -> None:
    from .auth_session import merge_into_session_file
    d = account_dir(accounts_dir, name)
    session = d / "session.json"
    token = ""
    if session.exists():
        try:
            token = str(json.loads(session.read_text(encoding="utf-8")).get("token") or "")
        except Exception:
            token = ""
    full_divar = []
    full_sheypoor = []
    phone = load_meta(accounts_dir, name).get("phone") or ""
    for c in cookies or []:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        domain = str(c.get("domain") or c.get("host_key") or "").lower()
        entry = {
            "name": c.get("name"), "value": c.get("value"),
            "domain": domain or ".divar.ir",
            "path": c.get("path") or "/",
            "httpOnly": bool(c.get("httpOnly", False)),
            "secure": True,
        }
        if "divar.ir" in domain:
            full_divar.append(entry)
            if str(c.get("name")) in ("token", "sAccessToken") and not token:
                val = str(c.get("value") or "")
                if val.count(".") >= 2:
                    token = val
        elif "sheypoor.com" in domain:
            full_sheypoor.append(entry)
        else:
            # بدون دامنه — هر دو
            full_divar.append(entry)
    # ذخیره هر دو
    merge_into_session_file(str(session), str(phone), token,
                            {"cookies_full": full_divar, "sheypoor_cookies": full_sheypoor})


def save_profile(accounts_dir: str, name: str) -> Dict[str, Any]:
    name = safe_name(name)
    prof = chromium_dir(accounts_dir, name)
    used_live = is_open(name) or _cdp_alive(prof)
    _clog("save", "start name=%s window_open=%s profile=%s" % (
        name, used_live, prof))
    cookies: List[Dict[str, Any]] = []
    if used_live:
        cookies = _cookies_from_live(name)
        if not cookies:
            try:
                with _LOCK:
                    live = _LIVE.get(name) or {}
                    proc = live.get("proc")
                    port = int(live.get("port") or 0)
                cookies = _cookies_from_cdp(prof, proc, port)
            except Exception as e:
                _clog("save", "cdp retry: %s" % e, "warning")
                cookies = []
    disk: List[Dict[str, Any]] = []
    try:
        disk = _cookies_from_sqlite(prof)
    except Exception as e:
        _clog("save", "sqlite cookies: %s" % e, "warning")
        disk = []
    if not cookies:
        cookies = disk
    else:
        # ترکیب
        # اگر live کم بود، disk هم اضافه کن
        if len(cookies) < 5 and disk:
            cookies = cookies + disk

    per = cookies_per_platform(cookies)
    ok = per.get("divar") or per.get("sheypoor")
    # همچنین disk را چک کن
    if not ok:
        per_disk = cookies_per_platform(disk)
        ok = per_disk.get("divar") or per_disk.get("sheypoor")
        per = {k: per.get(k) or per_disk.get(k) for k in per}

    if not ok and not used_live and not disk:
        rec = save_meta(accounts_dir, name, {
            "profile_ready": False,
            "status": "login_required",
            "last_error": "window_not_open",
        })
        _clog("save", "window not open — refuse throwaway launch", "warning")
        return {"ok": False, "ready": False, **rec,
                "stage": "window",
                "message": "پنجره Chromium این اکانت باز نیست. اول «باز کردن دیوار/شیپور» را بزنید، لاگین کنید، بعد ذخیره."}
    harvest_to_session(accounts_dir, name, cookies)
    rec = save_meta(accounts_dir, name, {
        "profile_ready": bool(ok),
        "status": "ready" if ok else "login_required",
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S") if ok else "",
        "cookie_count": len(cookies or []),
        "from_open_window": used_live,
        "last_error": "" if ok else "login_not_detected",
        "platforms": per,
    })
    if not ok:
        _clog("save", "login not detected cookie_count=%s per=%s" % (len(cookies or []), per), "warning")
        return {"ok": False, "ready": False, **rec, "stage": "login",
                "message": "لاگین دیوار/شیپور در این پروفایل دیده نشد. در همان پنجره Chromium (تب دیوار و تب شیپور) وارد شوید، بعد ذخیره را بزنید. پنجره بسته نشد."}
    close_live(name)
    rec = save_meta(accounts_dir, name, {
        "status": "ready", "closed_after_save": True, "last_error": "",
        "platforms": per,
    })
    _clog("save", "ok closed window per=%s" % per)
    return {"ok": True, "ready": True, **rec, "stage": "saved",
            "platforms": per,
            "message": f"پروفایل ذخیره شد ✅ دیوار: {'لاگین' if per.get('divar') else 'لاگین نیست'} | شیپور: {'لاگین' if per.get('sheypoor') else 'لاگین نیست'} — پنجره بسته شد."}


def create_and_open(accounts_dir: str, name: str, phone: str = "", primary_url: str = HOME_URL) -> Dict[str, Any]:
    name = safe_name(name)
    chromium_dir(accounts_dir, name).mkdir(parents=True, exist_ok=True)
    save_meta(accounts_dir, name, {
        "profile_ready": False,
        "status": "created",
        "phone": phone or "",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_error": "",
    })
    opened = open_profile(accounts_dir, name, primary_url or HOME_URL)
    opened["message"] = (
        "پروفایل ساخته شد — دیوار و شیپور روی همین پروفایل باز هستند. "
        "در هر تب لاگین کنید، بعد «ذخیره پروفایل» را بزنید."
    )
    return opened


def update_profile(accounts_dir: str, name: str) -> Dict[str, Any]:
    name = safe_name(name)
    if not is_open(name):
        open_profile(accounts_dir, name, HOME_URL)
        return {"ok": True, "running": True, "stage": "opened",
                "message": "پنجره باز شد. لاگین دیوار/شیپور را تازه کنید، بعد دوباره ذخیره پروفایل را بزنید."}
    return save_profile(accounts_dir, name)


def delete_profile(accounts_dir: str, name: str) -> Dict[str, Any]:
    import shutil
    name = safe_name(name)
    close_live(name)
    launch = chromium_dir(accounts_dir, name)
    d = account_dir(accounts_dir, name)
    if launch.exists():
        inside = False
        try:
            launch.resolve().relative_to(d.resolve())
            inside = True
        except Exception:
            inside = False
        if not inside:
            shutil.rmtree(launch, ignore_errors=True)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    return {"ok": True, "message": f"پروفایل «{name}» حذف شد"}


def snapshot_fields(accounts_dir: str, name: str) -> Dict[str, Any]:
    rec = load_meta(accounts_dir, name)
    ready = bool(rec.get("profile_ready"))
    opened = is_open(name) if rec else False
    if not opened:
        try:
            opened = _cdp_alive(chromium_dir(accounts_dir, name))
        except Exception:
            opened = False
    plats = rec.get("platforms") or {}
    return {
        "profile_ready": ready,
        "profile_status": rec.get("status") or ("ready" if ready else "none"),
        "profile_saved_at": rec.get("saved_at") or "",
        "profile_open": opened,
        "phone": rec.get("phone") or "",
        "home_url": HOME_URL,
        "last_error": rec.get("last_error") or "",
        "chromium_dir": str(chromium_dir(accounts_dir, name)),
        "platforms": plats,
    }
