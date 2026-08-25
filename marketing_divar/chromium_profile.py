# -*- coding: utf-8 -*-
"""پروفایل پایدار Chromium برای هر اکانت دیوار.

سشن سایت را تزریق نمی‌کنیم. همان user-data-dir مرورگر، لاگین را نگه می‌دارد.
هر اکانت پوشهٔ جدا دارد: accounts/<name>/chromium/
صفحهٔ اول همیشه https://divar.ir/s/tehran است.
"""

from __future__ import annotations

import json
import re
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


def _ensure_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright نصب نیست. نصب‌کننده باید «playwright install chromium» را اجرا کند"
        ) from e
    return sync_playwright


def launch_kwargs(user_data: Path) -> Dict[str, Any]:
    user_data.mkdir(parents=True, exist_ok=True)
    return {
        "user_data_dir": str(user_data),
        "headless": False,
        "viewport": {"width": 1100, "height": 800},
        "locale": "fa-IR",
        "timezone_id": "Asia/Tehran",
        "ignore_https_errors": False,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ],
        "ignore_default_args": ["--enable-automation"],
    }


def close_live(name: str) -> None:
    name = safe_name(name)
    with _LOCK:
        live = _LIVE.pop(name, None)
    if not live:
        return
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
        return name in _LIVE


def _run_browser(accounts_dir: str, name: str, url: str, ready: threading.Event,
                 errbox: List[str]) -> None:
    sync_playwright = _ensure_playwright()
    pw = None
    ctx = None
    try:
        pw = sync_playwright().start()
        ctx = pw.chromium.launch_persistent_context(
            **launch_kwargs(chromium_dir(accounts_dir, name)))
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url or HOME_URL, wait_until="domcontentloaded", timeout=60000)
        with _LOCK:
            _LIVE[name] = {"pw": pw, "context": ctx, "page": page,
                           "opened_at": time.time()}
        ready.set()
        stop = threading.Event()
        with _LOCK:
            _LIVE[name]["stop"] = stop
        while not stop.wait(0.5):
            try:
                if ctx.pages:
                    continue
                break
            except Exception:
                break
    except Exception as e:
        errbox.append(str(e))
        ready.set()
    finally:
        with _LOCK:
            cur = _LIVE.get(name)
            if cur and cur.get("context") is ctx:
                _LIVE.pop(name, None)
        try:
            if ctx:
                ctx.close()
        except Exception:
            pass
        try:
            if pw:
                pw.stop()
        except Exception:
            pass


def open_profile(accounts_dir: str, name: str, url: str = HOME_URL) -> Dict[str, Any]:
    """Chromium همان اکانت را باز می‌کند — صفحهٔ تهران."""
    name = safe_name(name)
    close_live(name)
    chromium_dir(accounts_dir, name).mkdir(parents=True, exist_ok=True)
    save_meta(accounts_dir, name, {"status": "open", "last_url": url or HOME_URL})
    ready = threading.Event()
    errbox: List[str] = []
    t = threading.Thread(
        target=_run_browser,
        args=(accounts_dir, name, url or HOME_URL, ready, errbox),
        daemon=True,
    )
    t.start()
    if not ready.wait(45):
        raise RuntimeError("Chromium در ۴۵ ثانیه باز نشد — نصب Chromium را از نصب‌کننده چک کنید")
    if errbox:
        raise RuntimeError(errbox[0])
    return {"ok": True, "name": name, "url": url or HOME_URL,
            "message": "Chromium باز شد — اگر لازم است در همان پنجره لاگین کنید"}


def _cookies_from_live(name: str) -> List[Dict[str, Any]]:
    with _LOCK:
        live = _LIVE.get(name)
        ctx = live.get("context") if live else None
    if not ctx:
        return []
    try:
        return list(ctx.cookies())
    except Exception:
        return []


def _cookies_via_temp_launch(accounts_dir: str, name: str) -> List[Dict[str, Any]]:
    """اگر پنجره باز نیست، یک لحظه پروفایل را می‌خواند (بدون تزریق)."""
    sync_playwright = _ensure_playwright()
    pw = sync_playwright().start()
    try:
        ctx = pw.chromium.launch_persistent_context(
            **launch_kwargs(chromium_dir(accounts_dir, name)))
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto(HOME_URL, wait_until="domcontentloaded", timeout=25000)
            except Exception:
                pass
            time.sleep(1.2)
            return list(ctx.cookies())
        finally:
            try:
                ctx.close()
            except Exception:
                pass
    finally:
        try:
            pw.stop()
        except Exception:
            pass


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
    """بعد از لاگین کاربر: کوکی پروفایل را می‌خواند و READY می‌کند."""
    name = safe_name(name)
    cookies = _cookies_from_live(name)
    used_live = bool(cookies)
    if not cookies:
        cookies = _cookies_via_temp_launch(accounts_dir, name)
    ok = cookies_look_logged_in(cookies)
    harvest_to_session(accounts_dir, name, cookies)
    rec = save_meta(accounts_dir, name, {
        "profile_ready": bool(ok),
        "status": "ready" if ok else "login_required",
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S") if ok else "",
        "cookie_count": len(cookies or []),
        "from_open_window": used_live,
    })
    if not ok:
        return {"ok": False, "ready": False, **rec,
                "message": "لاگین دیوار در این پروفایل دیده نشد. در پنجره Chromium وارد شوید، بعد ذخیره را بزنید."}
    return {"ok": True, "ready": True, **rec,
            "message": "پروفایل ذخیره شد. دفعهٔ بعد «باز کردن دیوار» همین حساب لاگین‌شده را می‌آورد."}


def create_and_open(accounts_dir: str, name: str, phone: str = "") -> Dict[str, Any]:
    name = safe_name(name)
    chromium_dir(accounts_dir, name).mkdir(parents=True, exist_ok=True)
    save_meta(accounts_dir, name, {
        "profile_ready": False,
        "status": "created",
        "phone": phone or "",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
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
        return {"ok": True, "running": True,
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
    }
