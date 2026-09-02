# -*- coding: utf-8 -*-
"""رابط وب برنامه — سرور FastAPI محلی (روی سیستم داخل ایران اجرا می‌شود).

اجزا:
- API مدیریت اکانت‌ها (لاگین OTP دو مرحله‌ای از داخل مرورگر)
- مدیریت کلمات کلیدی (چندتایی با کاما)، قالب پیام چت/پیامک، تنظیمات
- شروع/توقف مانیتور با گزینه «موارد موجود هم برداشته شوند؟»
- داشبورد وضعیت زنده + لیست سرنخ‌ها + لاگ‌ها + خروجی CSV

اجرا:  python -m marketing_divar.web   →  http://localhost:8642
"""

from __future__ import annotations

import csv
import io
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from .. import logging_util, store
from ..accounts import AccountManager
from ..client import DivarAuthError, DivarBlockedError, DivarClient
from ..config import DEFAULTS, load_config
from ..db import (chat_queue, connect, pending_phone, quota_today,
                  reclaim_stuck_processing, set_lead_status, stats)
from ..messaging import build_message
from ..monitor import Monitor
from ..sms import sms_ready

DB_PATH = os.environ.get("DIVAR_DB_PATH", "data/divar_leads.db")
ACCOUNTS_DIR = os.environ.get("DIVAR_ACCOUNTS_DIR", "data/accounts")
def _base_url():
    """آدرس پایه دیوار (برای تست: متغیر محیطی DIVAR_BASE_URL)."""
    return os.environ.get("DIVAR_BASE_URL")

logging_util.setup()
log = logging_util.log

from ..brand import APP_NAME_EN, APP_NAME_FA, PORT as APP_PORT
from ..netinfo import listen_urls

from .. import __version__ as _APP_VER
app = FastAPI(title=f"{APP_NAME_FA} — {APP_NAME_EN}", version=_APP_VER)


@app.middleware("http")
async def _license_gate(request: Request, call_next):
    from ..license_session import cookie_ok, is_public, license_enforced
    if not license_enforced():
        return await call_next(request)
    path = request.url.path or "/"
    if is_public(path):
        return await call_next(request)
    if path.startswith("/api/") and not cookie_ok(request):
        return JSONResponse({"detail": "برای ورود به برنامه ابتدا وارد شوید"},
                            status_code=401)
    return await call_next(request)


class LicenseLogin(BaseModel):
    username: str = ""
    password: str = ""
    remember: bool = False


def _license_payload(res: Dict[str, Any]) -> Dict[str, Any]:
    from ..license_session import payload_from_check, session_public
    packed = payload_from_check(res)
    pub = session_public({**packed, "u": packed.get("u"),
                          "n": packed.get("n"), "p": packed.get("p")})
    pub["message_fa"] = res.get("message_fa") or ""
    pub["reason"] = res.get("reason") or "ok"
    return packed, pub


@app.post("/api/license/login")
def license_login(req: LicenseLogin):
    from fastapi.responses import JSONResponse as _JR
    from ..license_ledger import check_login
    from ..license_session import (clear_remember, load_remember, save_remember,
                                   set_cookie, sign_payload)
    user, pwd = (req.username or "").strip(), (req.password or "")
    if not user or not pwd:
        rem = load_remember()
        user = user or rem.get("username") or ""
        pwd = pwd or rem.get("password") or ""
    if not user or not pwd:
        raise HTTPException(400, "نام کاربری و رمز را وارد کنید")
    res = check_login(user, pwd)
    if not res.get("ok"):
        return _JR({"ok": False, "reason": res.get("reason"),
                    "message_fa": res.get("message_fa") or "ورود ناموفق"},
                   status_code=401)
    packed, pub = _license_payload(res)
    if req.remember:
        save_remember(user, pwd)
    body = {"ok": True, **pub}
    out = _JR(body)
    set_cookie(out, sign_payload(packed), bool(req.remember),
               int(res.get("days_left") or 0))
    log("success", "ورود لایسنس «%s»" % (pub.get("username") or user))
    return out


@app.get("/api/license/me")
def license_me(request: Request):
    from fastapi.responses import JSONResponse as _JR
    from ..license_ledger import refresh_user
    from ..license_session import (cookie_from_request, license_enforced,
                                   load_remember, session_public,
                                   set_cookie, sign_payload, verify_payload)
    if not license_enforced():
        return {"ok": True, "skipped": True, "plan": "full", "days_left": 365,
                "span_days": 365, "pct": 100, "full_name": "",
                "username": "", "expires": ""}
    data = verify_payload(cookie_from_request(request))
    user = (data or {}).get("u") or ""
    pwd = ""
    if not user:
        rem = load_remember()
        user = rem.get("username") or ""
        pwd = rem.get("password") or ""
        if user and pwd:
            from ..license_ledger import check_login
            res = check_login(user, pwd)
            if not res.get("ok"):
                return {"ok": False, "reason": res.get("reason"),
                        "message_fa": res.get("message_fa"),
                        "remember": True}
            packed, pub = _license_payload(res)
            out = _JR({"ok": True, "remember": True, **pub})
            set_cookie(out, sign_payload(packed), True,
                       int(res.get("days_left") or 0))
            return out
        return {"ok": False, "reason": "need_login",
                "message_fa": "برای ورود نام کاربری و رمز را وارد کنید"}
    res = refresh_user(user)
    if not res.get("ok"):
        return {"ok": False, "reason": res.get("reason"),
                "message_fa": res.get("message_fa")}
    packed, pub = _license_payload(res)
    out = _JR({"ok": True, **pub})
    set_cookie(out, sign_payload(packed), False,
               int(res.get("days_left") or 0))
    return out


@app.post("/api/license/logout")
def license_logout(forget: bool = False):
    from fastapi.responses import JSONResponse as _JR
    from ..license_session import clear_cookie, clear_remember
    if forget:
        clear_remember()
    out = _JR({"ok": True, "message_fa": "خارج شدید"})
    clear_cookie(out)
    return out

# --------------------------------------------------------- وضعیت سراسری --
_state: Dict[str, Any] = {
    "monitor": None,        # نمونه Monitor در حال اجرا
    "thread": None,         # نخ اجرایی مانیتور
    "started_at": None,
    "pending_logins": {},   # name -> phone (بین دو مرحله OTP)
    "include_existing": False,
    "gates": {},             # name -> چالش جمع ساده برای پاپ‌آپ پنل
    "puzzles": {},           # name -> PuzzleLive
    "collectors": {},        # name -> {ok, message, running}
}
_puzzle_lock = threading.Lock()


def _stop_all_puzzles() -> None:
    """فقط یک پازل در هر لحظه — قبلی را می‌بندد و پروفایل/کوکی موقت را پاک می‌کند."""
    bag = _state.get("puzzles") or {}
    for live in list(bag.values()):
        try:
            live.stop()
        except Exception:
            pass
    _state["puzzles"] = {}


def mgr() -> AccountManager:
    return AccountManager(load_config(), ACCOUNTS_DIR)


# ------------------------------------------------------------- مدل‌ها --
class OtpRequest(BaseModel):
    name: str
    phone: str
    platform: str = "divar"  # divar | sheypoor


class OtpConfirm(BaseModel):
    name: str
    code: str


class KeywordAdd(BaseModel):
    keyword: str = ""            # می‌تواند «a,b,c» باشد؛ با دسته می‌تواند خالی باشد
    cities: Optional[List[int]] = None
    category: str = ""           # اسلاگ دسته دیوار (mobile-tablet, light, …)
    price_min: float = 0         # میلیون تومان
    price_max: float = 0
    vip: bool = False
    hunter: bool = False
    hunter_adv: Optional[Dict[str, Any]] = None


class SettingsUpdate(BaseModel):
    values: Dict[str, Any]


class TemplateUpdate(BaseModel):
    channel: str            # chat | sms
    text: str


class MonitorStart(BaseModel):
    include_existing: bool = False   # تیک «موارد فعلی هم گرفته شوند؟»


class AccountAction(BaseModel):
    name: str
    action: str             # release | disable | enable


class SmsTest(BaseModel):
    to: str = ""            # خالی = فقط موجودی پنل


class LeadStatusUpdate(BaseModel):
    status: str             # new|contacted|replied|converted|ignored
    notes: str = ""
    chat_status: Optional[str] = None  # sent|failed|requires_operator|available


# ------------------------------------------------------------ API اکانت‌ها --
@app.get("/api/accounts")
def accounts_list():
    return {"accounts": mgr().snapshot(DB_PATH, complete_only=False)}


@app.post("/api/accounts/otp")
def accounts_otp(req: OtpRequest):
    """گام ۱ لاگین: ارسال کد پیامکی — دیوار via API، شیپور via Chromium."""
    name = req.name.strip().lower().replace(" ", "-")
    if not name:
        raise HTTPException(400, "نام اکانت الزامی است")
    if not (req.phone.startswith("09") and len(req.phone) == 11
            and req.phone.isdigit()):
        raise HTTPException(400, "شماره باید ۱۱ رقم و با ۰۹ شروع شود")
    plat = (req.platform or "divar").strip().lower()
    if plat == "sheypoor":
        # شیپور OTP رسمی ندارد — پروفایل Chromium باز می‌شود روی صفحه لاگین شیپور
        from ..chromium_profile import SHEYPOOR_LOGIN_URL, create_and_open, profile_ready, open_profile
        try:
            if not profile_ready(ACCOUNTS_DIR, name):
                res = create_and_open(ACCOUNTS_DIR, name, req.phone, primary_url=SHEYPOOR_LOGIN_URL)
            else:
                res = open_profile(ACCOUNTS_DIR, name, SHEYPOOR_LOGIN_URL)
            mgr().set_status(name, "active", note="پروفایل شیپور باز شد — لاگین کنید")
            log("info", f"پروفایل شیپور «{name}» باز شد برای {req.phone}")
            return {"ok": True, "platform": "sheypoor",
                    "message": "پروفایل شیپور باز شد — شماره را وارد و کد را بزنید، بعد ذخیره پروفایل",
                    **res}
        except Exception as e:
            raise HTTPException(400, f"باز کردن شیپور ناموفق: {e}")
    # دیوار — API رسمی
    cl = DivarClient(session_path=str(mgr().session_path(name)),
                     base_url=_base_url())
    try:
        cl.request_otp(req.phone)
    except (DivarBlockedError, RuntimeError) as e:
        log("error", f"ارسال کد برای {req.phone} ناموفق: {e}")
        raise HTTPException(429, f"ارسال کد ناموفق: {e}")
    _state["pending_logins"][name] = req.phone
    log("info", f"کد تایید دیوار برای اکانت «{name}» به {req.phone} ارسال شد")
    return {"ok": True, "platform": "divar", "message": "کد تایید دیوار پیامک شد؛ کد را وارد و تأیید کنید"}


@app.post("/api/accounts/confirm")
def accounts_confirm(req: OtpConfirm):
    """گام ۲ لاگین: تأیید کد و ذخیره سشن اکانت."""
    name = req.name.strip().lower().replace(" ", "-")
    phone = _state["pending_logins"].pop(name, None)
    if not phone:
        raise HTTPException(400, "اول گام «ارسال کد» را برای این اکانت انجام دهید")
    cl = DivarClient(session_path=str(mgr().session_path(name)),
                     base_url=_base_url())
    try:
        cl.confirm_otp(phone, req.code)
    except DivarAuthError as e:
        _state["pending_logins"][name] = phone  # فرصت دوباره برای کد
        raise HTTPException(400, f"کد نامعتبر: {e}")
    if not cl.token:
        raise HTTPException(400, "کد قبول شد ولی توکن نیامد — دوباره کد بگیرید")
    mgr().set_status(name, "active", note="نیاز به سشن سایت")
    mgr().set_site_verified(name, False)
    log("success", f"اکانت «{name}» توکن گرفت ({phone}) — سشن سایت جدا جمع شود")
    return {"ok": True,
            "message": "لاگین API شد. حالا «جمع‌آوری سشن سایت» را بزنید و در مرورگر دیوار وارد شوید."}


class AccountCollect(BaseModel):
    name: str


class ProfileReq(BaseModel):
    name: str
    phone: str = ""
    platform: str = "divar"  # divar | sheypoor


def _profile_name(raw: str) -> str:
    from ..chromium_profile import safe_name
    try:
        return safe_name(raw)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/accounts/profile/create")
def accounts_profile_create(req: ProfileReq):
    """پوشهٔ chromium جدا + باز کردن دیوار+شیپور."""
    from ..chromium_profile import HOME_URL, SHEYPOOR_LOGIN_URL, create_and_open
    name = _profile_name(req.name)
    phone = (req.phone or "").strip()
    if phone and not (phone.startswith("09") and len(phone) == 11 and phone.isdigit()):
        raise HTTPException(400, "شماره باید ۱۱ رقم و با ۰۹ شروع شود (یا خالی بماند)")
    plat = (req.platform or "divar").lower()
    primary = SHEYPOOR_LOGIN_URL if plat == "sheypoor" else HOME_URL
    try:
        res = create_and_open(ACCOUNTS_DIR, name, phone, primary_url=primary)
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    mgr().set_status(name, "active", note="پروفایل ساخته شد — لاگین دیوار+شیپور در Chromium")
    log("info", f"پروفایل Chromium «{name}» ساخته شد — {plat}")
    return res


@app.post("/api/accounts/profile/save")
def accounts_profile_save(req: ProfileReq):
    from ..chromium_profile import save_profile
    name = _profile_name(req.name)
    try:
        res = save_profile(ACCOUNTS_DIR, name)
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    if res.get("ready"):
        mgr().set_site_verified(name, True, note="پروفایل Chromium ذخیره شد")
        mgr().set_status(name, "active", note="پروفایل آماده")
        log("success", f"پروفایل «{name}» ذخیره شد — {res.get('platforms')}")
    else:
        mgr().set_site_verified(name, False)
        log("warning", f"ذخیره پروفایل «{name}»: لاگین دیده نشد")
    return res


@app.post("/api/accounts/profile/open")
def accounts_profile_open(req: ProfileReq):
    from ..chromium_profile import HOME_URL, SHEYPOOR_LOGIN_URL, open_profile
    name = _profile_name(req.name)
    plat = (req.platform or "divar").lower()
    target = SHEYPOOR_LOGIN_URL if plat == "sheypoor" else HOME_URL
    try:
        res = open_profile(ACCOUNTS_DIR, name, target)
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    log("info", f"پروفایل Chromium «{name}» روی {plat} باز شد")
    return res


@app.post("/api/accounts/profile/update")
def accounts_profile_update(req: ProfileReq):
    from ..chromium_profile import update_profile
    name = _profile_name(req.name)
    try:
        res = update_profile(ACCOUNTS_DIR, name)
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    if res.get("ready"):
        mgr().set_site_verified(name, True, note="پروفایل به‌روز شد")
        log("success", f"پروفایل «{name}» به‌روز شد")
    return res


@app.post("/api/accounts/profile/delete")
def accounts_profile_delete(req: ProfileReq):
    name = _profile_name(req.name)
    mgr().delete_account(name)
    log("info", f"پروفایل «{name}» حذف شد")
    return {"ok": True, "message": f"پروفایل «{name}» حذف شد"}


@app.get("/api/chromium/status")
def chromium_status():
    from ..app_chromium import status as chrome_status
    return chrome_status()


@app.post("/api/chromium/install")
def chromium_install():
    from ..app_chromium import start_install_async
    st = start_install_async()
    return {"ok": True, "message": "دانلود Chromium اختصاصی شروع شد", **st}


@app.post("/api/accounts/collect-site")
def accounts_collect_site(req: AccountCollect):
    """گام ۳: صفحهٔ لاگین دیوار در مرورگر — کاربر وارد می‌شود، کوکی‌ها ذخیره می‌شوند."""
    name = req.name.strip().lower().replace(" ", "-")
    m = mgr()
    if not m.has_token(name):
        raise HTTPException(404, "اول با کد پیامک لاگین کنید")
    bag = _state.setdefault("collectors", {})
    prev = bag.get(name) or {}
    if prev.get("running"):
        return {"ok": True, "running": True,
                "message": prev.get("message") or "صفحهٔ لاگین باز است — همان‌جا وارد شوید"}

    bag[name] = {"ok": None, "running": True,
                 "message": "صفحهٔ لاگین دیوار باز شد — همان‌جا با همین شماره وارد شوید"}

    def _work() -> None:
        try:
            from ..session_view import collect_site_login
            res = collect_site_login(str(m.session_path(name)), timeout_sec=180)
            if res.get("ok"):
                m.set_site_verified(name, True, note="سشن سایت تأیید شد")
                log("success", f"سشن سایت اکانت «{name}» ذخیره و تأیید شد")
            else:
                m.set_site_verified(name, False)
                log("warning", f"جمع‌آوری سشن «{name}»: {res.get('message')}")
            bag[name] = {"ok": bool(res.get("ok")), "running": False,
                         "message": res.get("message") or ""}
        except Exception as e:
            bag[name] = {"ok": False, "running": False, "message": str(e)}
            log("error", f"جمع‌آوری سشن «{name}» ناموفق: {e}")

    threading.Thread(target=_work, daemon=True).start()
    log("info", f"جمع‌آوری سشن سایت برای «{name}» شروع شد")
    return {"ok": True, "running": True,
            "message": "صفحهٔ دیوار باز می‌شود. همان‌جا لاگین کنید تا کوکی‌ها ذخیره شوند."}


@app.get("/api/accounts/collect-site")
def accounts_collect_status(name: str):
    name = (name or "").strip().lower().replace(" ", "-")
    rec = (_state.get("collectors") or {}).get(name) or {}
    m = mgr()
    verified = False
    try:
        verified = bool(next((a.get("site_verified") for a in
                              m.snapshot(DB_PATH) if a.get("name") == name), False))
    except Exception:
        verified = False
    if verified:
        return {"ok": True, "running": False, "verified": True,
                "message": rec.get("message") or "سشن سایت تأیید شد"}
    return {"ok": rec.get("ok"), "running": bool(rec.get("running")),
            "verified": False, "message": rec.get("message") or "هنوز شروع نشده"}


def _do_unlock(name: str, reason: str = "operator") -> Dict[str, Any]:
    from ..unlock import try_release_account
    res = try_release_account(mgr(), name, base_url=_base_url(), reason=reason)
    if res.get("cleared"):
        _state.get("gates", {}).pop(name, None)
        log("success", f"اکانت «{name}» با زدن دیوار باز شد ({reason})")
    elif res.get("state") == "captcha":
        log("warning", f"اکانت «{name}» هنوز پازل دیوار می‌خواهد — خودکار چک می‌شود")
    elif res.get("state") == "relogin":
        log("error", f"اکانت «{name}» نیاز به لاگین مجدد دارد")
    return res


@app.post("/api/accounts/action")
def accounts_action(req: AccountAction):
    m = mgr()
    if req.name not in m.list_accounts() and not m.has_token(req.name):
        raise HTTPException(404, "چنین اکانتی نیست")
    if req.action == "release":
        res = _do_unlock(req.name, "آزادسازی پنل")
        return {"ok": True, **res,
                "message": res.get("message") or ("آزاد شد" if res.get("cleared")
                                                  else "هنوز پازل می‌خواهد")}
    if req.action == "disable":
        m.set_status(req.name, "disabled")
        log("info", f"اکانت «{req.name}» غیرفعال شد")
    elif req.action == "enable":
        m.set_status(req.name, "active", note="")
    return {"ok": True}


class AccountProbe(BaseModel):
    name: str


@app.post("/api/accounts/captcha-cleared")
def accounts_captcha_cleared(req: AccountProbe):
    """کپچا حل شد: همین اکانت آزاد شود و فوراً یک شماره از صف گرفته شود."""
    from ..unlock import confirm_captcha_phone
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(400, "نام اکانت الزامی است")
    mon = _state.get("monitor")
    if mon is not None:
        try:
            mon._acct_errors[name] = 0
        except Exception:
            pass
    res = confirm_captcha_phone(mgr(), name, DB_PATH, base_url=_base_url())
    if res.get("cleared"):
        _state.get("gates", {}).pop(name, None)
        log("success", f"کپچا «{name}»: {res.get('message')}")
    else:
        log("warning", f"کپچا «{name}»: {res.get('message')}")
    return res


@app.post("/api/accounts/probe")
def accounts_probe(req: AccountProbe):
    """با همان اکانت مسدود به دیوار بزن — اگر پازل رفته بود خودکار آزاد شود."""
    m = mgr()
    if not m.has_full_login(req.name) and not m.has_token(req.name):
        raise HTTPException(404, "سشن کامل این اکانت نیست — دوباره لاگین کنید")
    live = (_state.get("puzzles") or {}).get(req.name)
    if live:
        try:
            live.harvest_cookies()
        except Exception:
            pass
    res = _do_unlock(req.name, "بررسی دستی")
    return res


class AccountPuzzle(BaseModel):
    name: str


@app.post("/api/accounts/open-puzzle")
def accounts_open_puzzle(req: AccountPuzzle):
    """پازل همان اکانت را داخل پاپ‌آپ پنل باز می‌کند (نه iframe، نه تب مهمان)."""
    m = mgr()
    if not m.has_full_login(req.name):
        raise HTTPException(404, "سشن کامل این اکانت نیست — پروفایل Chromium را ذخیره کنید")
    from ..chromium_profile import HOME_URL, open_profile, profile_ready
    start_url = HOME_URL
    try:
        rec = next((a for a in m.snapshot(DB_PATH) if a.get("name") == req.name), {})
        if rec.get("last_ad_url"):
            start_url = rec.get("last_ad_url")
        elif rec.get("last_ad_token"):
            start_url = f"https://divar.ir/v/{rec['last_ad_token']}"
    except Exception:
        pass
    if profile_ready(ACCOUNTS_DIR, req.name):
        try:
            res = open_profile(ACCOUNTS_DIR, req.name, start_url)
        except Exception as e:
            raise HTTPException(400, str(e))
        log("info", f"پازل/دیوار با پروفایل Chromium «{req.name}» باز شد")
        return {"ok": True, "embed": False, "fallback": True, "url": start_url,
                "message": (res.get("message") or "پنجرهٔ همین اکانت باز شد")
                + " — همان پروفایل لاگین‌شده است."}
    from ..session_view import PuzzleLive
    try:
        rec = next((a for a in m.snapshot(DB_PATH) if a.get("name") == req.name), {})
        start_url = rec.get("last_ad_url") or start_url
        if not rec.get("last_ad_url") and rec.get("last_ad_token"):
            start_url = f"https://divar.ir/v/{rec['last_ad_token']}"
    except Exception:
        pass
    with _puzzle_lock:
        _stop_all_puzzles()
        live = PuzzleLive()
        try:
            live.start(str(m.session_path(req.name)), start_url=start_url)
        except Exception as e:
            try:
                live.stop()
            except Exception:
                pass
            from ..session_view import launch_account_browser
            ok, win_msg = launch_account_browser(
                str(m.session_path(req.name)), req.name)
            if ok:
                log("warning",
                    f"تصویر داخل پنل نیامد — پنجرهٔ Chromium برای «{req.name}» باز شد")
                return {"ok": True, "embed": False, "fallback": True,
                        "url": start_url,
                        "message": (win_msg + " پازل را در همان پنجره حل کنید، "
                                    "بعد «الان با همین اکانت بزن» را بزنید.")}
            msg = str(e)
            if "timed out" in msg.lower() or "CDP" in msg or "آماده نشد" in msg:
                msg = ("مرورگر روی رایانه برای پازل آماده نشد. "
                       "پنجرهٔ Chromium اختصاصی را ببندید، پروکسی را خاموش کنید، "
                       "بعد دوباره «نمایش پازل همین‌جا» را بزنید. " + msg)
            raise HTTPException(400, msg)
        _state["puzzles"] = {req.name: live}
    log("info", f"پازل دیوار فقط برای اکانت «{req.name}» داخل همین صفحه باز شد")
    hint = "روی تصویر «نمایش شماره» را بزنید و پازل را حل کنید. لاگین پاک نمی‌شود."
    if start_url and start_url != "https://divar.ir":
        hint = "صفحهٔ همان آگهی مسدود باز است — «نمایش شماره» را بزنید و پازل را حل کنید."
    return {"ok": True, "embed": True, "url": start_url,
            "message": hint}


@app.post("/api/accounts/close-puzzle")
def accounts_close_puzzle():
    with _puzzle_lock:
        _stop_all_puzzles()
    return {"ok": True, "message": "پنجره بسته شد؛ لاگین و پروفایل همین اکانت ماند"}


@app.get("/api/accounts/puzzle-frame")
def accounts_puzzle_frame(name: str):
    from fastapi.responses import Response
    live = (_state.get("puzzles") or {}).get(name)
    if not live:
        raise HTTPException(404, "پازل این اکانت باز نیست")
    try:
        data = live.screenshot()
    except Exception as e:
        raise HTTPException(400, str(e))
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


class PuzzleClick(BaseModel):
    name: str
    x: float = 0.5
    y: float = 0.5
    text: str = ""


@app.post("/api/accounts/puzzle-click")
def accounts_puzzle_click(req: PuzzleClick):
    live = (_state.get("puzzles") or {}).get(req.name)
    if not live:
        raise HTTPException(404, "پازل این اکانت باز نیست")
    try:
        if req.text:
            live.type_text(req.text)
        else:
            live.click(req.x, req.y)
        try:
            live.harvest_cookies()
        except Exception:
            pass
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


# --------------------------------------------------------- API کلمات کلیدی --
@app.get("/api/categories")
def categories_get(exclude_estate: bool = True):
    from ..categories import public_list, public_list_non_estate
    if exclude_estate:
        return {"categories": public_list_non_estate(), "note": "املاک حذف شد — حوزه املاک کار نمی‌کنیم"}
    return {"categories": public_list()}


@app.get("/api/cities")
def cities_get():
    from ..cities import public_list
    return {"cities": public_list()}


@app.get("/api/keywords")
def keywords_get():
    return {"keywords": store.keywords_list(DB_PATH)}


@app.post("/api/keywords")
def keywords_add(req: KeywordAdd):
    if not (req.keyword or "").strip() and not (req.category or "").strip():
        raise HTTPException(400, "کلمه کلیدی یا دسته‌بندی دیوار را انتخاب کنید")
    from ..cities import parse_city_ids
    from ..pricing import million_to_toman
    added = store.keywords_add(
        DB_PATH, req.keyword, parse_city_ids(req.cities), req.category,
        price_min=million_to_toman(req.price_min),
        price_max=million_to_toman(req.price_max),
        vip=bool(req.vip), hunter=bool(req.hunter),
        hunter_adv=req.hunter_adv)
    log("info", f"پایش اضافه شد: {req.keyword or req.category}")
    return {"ok": added, "message": "اضافه شد" if added else "از قبل موجود بود"}


@app.delete("/api/keywords/{kw_id}")
def keywords_delete(kw_id: int):
    store.keywords_delete(DB_PATH, kw_id)
    return {"ok": True}


@app.post("/api/keywords/{kw_id}/toggle")
def keywords_toggle(kw_id: int, active: bool = True):
    store.keywords_toggle(DB_PATH, kw_id, active)
    return {"ok": True}


@app.get("/api/hunter-profile")
def hunter_profile_get(keyword: str = "", category: str = ""):
    from ..categories import hunter_allowed, is_real_estate
    from ..hunter_profile import default_profile, merge_overrides, public_for_ui
    if is_real_estate(category):
        return {"ok": False, "hunter": False,
                "reason": "املاک در شکارچی پشتیبانی نمی‌شود",
                "profile": public_for_ui(default_profile(category, keyword))}
    prof = store.hunter_profile_for(DB_PATH, keyword, category)
    return {"ok": True, "hunter": hunter_allowed(category), "profile": prof}


class HunterAdvUpdate(BaseModel):
    values: Dict[str, Any] = {}


@app.post("/api/keywords/{kw_id}/hunter-adv")
def keywords_hunter_adv(kw_id: int, req: HunterAdvUpdate):
    ok = store.keywords_set_hunter_adv(DB_PATH, kw_id, req.values or {})
    if not ok:
        raise HTTPException(404, "این پایش پیدا نشد")
    return {"ok": True, "message": "تنظیمات پیشرفته شکارچی ذخیره شد"}


@app.get("/api/hunter/analyze/{token}")
def hunter_analyze_token(token: str):
    """آنالیز حرفه‌ای یک آگهی — بازار سالم + اطمینان + مذاکره."""
    from ..hunter import collect_samples_detailed, evaluate
    from ..hunter_profile import default_profile, merge_overrides
    import json as _json

    con = connect(DB_PATH)
    try:
        row = con.execute("SELECT * FROM leads WHERE token=?", (token,)).fetchone()
        if not row:
            raise HTTPException(404, "آگهی پیدا نشد")
        kw = row["keyword"] if "keyword" in row.keys() else ""
        city = row["city"] if "city" in row.keys() else ""
        plat = row["platform"] if "platform" in row.keys() else "divar"
        cat = ""
        adv = {}
        try:
            kwrow = con.execute("SELECT category, hunter_adv FROM keywords WHERE keyword=?", (kw,)).fetchone()
            if kwrow:
                cat = kwrow["category"] or ""
                raw = kwrow["hunter_adv"] or ""
                if raw:
                    adv = _json.loads(raw)
        except Exception:
            pass
        prof = merge_overrides(default_profile(cat, kw), adv)
        extra = dict(row)
        extra["keyword"] = kw
        extra["category"] = cat
        blob = " ".join(str(row[k] or "") for k in ("title", "subtitle", "description", "inspect_summary") if k in row.keys())
        samples = collect_samples_detailed(con, kw, city, plat, limit=80)
        sc = evaluate(int(row["price"] if "price" in row.keys() else 0), samples, extra=extra, profile=prof, text=blob)
        # مذاکره
        history = []
        try:
            raw_hist = row["negotiation_history"] if "negotiation_history" in row.keys() else ""
            if raw_hist:
                history = _json.loads(raw_hist)
        except Exception:
            history = []
        return {"ok": True, "analysis": sc, "negotiation_history": history, "lead": dict(row)}
    finally:
        con.close()


@app.post("/api/hunter/negotiate/{token}")
def hunter_negotiate_trigger(token: str):
    """شروع/ادامه مذاکره دستی برای یک آگهی شکار."""
    con = connect(DB_PATH)
    try:
        row = con.execute("SELECT * FROM leads WHERE token=?", (token,)).fetchone()
        if not row:
            raise HTTPException(404, "آگهی پیدا نشد")
        # اگر مانیتور در حال اجراست، از متدش استفاده کن، وگرنه فقط رویداد بزن
        mon = _state.get("monitor")
        if mon:
            try:
                mon._maybe_hunter_negotiate(con, row, phone=row["phone"] if "phone" in row.keys() else "")
                return {"ok": True, "message": "مذاکره ارسال شد"}
            except Exception as e:
                raise HTTPException(400, str(e))
        else:
            # بدون مانیتور — فقط تحلیل مذاکره را برگردان
            from ..hunter_negotiator import generate_negotiation_message

            context = {
                "price": int(row["price"] if "price" in row.keys() else 0),
                "fair": int(row["hunter_fair_price"] if "hunter_fair_price" in row.keys() else 0),
                "healthy_median": int(row["hunter_market_median"] if "hunter_market_median" in row.keys() else 0),
                "discount_pct": float(row["hunter_discount_pct"] if "hunter_discount_pct" in row.keys() else 0),
                "title": str(row["title"] if "title" in row.keys() else ""),
                "level": str(row["hunter_level"] if "hunter_level" in row.keys() else ""),
            }
            msg = generate_negotiation_message(context, [], stage="opener")
            return {"ok": True, "message": msg, "text": msg}
    finally:
        con.close()


@app.get("/api/hunter/vip")
def hunter_vip_list(limit: int = 50):
    """لیست شکارهای ویژه — VIP آلارم‌ها."""
    con = connect(DB_PATH)
    try:
        rows = con.execute(
            "SELECT token,title,price,hunter_level,hunter_fair_price,hunter_market_median,hunter_discount_pct,"
            "hunter_confidence,negotiated_price,negotiation_status,url,phone,city,platform "
            "FROM leads WHERE hunter_level IN ('good','great') ORDER BY id DESC LIMIT ?",
            (min(limit, 200),),
        ).fetchall()
        return {"ok": True, "vip": [dict(r) for r in rows]}
    finally:
        con.close()


@app.get("/api/hunter/recheck-week")
def hunter_recheck_week(limit: int = 20):
    """هفته گذشته — شکارهایی که پیام نرفته یا مذاکره نیمه‌کاره است."""
    from ..monitor import recheck_week_old_leads
    res = recheck_week_old_leads(DB_PATH, max_items=min(limit, 100))
    return {"ok": True, **res}


@app.post("/api/hunter/recheck-week/run")
def hunter_recheck_week_run(limit: int = 12):
    """اجرای مذاکره/استعلام برای آگهی‌های هفته گذشته که پیام نرفته."""
    mon = _state.get("monitor")
    if mon:
        stats = mon.drain_week_old(max_items=min(limit, 30))
        return {"ok": True, "ran": True, "stats": stats, "message": f"{stats.get('negotiated',0)} مذاکره و {stats.get('inquired',0)} استعلام ارسال شد"}
    else:
        # بدون مانیتور — فقط لیست را برگردان، ارسال دستی از طریق negotiate/inquire
        from ..monitor import recheck_week_old_leads
        res = recheck_week_old_leads(DB_PATH, max_items=min(limit, 30))
        need = [x for x in res.get("items", []) if x.get("needs_action")]
        return {"ok": True, "ran": False, "needs_action": len(need), "items": need,
                "message": f"مانیتور خاموش است — {len(need)} مورد نیاز به اقدام دستی دارد. مانیتور را روشن کن یا دکمه مذاکره را بزن"}


# --------------------------------------------------- AI شکارچی — تنظیمات با کمک AI --
class HunterAIChatReq(BaseModel):
    message: str = ""
    session_id: str = "default"
    reset: bool = False


class HunterAIApplyReq(BaseModel):
    session_id: str = "default"
    config: Optional[Dict[str, Any]] = None  # اگر مستقیم بفرستد
    city_ids: Optional[List[int]] = None  # شهرهای پیش‌فرض برای پایش


@app.post("/api/hunter/ai-start")
def hunter_ai_start(session_id: str = "default"):
    from ..hunter_ai_wizard import get_wizard
    wiz = get_wizard(session_id or "default")
    res = wiz.start()
    return {"ok": True, **res}


@app.post("/api/hunter/ai-chat")
def hunter_ai_chat(req: HunterAIChatReq):
    from ..hunter_ai_wizard import get_wizard
    sid = (req.session_id or "default").strip() or "default"
    wiz = get_wizard(sid)
    if req.reset:
        wiz.reset()
        start = wiz.start()
        return {"ok": True, **start}
    # اگر هنوز start نشده، start کن
    if not wiz.state.get("messages"):
        wiz.start()
    result = wiz.handle_user(req.message or "")
    return {"ok": True, **result}


@app.get("/api/hunter/ai-config")
def hunter_ai_config(session_id: str = "default"):
    from ..hunter_ai_wizard import get_wizard
    wiz = get_wizard(session_id or "default")
    cfg = wiz.build_config()
    return {"ok": True, "config": cfg, "state": wiz.get_state(), "ready": bool(wiz.state.get("done"))}


@app.post("/api/hunter/ai-apply")
def hunter_ai_apply(req: HunterAIApplyReq):
    """ست کردن تنظیمات AI — خودکار کلمات کلیدی + hunter_adv می‌سازد"""
    from ..hunter_ai_wizard import get_wizard
    from ..cities import parse_city_ids
    sid = (req.session_id or "default").strip() or "default"
    wiz = get_wizard(sid)

    cfg = req.config or wiz.build_config()
    if not cfg or not cfg.get("keywords"):
        raise HTTPException(400, "هنوز تنظیماتی آماده نیست — اول با AI چت کن")

    cities = parse_city_ids(req.city_ids) if req.city_ids else None
    # اگر شهر نداده، از تنظیمات قبلی یا None (همه ایران)
    if cities is None:
        try:
            specs = store.keywords_active_specs(DB_PATH)
            if specs and specs[0].get("cities"):
                cities = specs[0].get("cities")
        except Exception:
            cities = None

    added = 0
    for kw in cfg.get("keywords", []):
        keyword = kw.get("keyword") or kw.get("model") or ""
        category = kw.get("category") or "mobile-phones"
        price_min = int(kw.get("price_min") or 0)
        price_max = int(kw.get("price_max") or 0)
        hunter_adv = kw.get("hunter_adv") or {}
        # تضمین vip+hunter
        ok = store.keywords_add(
            DB_PATH, keyword, cities, category,
            price_min=price_min, price_max=price_max,
            vip=True, hunter=True, hunter_adv=hunter_adv
        )
        if ok:
            added += 1

    log("success", f"تنظیمات AI شکارچی اعمال شد — {added} کلمه کلیدی: {', '.join([k['keyword'] for k in cfg.get('keywords',[])])}")
    return {
        "ok": True,
        "added": added,
        "message": f"{added} تنظیم شکارچی ست شد ✅ دیوار و شیپور هر دو فعال — مانیتور را شروع کن",
        "config": cfg,
        "warnings": cfg.get("warnings", []),
    }


class TiraPriceReq(BaseModel):
    query: str = ""
    models: List[str] = []

@app.get("/api/tira/price")
def tira_price(query: str = "", models: str = ""):
    """قیمت روز آیفون 13/14/15 پرو/پرومکس/نات‌اکتیو از اینترنت — ترب + کش."""
    from ..hunter_ai_wizard import get_market_price_for_model, extract_products_from_text
    from ..price_knowledge import fetch_market_price_from_web
    q = (query or models or "").strip()
    if not q:
        return {"ok": False, "message": "query خالی است"}
    # استخراج مدل‌ها
    prods = extract_products_from_text(q)
    model_names = [p["model"] for p in prods] if prods else [q]
    # اگر مدل آیفون 13/14/15 پرو/پرومکس/نات‌اکتیو جدا باشد، هر کدام را جدا قیمت بگیر
    prices = []
    for mn in model_names:
        try:
            price = get_market_price_for_model(mn)
            # تشخیص نات‌اکتیو
            is_not_active = any(w in mn.lower() for w in ["نات اکتیو", "not active", "پلمپ"]) or any(w in q.lower() for w in ["نات اکتیو", "not active"])
            prices.append({
                "model": mn,
                "price": int(price) if price else 0,
                "price_million": (int(price)//1_000_000) if price else 0,
                "is_not_active": bool(is_not_active),
                "source": "torob" if price else "none",
                "has_price": bool(price),
            })
        except Exception as e:
            prices.append({"model": mn, "price": 0, "error": str(e), "has_price": False})
    # اگر هیچ مدلی استخراج نشد ولی query آیفون دارد، برای 13/14/15 پرو/پرومکس جدا قیمت بگیر
    if not prices or (len(prices)==1 and not prices[0]["has_price"]):
        # تلاش برای مدل‌های رایج
        common = []
        for base in ["13", "13 Pro", "13 Pro Max", "14", "14 Pro", "14 Pro Max", "15", "15 Pro", "15 Pro Max"]:
            if base.split()[0] in q or "آیفون" in q.lower() or "iphone" in q.lower():
                common.append(f"آیفون {base}")
        # اگر query کلی آیفون است، همه را برگردان
        if "آیفون" in q or "iphone" in q.lower():
            if not common:
                common = [f"آیفون {b}" for b in ["13", "13 Pro", "13 Pro Max", "14", "14 Pro", "14 Pro Max", "15", "15 Pro", "15 Pro Max"]]
            for mn in common[:9]:
                if mn not in [p["model"] for p in prices]:
                    try:
                        price = get_market_price_for_model(mn)
                        prices.append({"model": mn, "price": int(price) if price else 0, "price_million": (int(price)//1_000_000) if price else 0, "source": "torob" if price else "none", "has_price": bool(price)})
                    except Exception:
                        pass
    return {"ok": True, "query": q, "prices": prices, "message": f"{len([p for p in prices if p.get('has_price')])} قیمت از اینترنت پیدا شد"}


# ---------------- تیرا ایجنت تمام‌عیار v3.6
class TiraAgentReq(BaseModel):
    message: str = ""
    session_id: str = "default"
    reset: bool = False
    topic: str = ""  # برای guide


@app.get("/api/tira/guide")
def tira_guide(topic: str = "general"):
    from ..tira_agent import get_system_guide
    guide = get_system_guide(topic)
    return {"ok": True, "topic": topic, "guide": guide}


@app.post("/api/tira/agent")
def tira_agent_chat(req: TiraAgentReq):
    """تیرا ایجنت — تسلط کامل به سیستم + تحقیق بازار + شکار"""
    from ..tira_agent import get_tira_agent, get_system_guide, research_any_product
    sid = (req.session_id or "default").strip() or "default"
    ag = get_tira_agent(sid)
    if req.reset:
        ag.reset()
        start = ag.start()
        return {"ok": True, **start, "session_id": sid}
    # اگر هنوز شروع نشده
    if not ag.state.get("messages"):
        ag.start()
    # اگر topic guide خواسته
    if req.topic and not req.message:
        guide = get_system_guide(req.topic)
        return {"ok": True, "reply": guide, "messages": ag.state["messages"], "guide": guide, "session_id": sid}
    result = ag.handle_user(req.message or "")
    result["session_id"] = sid
    result["ok"] = True
    return result


class TiraResearchReq(BaseModel):
    keyword: str = ""


@app.post("/api/tira/research")
def tira_research(req: TiraResearchReq):
    from ..tira_agent import research_any_product
    kw = (req.keyword or "").strip()
    if not kw:
        raise HTTPException(400, "کلمه کلیدی خالی است")
    res = research_any_product(kw)
    prices = res.get("prices") or []
    market_price = prices[0]["price"] if prices else None
    source = prices[0]["source"] if prices else res.get("type")
    variant = None
    # تشخیص واریانت آیفون از keyword
    low = kw.lower()
    if "پرو مکس" in kw or "promax" in low or "pro max" in low:
        variant = {"model": "Pro Max", "type": "پرو مکس"}
    elif "پرو" in kw:
        variant = {"model": "Pro", "type": "پرو"}
    elif "مینی" in kw or "mini" in low:
        variant = {"model": "Mini", "type": "مینی"}
    elif "پلاس" in kw or "plus" in low:
        variant = {"model": "Plus", "type": "پلاس"}
    else:
        variant = {"model": res.get("variants", [kw])[0] if res.get("variants") else kw, "type": res.get("type")}
    # اگر نات‌اکتیو
    if any(w in low for w in ["نات اکتیو", "not active", "پلمپ", "آکبند"]):
        variant["not_active"] = True
        variant["extra"] = "+8% گران‌تر از کارکرده سالم"
    return {"ok": True, "market_price": market_price, "source": source, "variant": variant, "all_prices": prices, **res}


class TiraTestReq(BaseModel):
    phone: str = ""  # شماره تست خود کاربر
    title: str = ""  # عنوان آگهی فرضی
    price: int = 0
    scenario: str = "negotiate"  # negotiate | second_sim | opener | full
    incoming_phone: str = ""  # برای تست سیم دوم
    original_phone: str = ""
    incoming_text: str = ""  # متن ورودی فروشنده برای تست شما؟


@app.post("/api/tira/test")
def tira_test(req: TiraTestReq):
    """🧪 تست تیرا — مذاکره آزمایشی + سیم دوم + تحقیق قیمت"""
    from ..tira_agent import generate_polite_negotiation, detect_second_sim_reply, detect_ambiguous_text_reply, research_any_product
    phone = (req.phone or "").strip()
    if phone and not (phone.startswith("09") and len(phone) == 11 and phone.isdigit()):
        raise HTTPException(400, "شماره تست باید 11 رقم و با 09 شروع شود")
    title = (req.title or "آیفون 13 پرو مکس تمیز").strip()
    price = int(req.price or 25_000_000)
    scenario = (req.scenario or "negotiate").lower()

    if scenario == "second_sim":
        inc = (req.incoming_phone or "09120000000").strip()
        orig = (req.original_phone or "09121111111").strip()
        inc_text = (req.incoming_text or "").strip() or "شما؟"
        det_phone = detect_second_sim_reply(inc, orig, ad_token="test-token", ad_title=title, incoming_text=inc_text)
        det_text = detect_ambiguous_text_reply(inc_text, ad_title=title)
        return {"ok": True, "scenario": "second_sim", "detection": det_phone, "text_detection": det_text, "second_sim_test": {"incoming": inc_text, "needs_clarify": det_phone.get("need_clarify") or det_text.get("need_clarify"), "response": det_phone.get("message") or det_text.get("message")}, "message": det_phone.get("message") or det_text.get("message"), "note": "اگر فروشنده با سیم دوم یا با متن «شما؟» جواب داد، تیرا گیج نمی‌زند"}

    # سناریو مذاکره
    context = {
        "title": title,
        "price": price,
        "fair": int(price * 1.15),
        "healthy_median": int(price * 1.2),
        "discount_pct": 12,
        "model": title,
        "factors": [],
    }
    if scenario == "opener":
        msg = generate_polite_negotiation(context, stage="opener")
    elif scenario == "offer":
        msg = generate_polite_negotiation(context, stage="offer")
    elif scenario == "final":
        msg = generate_polite_negotiation(context, stage="final")
    elif scenario == "full":
        research = research_any_product(title)
        opener = generate_polite_negotiation({**context, "fair": research.get("prices", [{}])[0].get("price", context["fair"]) if research.get("prices") else context["fair"]}, stage="opener")
        offer = generate_polite_negotiation(context, stage="offer")
        closer = generate_polite_negotiation(context, stage="final")
        second = detect_second_sim_reply("09120000000", "09121111111", ad_token="test-full", ad_title=title, incoming_text="شما؟")
        analysis = None
        try:
            from ..hunter import analyze_lead
            lead_mock = {"title": title, "price": price, "description": title, "city": "تهران"}
            analysis = analyze_lead(lead_mock, keyword=title)
        except Exception as e:
            analysis = {"note": f"hunter analyze not available: {e}", "price": price, "fair": context["fair"], "level": "good"}
        return {"ok": True, "scenario": "full", "analysis": analysis, "negotiation": {"opener": opener, "offer": offer, "closer": closer, "fair_price": context["fair"]}, "second_sim_test": {"incoming": "شما؟", "needs_clarify": second.get("need_clarify"), "response": second.get("message")}, "market_research": research, "message": "تست کامل تیرا"}
    else:
        msg = generate_polite_negotiation(context, stage="opener")
        try:
            from ..hunter import analyze_lead
            analysis = analyze_lead({"title": title, "price": price, "description": title, "city": "تهران"}, keyword=title)
        except Exception:
            analysis = {"price": price, "fair": context["fair"], "median": context["healthy_median"], "level": "good", "raw_level": "good", "discount_pct": 12, "flags": {}, "missing": []}
        offer = generate_polite_negotiation(context, stage="offer")
        closer = generate_polite_negotiation(context, stage="final")
        second = detect_second_sim_reply("09120000000", "09121111111", ad_token="test-neg", ad_title=title, incoming_text="شما؟")
        research = research_any_product(title)
        return {"ok": True, "scenario": scenario, "analysis": analysis, "negotiation": {"opener": msg, "offer": offer, "closer": closer, "fair_price": context["fair"]}, "second_sim_test": {"incoming": "شما؟", "needs_clarify": second.get("need_clarify"), "response": second.get("message")}, "market_research": research, "message": msg}

    try:
        from ..hunter import analyze_lead
        analysis = analyze_lead({"title": title, "price": price, "description": title, "city": "تهران"}, keyword=title)
    except Exception:
        analysis = {"price": price, "fair": context["fair"], "median": context["healthy_median"], "level": "good", "discount_pct": 5, "flags": {}, "missing": []}
    second = detect_second_sim_reply("09120000000", "09121111111", ad_token="test", ad_title=title, incoming_text="شما؟")
    research = research_any_product(title)
    return {"ok": True, "scenario": scenario, "analysis": analysis, "negotiation": {"opener": msg if scenario=="opener" else "", "offer": msg if scenario=="offer" else "", "closer": msg if scenario=="final" else "", "fair_price": context["fair"]}, "second_sim_test": {"incoming": "شما؟", "needs_clarify": second.get("need_clarify"), "response": second.get("message")}, "market_research": research, "message": msg}


@app.post("/api/accounts/platform/toggle")
def accounts_platform_toggle(req: PlatformToggleReq):
    """toggle آیکون دیوار/شیپور کنار اکانت‌ها — روشن/خاموش پلتفرم per-account"""
    from ..chromium_profile import get_platforms_enabled, set_platform_enabled, toggle_platform_enabled, safe_name
    try:
        name = safe_name(req.name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    plat = (req.platform or "").lower().strip()
    if plat not in ("divar", "sheypoor"):
        raise HTTPException(400, "platform باید divar یا sheypoor باشد")
    if req.enabled is None:
        en = toggle_platform_enabled(ACCOUNTS_DIR, name, plat)
    else:
        en = set_platform_enabled(ACCOUNTS_DIR, name, plat, bool(req.enabled))
    log("info", f"پلتفرم «{plat}» برای اکانت «{name}» → {'روشن' if en.get(plat) else 'خاموش'}")
    return {"ok": True, "name": name, "platform": plat, "enabled": bool(en.get(plat)), "platforms_enabled": en, "message": f"{plat} برای {name} {'روشن' if en.get(plat) else 'خاموش'} شد"}


@app.get("/api/platforms")
def platforms_status():
    from ..platforms import active_platforms, enabled_from_settings, TITLES
    s = store.settings_all(DB_PATH)
    enabled = enabled_from_settings(s)
    return {
        "ok": True,
        "active_default": list(active_platforms()),
        "enabled": enabled,
        "titles": TITLES,
        "settings": {f"platform_{pid}": bool(s.get(f"platform_{pid}", pid in active_platforms())) for pid in ("divar", "sheypoor")},
        "note": " غیرفعال پیش‌فرض — فقط دیوار و شیپور فعال",
    }


# ------------------------------------------------------------- API پیام‌ها --
@app.get("/api/templates")
def templates_get():
    chat = store.template_get(DB_PATH, "chat") or {"text": DEFAULTS["chat_template"]}
    sms = store.template_get(DB_PATH, "sms") or {"text": DEFAULTS["chat_template"]}
    inq = store.template_get(DB_PATH, "inquire") or {
        "text": DEFAULTS.get("inquire_template") or ""}
    return {"chat": chat["text"], "sms": sms["text"], "inquire": inq["text"]}


@app.post("/api/templates")
def templates_set(req: TemplateUpdate):
    if req.channel not in ("chat", "sms", "inquire"):
        raise HTTPException(400, "channel باید chat یا sms یا inquire باشد")
    store.template_set(DB_PATH, req.channel, req.text)
    log("info", f"قالب پیام {req.channel} ذخیره شد")
    return {"ok": True}


# ------------------------------------------------------------ API تنظیمات --
@app.get("/api/settings")
def settings_get():
    return store.settings_all(DB_PATH)


def _apply_sms_to_monitor() -> None:
    mon = _state.get("monitor")
    if not mon:
        return
    s = store.settings_all(DB_PATH)
    for k in ("sms_provider", "sms_api_key", "sms_username", "sms_password",
              "sms_line_number", "sms_auto_on_new", "sms_daily_limit",
              "per_account_daily_limit", "adaptive_until_captcha",
              "ip_daily_limit", "phone_delay_sec",
              "chat_auto_on_new", "chat_auto_daily_limit", "chat_auto_delay_sec",
              "sms_inbox_on", "nlu_use_local",
              "sms_use_pattern", "sms_pattern_bodyid", "sms_pattern_args",
              "sms_pattern_text"):
        if k in s:
            mon.cfg[k] = s[k]


@app.post("/api/settings")
def settings_update(req: SettingsUpdate):
    saved = [k for k, v in req.values.items() if store.settings_set(DB_PATH, k, v)]
    _apply_sms_to_monitor()
    log("info", f"تنظیمات ذخیره شد: {', '.join(saved)}")
    return {"ok": True, "saved": saved}


class SmsAuto(BaseModel):
    on: bool = True


@app.post("/api/sms/auto")
def sms_auto_toggle(req: SmsAuto):
    """روشن/خاموش کردن ارسال خودکار — همان لحظه روی مانیتور اعمال می‌شود."""
    store.settings_set(DB_PATH, "sms_auto_on_new", bool(req.on))
    if req.on:
        store.settings_set(DB_PATH, "sms_provider", "melipayamak")
    _apply_sms_to_monitor()
    from ..sms import sms_ready
    ready, why = sms_ready(store.settings_all(DB_PATH))
    if req.on and not ready:
        log("warning", f"ارسال خودکار روشن شد ولی هنوز آماده نیست: {why}")
        return {"ok": True, "on": True, "ready": False,
                "message": f"خودکار روشن شد — اول {why}"}
    log("success" if req.on else "info",
        "ارسال خودکار پیامک " + ("روشن شد" if req.on else "خاموش شد"))
    return {"ok": True, "on": bool(req.on), "ready": ready,
            "message": "ارسال خودکار روشن است — به محض پیدا شدن شماره پیامک می‌رود"
            if req.on else "ارسال خودکار خاموش شد"}


class ChatAuto(BaseModel):
    on: bool = True


@app.post("/api/chat/auto")
def chat_auto_toggle(req: ChatAuto):
    store.settings_set(DB_PATH, "chat_auto_on_new", bool(req.on))
    _apply_sms_to_monitor()
    log("success" if req.on else "info",
        "ارسال خودکار چت " + ("روشن شد" if req.on else "خاموش شد"))
    return {"ok": True, "on": bool(req.on),
            "message": "چت خودکار برای آگهی فقط‌چت روشن است (متن با {title} متغیر است)"
            if req.on else "چت خودکار خاموش شد"}


@app.get("/api/robot")
def robot_status():
    """پنل ربات هوشمند — وضعیت چت، صندوق، مدل محلی."""
    from ..nlu_model import status as nlu_st
    con = connect(DB_PATH)
    try:
        def _c(where: str) -> int:
            try:
                return con.execute("SELECT COUNT(*) c FROM leads WHERE " + where).fetchone()["c"]
            except Exception:
                return 0
        replies_n = 0
        try:
            replies_n = con.execute("SELECT COUNT(*) c FROM replies").fetchone()["c"]
        except Exception:
            replies_n = 0
        unread = 0
        try:
            unread = con.execute(
                "SELECT COUNT(*) c FROM replies WHERE COALESCE(acted,0)=0").fetchone()["c"]
        except Exception:
            pass
        s = store.settings_all(DB_PATH)
        return {
            "chat_auto": bool(s.get("chat_auto_on_new")),
            "sms_auto": bool(s.get("sms_auto_on_new")),
            "sms_inbox": bool(s.get("sms_inbox_on", True)),
            "platforms": {
                "divar": bool(s.get("platform_divar", True)),
                "sheypoor": bool(s.get("platform_sheypoor", True)),
                            },
            "nlu": nlu_st(),
            "chats_today": quota_today(con).get("chats", 0),
            "sms_today": quota_today(con).get("sms", 0),
            "chat_sent": _c("chat_status='sent'"),
            "chat_need_operator": _c("chat_status='requires_operator'"),
            "replied": _c("lead_status='replied'"),
            "replies": replies_n,
            "unread_replies": unread,
            "hunter_great": _c("hunter_level='great'"),
            "hunter_pending": _c("hunter_level='pending'"),
            "defect": _c("is_defect=1"),
            "inquiry": _c("inquiry_status IN ('pending','sent')"),
        }
    finally:
        con.close()


@app.get("/api/replies")
def replies_list(token: str = "", limit: int = 80):
    from ..inbox import list_replies
    con = connect(DB_PATH)
    try:
        return {"replies": list_replies(con, token=token, limit=min(limit, 200))}
    finally:
        con.close()


@app.get("/api/nlu/status")
def nlu_status():
    from ..nlu_model import status as nlu_st
    return nlu_st()


@app.post("/api/nlu/install")
def nlu_install(small: bool = False):
    from ..nlu_model import start_install_async
    st = start_install_async(small=small)
    log("info", "دانلود مدل محلی درک متن شروع شد")
    return {"ok": True, "message": "دانلود مدل محلی شروع شد — کنار برنامه نصب می‌شود", **st}


@app.post("/api/nlu/install-dummy")
def nlu_install_dummy():
    """نصب مدل تستی 10MB برای تست صفر تا صد بدون دانلود 1.5GB — fallback هوشمند فعال."""
    from ..nlu_model import ensure_dummy_model_for_test, status as nlu_st
    try:
        ensure_dummy_model_for_test()
        log("success", "مدل تستی نصب شد — fallback هوشمند فعال")
        return {"ok": True, "message": "مدل تستی نصب شد — سیستم کامل با fallback هوشمند کار می‌کند", **nlu_st()}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/api/nlu/memory")
def nlu_memory():
    from ..nlu_memory import get_memory, get_stats
    return {"memory": get_memory(), "stats": get_stats()}


@app.get("/api/nlu/events")
def nlu_events(limit: int = 50):
    from ..events import recent
    return {"events": recent(limit)}


@app.get("/api/nlu/engine")
def nlu_engine_status():
    from ..nlu_engine import NluEngine
    eng = NluEngine(db_path=DB_PATH)
    return eng.status()


@app.post("/api/nlu/selftest")
def nlu_selftest():
    from ..nlu_engine import NluEngine
    eng = NluEngine(db_path=DB_PATH)
    res = eng.full_selftest()
    log("success" if res.get("ok") else "warning", f"تست صفر تا صد: {res.get('summary')}")
    return res


class NluAnalyzeReq(BaseModel):
    text: str = ""
    keyword: str = ""
    category: str = ""
    platform: str = "divar"


@app.post("/api/nlu/analyze")
def nlu_analyze(req: NluAnalyzeReq):
    from ..nlu_engine import NluEngine
    eng = NluEngine(db_path=DB_PATH)
    return eng.analyze_reply(req.text, keyword=req.keyword, category=req.category, platform=req.platform)


# ------------------------------------------------------------ API مانیتور --
@app.post("/api/monitor/start")
def monitor_start(req: MonitorStart):
    if _state["thread"] and _state["thread"].is_alive():
        raise HTTPException(409, "مانیتور از قبل در حال اجراست")
    specs = store.keywords_active_specs(DB_PATH)
    if req.include_existing:
        for s in specs:
            if s.get("match_all"):
                s["pages"] = max(int(s.get("pages") or 1), 5)
    if not specs:
        raise HTTPException(400, "اول حداقل یک کلمه کلیدی یا دسته‌بندی فعال اضافه کنید")
    if not mgr().list_accounts():
        raise HTTPException(400, "اول حداقل یک اکانت لاگین کنید")

    cfg = store.effective_config(DB_PATH, load_config())
    # گزینه «موارد موجود هم گرفته شوند؟»
    con = connect(DB_PATH)
    try:
        reclaim_stuck_processing(con)
        if not req.include_existing:
            con.execute("UPDATE leads SET phone_status='legacy' "
                        "WHERE phone_status='pending'")
            con.commit()
            log("info", "حالت «فقط آگهی‌های جدید» — سرنخ‌های قدیمی نادیده گرفته شدند")
        else:
            log("info", "حالت «موارد موجود هم گرفته شوند» فعال شد")
    finally:
        con.close()

    mon = Monitor(cfg, specs, db_path=DB_PATH, accounts_dir=ACCOUNTS_DIR,
                  interactive=False, base_url=_base_url(),
                  on_event=lambda level, msg: logging_util.log(
                      "warning" if level == "warning" else
                      ("error" if level == "error" else
                       ("success" if level == "success" else "info")), msg))
    _state.update(monitor=mon, started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                  include_existing=req.include_existing)
    t = threading.Thread(target=_run_monitor, args=(mon,), daemon=True)
    _state["thread"] = t
    t.start()
    log("success", f"مانیتور شروع شد ({len(specs)} کلمه کلیدی، "
                   f"حالت: {'همه' if req.include_existing else 'فقط جدیدها'})")
    return {"ok": True, "keywords": len(specs)}


def _run_monitor(mon: Monitor) -> None:
    try:
        mon.run()
    except Exception as e:  # نخ پس‌زمینه هرگز نباید بی‌صدا بمیرد
        log("error", f"مانیتور با خطا متوقف شد: {e}")
    finally:
        _state["monitor"] = None
        log("info", "نخ مانیتور پایان یافت")


@app.post("/api/monitor/stop")
def monitor_stop():
    mon = _state.get("monitor")
    if not mon:
        raise HTTPException(404, "مانیتور در حال اجرا نیست")
    mon.stop()
    log("info", "دستور توقف مانیتور صادر شد")
    return {"ok": True}


def _telegram_status() -> Dict[str, Any]:
    from ..notifier import telegram_configured, telegram_last
    cfg = store.effective_config(DB_PATH, load_config())
    last = telegram_last()
    last["configured"] = telegram_configured(cfg)
    if not last["configured"]:
        last["message"] = "توکن/Chat ID ذخیره نشده — پنل بدون تلگرام کار می‌کند"
    return last


def _channels_status() -> Dict[str, Any]:
    from ..notifier import channels_status
    return channels_status(store.effective_config(DB_PATH, load_config()))


@app.get("/api/status")
def status():
    mon = _state.get("monitor")
    running = bool(_state["thread"] and _state["thread"].is_alive())
    con = connect(DB_PATH)
    try:
        q = quota_today(con)
        st = [dict(r) for r in stats(con)]
        queue_len = len(pending_phone(con))
        chat_len = len(chat_queue(con))
        def _cnt(where: str) -> int:
            return con.execute(f"SELECT COUNT(*) c FROM leads WHERE {where}").fetchone()["c"]
        total_leads = con.execute("SELECT COUNT(*) c FROM leads").fetchone()["c"]
        found = _cnt("phone_status='found'")
        try:
            vip_found = _cnt("vip=1")
        except Exception:
            vip_found = 0
        breakdown = {
            "total": total_leads,
            "new": _cnt("phone_status='pending'"),
            "matched": total_leads,
            "processing": _cnt("phone_status='processing'"),
            "contact_found": found,
            "no_contact": _cnt("phone_status='hidden'"),
            "failed": _cnt("phone_status='error'"),
        }
        acc_snap = mgr().snapshot(DB_PATH, complete_only=False)
        # IP info
        current_ip = None
        last_ip = None
        ip_changed = False
        try:
            from ..netinfo import get_public_ip
            from ..db import get_last_ip as _get_last_ip, get_ip_history as _get_ip_hist
            # get_public_ip کش ندارد، پس از کش فایل استفاده کن برای سرعت
            try:
                from ..netinfo import get_current_ip_cached
                current_ip = get_current_ip_cached(cache_sec=120)
            except Exception:
                current_ip = None
            last_ip = _get_last_ip(con)
            if last_ip and current_ip and last_ip != current_ip:
                ip_changed = True
        except Exception:
            pass
        acc_break = {"active": 0, "busy": 0, "rate_limited": 0,
                     "captcha": 0, "error": 0, "disabled": 0}
        for a in acc_snap:
            stt = a.get("status") or "active"
            if stt == "active":
                acc_break["active"] += 1
            elif stt == "captcha":
                acc_break["captcha"] += 1
            elif stt == "cooldown":
                acc_break["rate_limited"] += 1
            elif stt == "relogin":
                acc_break["error"] += 1
            elif stt == "disabled":
                acc_break["disabled"] += 1
    finally:
        con.close()
    return {
        "running": running, "started_at": _state.get("started_at"),
        "tick": mon.tick if mon else 0, "paused": mon.paused if mon else False,
        "queue": queue_len, "chat_queue": chat_len, "total_leads": total_leads,
        "phones_found": found, "phones_today": q["phones"],
        "searches_today": q["searches"],
        "sms_today": q.get("sms", 0),
        "ip_daily_limit": store.settings_all(DB_PATH).get("ip_daily_limit", 240),
        "sms_auto_on_new": bool(store.settings_all(DB_PATH).get("sms_auto_on_new")),
        "chat_auto_on_new": bool(store.settings_all(DB_PATH).get("chat_auto_on_new")),
        "chats_today": q.get("chats", 0),
        "sms_ready": sms_ready(store.settings_all(DB_PATH))[0],
        "data_dir": os.environ.get("DIVAR_DATA_DIR") or str(Path(DB_PATH).resolve().parent),
        "listen": listen_urls(APP_PORT),
        "app_name": APP_NAME_FA,
        "breakdown": breakdown, "accounts_breakdown": acc_break,
        "accounts": acc_snap,
        "keywords": store.keywords_list(DB_PATH),
        "logs": logging_util.recent(50),
        "stats_by_keyword": st,
        "captcha_needed": [a["name"] for a in acc_snap if a.get("status") == "captcha"],
        "per_account_daily_limit": store.settings_all(DB_PATH).get(
            "per_account_daily_limit", 60),
        "adaptive_until_captcha": bool(store.settings_all(DB_PATH).get(
            "adaptive_until_captcha", True)),
        "telegram": _telegram_status(),
        "channels": _channels_status(),
        "vip_found": vip_found,
    }


@app.post("/api/monitor/pause")
def monitor_pause():
    mon = _state.get("monitor")
    if mon:
        mon.paused = not mon.paused
        log("info", "مانیتور " + ("متوقف موقت شد" if mon.paused else "ادامه یافت"))
        return {"ok": True, "paused": mon.paused}
    raise HTTPException(404, "مانیتور در حال اجرا نیست")


class RequeueOne(BaseModel):
    token: str


@app.post("/api/leads/requeue-hidden")
def requeue_hidden():
    """آگهی‌هایی که اشتباه «فقط چت» شده‌اند را به صف شماره‌گیری برگردان."""
    con = connect(DB_PATH)
    try:
        cur = con.execute(
            "UPDATE leads SET phone_status='pending', last_error='requeued', "
            "retry_count=0, phone_error='' "
            "WHERE phone_status='hidden'")
        n = cur.rowcount
        con.commit()
    finally:
        con.close()
    log("info", f"{n} آگهی از فقط‌چت به صف شماره‌گیری برگشت")
    return {"ok": True, "count": n, "message": f"{n} آگهی به صف شماره‌گیری برگشت"}


@app.post("/api/leads/requeue")
def requeue_one(req: RequeueOne):
    con = connect(DB_PATH)
    try:
        cur = con.execute(
            "UPDATE leads SET phone_status='pending', last_error='requeued', "
            "retry_count=0, phone_error='' WHERE token=? AND "
            "phone_status IN ('hidden','error')",
            (req.token,))
        n = cur.rowcount
        con.commit()
    finally:
        con.close()
    if not n:
        raise HTTPException(404, "این سرنخ برای برگشت به صف مناسب نیست")
    return {"ok": True, "message": "به صف شماره‌گیری برگشت"}


# ------------------------------------------------------------- API سرنخ‌ها --
@app.get("/api/leads")
def leads(filter: str = "all", limit: int = 100):
    con = connect(DB_PATH)
    try:
        if filter == "phone":
            where, args = "phone_status='found'", ()
        elif filter == "chat":
            where, args = "phone_status='hidden' AND lead_status='new'", ()
        elif filter == "replied":
            where, args = "lead_status='replied'", ()
        elif filter == "hunter":
            where, args = "hunter_level IN ('good','great','pending')", ()
        elif filter == "hunter_pending":
            where, args = "hunter_level='pending'", ()
        elif filter == "defect":
            where, args = "is_defect=1", ()
        else:
            where, args = "1=1", ()
        rows = con.execute(
            f"SELECT token,title,subtitle,description,phone,phone_status,keyword,"
            f"matched_keywords,city,lead_status,chat_status,sms_status,url,first_seen_at,"
            f"phone_checked_at,last_error,platform,hunter_level,last_reply_intent,"
            f"price_kind FROM leads WHERE {where} "
            f"ORDER BY id DESC LIMIT ?", (*args, min(limit, 500))).fetchall()
        return {"leads": [dict(r) for r in rows]}
    finally:
        con.close()


@app.get("/api/export")
def export(filter: str = "phone"):
    """دانلود CSV سازگار با اکسل (utf-8-sig)."""
    con = connect(DB_PATH)
    try:
        if filter == "phone":
            where = "phone_status='found'"
        elif filter == "chat":
            where = "phone_status='hidden'"
        elif filter == "hunter":
            where = "hunter_level IN ('good','great')"
        elif filter == "defect":
            where = "is_defect=1"
        elif filter == "inquiry":
            where = "inquiry_status IN ('pending','sent')"
        else:
            where = "1=1"
        rows = con.execute(
            f"SELECT token,title,subtitle,description,phone,phone_status,keyword,"
            f"matched_keywords,city,lead_status,chat_status,sms_status,url,"
            f"first_seen_at,phone_checked_at,published_at,sms_sent_at,"
            f"platform,hunter_level,price_kind,is_defect,is_placeholder,"
            f"inquiry_status,last_reply_intent "
            f"FROM leads WHERE {where} "
            f"ORDER BY id DESC").fetchall()
    finally:
        con.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["توکن", "عنوان", "توضیح میانی", "متن", "شماره تماس", "وضعیت شماره",
                "کلمه کلیدی", "کلمات منطبق", "شهر", "وضعیت پیگیری", "وضعیت چت",
                "وضعیت پیامک", "لینک", "تاریخ‌ساعت کشف", "تاریخ‌ساعت استخراج شماره",
                "زمان انتشار آگهی", "تاریخ‌ساعت ارسال پیامک",
                "پلتفرم", "شکارچی", "نوع قیمت", "معیوب", "قیمت ساختگی",
                "وضعیت استعلام", "نیت آخرین پاسخ"])
    for r in rows:
        w.writerow(list(r))
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition":
                 f"attachment; filename=leads_{filter}_{time.strftime('%Y%m%d')}.csv"})


@app.get("/api/leads/{token}/draft")
def lead_draft(token: str):
    """متن شخصی‌سازی‌شده + لینک چت برای ارسال نیمه‌خودکار."""
    con = connect(DB_PATH)
    try:
        row = con.execute("SELECT * FROM leads WHERE token=?", (token,)).fetchone()
        if not row:
            raise HTTPException(404, "سرنخ پیدا نشد")
        tpl = (store.template_get(DB_PATH, "chat") or {}).get("text") \
            or DEFAULTS["chat_template"]
        return {"token": token, "url": row["url"], "title": row["title"],
                "message": build_message(tpl, row),
                "chat_status": row["chat_status"] if "chat_status" in row.keys() else "",
                "phone_status": row["phone_status"]}
    finally:
        con.close()


@app.post("/api/leads/{token}/status")
def lead_status_update(token: str, req: LeadStatusUpdate):
    allowed = {"new", "contacted", "replied", "converted", "ignored", "removed"}
    if req.status not in allowed:
        raise HTTPException(400, "وضعیت نامعتبر")
    con = connect(DB_PATH)
    try:
        row = con.execute("SELECT token FROM leads WHERE token=?", (token,)).fetchone()
        if not row:
            raise HTTPException(404, "سرنخ پیدا نشد")
        set_lead_status(con, token, req.status, req.notes)
        if req.chat_status:
            con.execute("UPDATE leads SET chat_status=? WHERE token=?",
                        (req.chat_status, token))
        con.commit()
    finally:
        con.close()
    log("info", f"وضعیت سرنخ {token} → {req.status}")
    return {"ok": True}


@app.post("/api/leads/{token}/sms")
def lead_send_sms(token: str):
    """ارسال دستی همان قالب آماده‌شده به شمارهٔ این سرنخ."""
    from ..db import bump_quota, now as _now
    from ..sms import live_sms_cfg, send_for_lead
    con = connect(DB_PATH)
    try:
        row = con.execute("SELECT * FROM leads WHERE token=?", (token,)).fetchone()
        if not row:
            raise HTTPException(404, "سرنخ پیدا نشد")
        if row["phone_status"] != "found" or not row["phone"]:
            raise HTTPException(400, "این سرنخ شماره ندارد")
        cfg = live_sms_cfg(DB_PATH)
        tpl = (store.template_get(DB_PATH, "sms") or {}).get("text") or ""
        r = send_for_lead(cfg, dict(row), tpl)
        if r.get("ok"):
            try:
                con.execute(
                    "UPDATE leads SET sms_status='sent', sms_sent_at=?, "
                    "sms_recid=?, sms_delivery_status='pending' WHERE token=?",
                    (_now(), str(r.get("recid") or ""), token))
                bump_quota(con, "sms")
                con.commit()
            except Exception:
                pass
            log("success", f"پیامک دستی ارسال شد → {row['phone']}")
        else:
            try:
                con.execute("UPDATE leads SET sms_status='failed' WHERE token=?", (token,))
                con.commit()
            except Exception:
                pass
            log("error", f"پیامک دستی ناموفق: {r.get('message')}")
        return r
    finally:
        con.close()


@app.get("/api/sms/completeness")
def sms_completeness():
    """بررسی کامل بودن اتصال ملی‌پیامک برای کاربر — v4"""
    from ..sms import check_mellipayamak_completeness
    s = store.settings_all(DB_PATH)
    res = check_mellipayamak_completeness(s)
    return {"ok": True, **res}


@app.post("/api/sms/delivery-check")
def sms_delivery_check():
    """وضعیت تحویل پیامک‌های «در انتظار» را از ملی‌پیامک (GetDeliveries2) می‌پرسد.

    همهٔ سرنخ‌هایی که sms_status='sent' و delivery='pending' و recid دارند
    چک می‌شوند؛ نتیجه به‌صورت delivered / failed ذخیره می‌شود.
    """
    from ..sms import delivery_melipayamak
    s = store.settings_all(DB_PATH)
    if (s.get("sms_provider") or "none") != "melipayamak":
        raise HTTPException(400, "سرویس‌دهنده را ملی‌پیامک کنید")
    user = s.get("sms_username") or ""
    pwd = s.get("sms_password") or s.get("sms_api_key") or ""
    if not user or not pwd:
        raise HTTPException(400, "نام کاربری و رمز ملی‌پیامک را ذخیره کنید")
    con = connect(DB_PATH)
    updated = {"delivered": 0, "failed": 0, "pending": 0, "checked": 0}
    try:
        rows = con.execute(
            "SELECT token, phone, sms_recid FROM leads WHERE sms_status='sent' "
            "AND sms_delivery_status IN ('pending','') AND sms_recid IS NOT NULL "
            "AND sms_recid != ''").fetchall()
        for r in rows:
            recid = str(r["sms_recid"])
            d = delivery_melipayamak(user, pwd, recid)
            st = d.get("status") or "unknown"
            if st == "delivered":
                con.execute(
                    "UPDATE leads SET sms_delivery_status='delivered', "
                    "sms_delivered_at=? WHERE token=?",
                    (time.strftime("%Y-%m-%d %H:%M:%S"), r["token"]))
                updated["delivered"] += 1
            elif st == "failed":
                con.execute(
                    "UPDATE leads SET sms_delivery_status='failed' WHERE token=?",
                    (r["token"],))
                updated["failed"] += 1
            else:
                updated["pending"] += 1
            updated["checked"] += 1
        con.commit()
    finally:
        con.close()
    log("success", f"بررسی تحویل پیامک: {updated['checked']} چک، "
                   f"{updated['delivered']} تحویل، {updated['failed']} ناموفق")
    return {"ok": True, **updated}


# ------------------------------------------------------------ صفحه اصلی --
def _static_dir() -> Path:
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        for cand in (root / "marketing_divar" / "web" / "static",
                     root / "static"):
            if cand.exists():
                return cand
    return Path(__file__).parent / "static"


_STATIC = _static_dir()


def start_background() -> None:
    """ربات تلگرام + چک دوره‌ای پازل دیوار برای اکانت‌های مسدود."""
    from ..telegram_bot import start_bot
    from ..unlock import start_watch

    def _cfg():
        return store.effective_config(DB_PATH, load_config())

    def _st():
        mon = _state.get("monitor")
        return {"running": bool(_state.get("thread") and _state["thread"].is_alive()),
                "tick": mon.tick if mon else 0}

    start_bot(_cfg, DB_PATH, _st)

    def _cleared(name: str, res: Dict[str, Any]) -> None:
        log("success", f"اکانت «{name}» خودکار آزاد شد — دیوار دیگر پازل نمی‌خواهد")
        try:
            from ..notifier import notify
            notify(_cfg(), f"اکانت {name} آزاد شد — پازل دیوار دیگر لازم نیست. شماره‌گیری ادامه می‌یابد.",
                   account=name, problem="captcha_cleared", operation="contact",
                   action="نیازی به کار شما نیست")
        except Exception:
            pass

    start_watch(mgr, lambda: DB_PATH, _base_url, _cleared)


@app.post("/api/sms/test")
def sms_test(req: SmsTest):
    """آزمایش موجودی یا ارسال یک پیامک از مسیر رسمی ملی‌پیامک."""
    from ..sms import credit_melipayamak, send_melipayamak
    s = store.settings_all(DB_PATH)
    user = s.get("sms_username") or ""
    pwd = s.get("sms_password") or s.get("sms_api_key") or ""
    if (s.get("sms_provider") or "none") != "melipayamak":
        raise HTTPException(400, "سرویس‌دهنده را ملی‌پیامک کنید")
    if not user or not pwd:
        raise HTTPException(400, "نام کاربری و رمز ملی‌پیامک را ذخیره کنید")
    if req.to.strip():
        line = s.get("sms_line_number") or ""
        if not line:
            raise HTTPException(400, "شماره خط ارسال را وارد کنید")
        r = send_melipayamak(user, pwd, req.to.strip(), line, f"test {APP_NAME_EN}")
    else:
        r = credit_melipayamak(user, pwd)
    log("info" if r.get("ok") else "error",
        f"ملی‌پیامک: {r.get('message')}")
    return r


class ChannelTest(BaseModel):
    channel: str
    token: str = ""
    chat_id: str = ""
    enabled: Optional[bool] = True


@app.post("/api/channels/test")
def channel_test(req: ChannelTest):
    """ذخیره توکن/شناسه همان پلتفرم و ارسال پیام «ارتباط برقرار شد»."""
    from ..notifier import channels_status, test_channel
    ch = (req.channel or "").strip().lower()
    key_map = {
        "telegram": ("telegram_bot_token", "telegram_chat_id", "telegram_enabled"),
        "bale": ("bale_bot_token", "bale_chat_id", "bale_enabled"),
        "rubika": ("rubika_bot_token", "rubika_chat_id", "rubika_enabled"),
    }
    if ch not in key_map:
        raise HTTPException(400, "پلتفرم باید telegram یا bale یا rubika باشد")
    tok_k, chat_k, en_k = key_map[ch]
    if req.token.strip():
        store.settings_set(DB_PATH, tok_k, req.token.strip())
    if req.chat_id.strip():
        store.settings_set(DB_PATH, chat_k, req.chat_id.strip())
    store.settings_set(DB_PATH, en_k, True if req.enabled is None else bool(req.enabled))
    cfg = store.effective_config(DB_PATH, load_config())
    res = test_channel(cfg, ch)
    if res.get("ok") and res.get("suggested_chat_id"):
        store.settings_set(DB_PATH, chat_k, str(res["suggested_chat_id"]))
        cfg = store.effective_config(DB_PATH, load_config())
    res["channels"] = channels_status(cfg)
    log("success" if res.get("ok") else "warning",
        f"تست {ch}: {res.get('message')}")
    return res


@app.post("/api/telegram/test")
def telegram_test():
    from ..notifier import (bale_configured, channels_status, notify,
                            rubika_configured, telegram_configured,
                            telegram_last)
    from ..telegram_bot import build_status_text
    cfg = store.effective_config(DB_PATH, load_config())
    mon = _state.get("monitor")
    running = bool(_state.get("thread") and _state["thread"].is_alive())
    text = build_status_text(DB_PATH, cfg, running=running,
                             tick=mon.tick if mon else 0)
    any_ch = (telegram_configured(cfg) or bale_configured(cfg)
              or rubika_configured(cfg))
    if any_ch:
        notify(cfg, text, important=False)
    last = telegram_last()
    ch = channels_status(cfg)
    return {"ok": last.get("ok") or ch["bale"]["ok"] or ch["rubika"]["ok"]
            or not any_ch,
            "preview": text, "telegram": last, "channels": ch}


class CaptchaSolve(BaseModel):
    name: str
    answer: str


@app.get("/api/captcha/pending")
def captcha_pending():
    """اکانت‌هایی که دیوار کپچا خواسته + سؤال ساده برای پاپ‌آپ پنل."""
    from ..gate import new_challenge
    gates = _state.setdefault("gates", {})
    pending = []
    for a in mgr().snapshot(DB_PATH, complete_only=False):
        if a.get("status") != "captcha":
            gates.pop(a["name"], None)
            continue
        ch = gates.get(a["name"]) or new_challenge(a["name"])
        gates[a["name"]] = ch
        from ..client import parse_block_body
        parsed = parse_block_body(a.get("last_block_body") or "")
        pending.append({"name": a["name"], "question": ch["question"],
                        "note": a.get("note") or "",
                        "last_probe_at": a.get("last_probe_at") or "",
                        "last_probe_state": a.get("last_probe_state") or "",
                        "image_url": parsed.get("image_url") or "",
                        "has_widget": bool(parsed.get("has_widget")),
                        "last_ad_url": a.get("last_ad_url") or "",
                        "divar_url": a.get("last_ad_url") or "https://divar.ir"})
    return {"pending": pending}


@app.post("/api/captcha/solve")
def captcha_solve(req: CaptchaSolve):
    """حل کپچای پنل → آزادسازی اکانت (ادامهٔ درخواست به دیوار)."""
    from ..gate import check_answer
    name = req.name.strip().lower().replace(" ", "-")
    ch = (_state.get("gates") or {}).get(name)
    if not ch:
        raise HTTPException(400, "چالشی برای این اکانت نیست")
    if not check_answer(ch, req.answer):
        raise HTTPException(400, "پاسخ نادرست است")
    m = mgr()
    if not m.has_token(name):
        raise HTTPException(404, "چنین اکانتی لاگین نشده است")
    m.release(name)
    _state.get("gates", {}).pop(name, None)
    log("success", f"کپچای پنل برای «{name}» حل شد — اکانت آزاد")
    return {"ok": True, "message": "حل شد — شماره‌گیری ادامه می‌یابد"}


@app.post("/api/diag")
def diag_run():
    """بررسی اتصال کامل — روی سیستم خود کاربر، همهٔ لایه‌ها را تست می‌کند."""
    from ..diag import run_diag
    kws = store.keywords_list(DB_PATH)
    keyword = next((k["keyword"] for k in kws if k.get("active")), None) or "آپارتمان"
    accs = mgr().list_accounts()
    sess = str(mgr().session_path(accs[0])) if accs else None
    log("info", f"بررسی اتصال کامل شروع شد (کلمهٔ آزمایشی: «{keyword}»)")
    result = run_diag(base_url=_base_url(), keyword=keyword,
                      account_session=sess)
    for st in result["steps"]:
        mark = "✓" if st["ok"] else "✗"
        log("success" if st["ok"] else "error",
            f"{mark} {st['fa']} — {st['detail']} ({st['ms']}ms)")
    good = sum(1 for x in result["steps"] if x["ok"])
    log("success" if good >= 4 else "error",
        f"بررسی اتصال تمام شد: {good}/{len(result['steps'])} قدم سالم")
    return result



@app.get("/api/ip/status")
def ip_status():
    """وضعیت IP فعلی و تاریخچه — برای نمایش در پنل + ریست خودکار سهمیه."""
    from ..db import connect as _connect, get_last_ip, get_ip_history, quota_today
    from ..netinfo import get_public_ip, lan_ipv4
    con = _connect(DB_PATH)
    try:
        last_ip = get_last_ip(con)
        history = []
        try:
            rows = get_ip_history(con, limit=20)
            history = [dict(r) for r in rows]
        except Exception:
            history = []
        q = quota_today(con)
    finally:
        con.close()
    current_ip = None
    try:
        current_ip = get_public_ip(timeout=5)
    except Exception:
        current_ip = None
    lan = []
    try:
        lan = lan_ipv4()
    except Exception:
        lan = []
    changed = (last_ip is not None and current_ip is not None and last_ip != current_ip)
    return {
        "ok": True,
        "current_ip": current_ip,
        "last_ip": last_ip,
        "changed": bool(changed),
        "lan_ips": lan,
        "history": history,
        "quota_today": q,
        "message": f"IP فعلی: {current_ip or 'نامشخص'} — آخرین IP ثبت: {last_ip or 'ندارد'}" + (" — IP عوض شده، سهمیه ریست می‌شود" if changed else ""),
    }


@app.post("/api/ip/check")
def ip_check():
    """چک دستی IP — اگر عوض شده باشد سهمیه صفر می‌شود."""
    from ..db import connect as _connect, set_ip_and_check_reset, quota_today
    from ..netinfo import get_public_ip
    ip = get_public_ip(timeout=8)
    if not ip:
        raise HTTPException(400, "نتوانست IP خارجی را بگیرد — اینترنت را چک کنید")
    con = _connect(DB_PATH)
    try:
        res = set_ip_and_check_reset(con, ip)
        q = quota_today(con)
    finally:
        con.close()
    if res.get("changed"):
        log("success", f"IP عوض شد: {res.get('old_ip')} → {res.get('new_ip')} — سهمیه ریست شد")
        return {"ok": True, "changed": True, "old_ip": res.get("old_ip"), "new_ip": res.get("new_ip"), "quota": q, "message": f"IP عوض شد ({res.get('old_ip')} → {res.get('new_ip')}) — سهمیه امروز صفر شد ✅"}
    elif res.get("first_time"):
        return {"ok": True, "changed": False, "first_time": True, "new_ip": ip, "quota": q, "message": f"IP ثبت شد: {ip}"}
    else:
        return {"ok": True, "changed": False, "ip": ip, "quota": q, "message": f"IP تغییری نکرده: {ip} — سهمیه امروز: {q.get('phones',0)} شماره"}


@app.post("/api/ip/reset-quota")
def ip_reset_quota(reason: str = "manual"):
    """ریست دستی سهمیه — وقتی کاربر می‌داند IP عوض شده یا می‌خواهد دوباره شروع کند."""
    from ..db import connect as _connect, reset_today_quota, quota_today
    con = _connect(DB_PATH)
    try:
        q = reset_today_quota(con, reason=reason)
    finally:
        con.close()
    log("success", f"سهمیه امروز دستی ریست شد — دلیل: {reason}")
    return {"ok": True, "quota": q, "message": "سهمیه امروز صفر شد — می‌تونی دوباره شماره بگیری ✅"}




class TiraProfitReq(BaseModel):
    keyword: str = ""
    sell_price: int = 0
    profit_pct: float = 10
    conditions: str = ""
    test_improve: bool = False

@app.post("/api/tira/profitability")
def tira_profitability(req: TiraProfitReq):
    """محاسبه سودآوری با هزاران پارامتر + تحقیق اینترنت + تست/بهبود خودکار"""
    from ..profitability import calculate_profitability, test_and_improve_profitability
    kw = (req.keyword or "").strip()
    if not kw:
        raise HTTPException(400, "کلمه کلیدی خالی است")
    if req.test_improve:
        res = test_and_improve_profitability(kw, iterations=3)
        return {"ok": True, **res}
    res = calculate_profitability(
        title=kw,
        sell_price_healthy=req.sell_price if req.sell_price else None,
        desired_profit_pct=req.profit_pct or 10,
        conditions_text=req.conditions or "",
    )
    return {"ok": True, **res}


@app.post("/api/shutdown")
def shutdown():
    """Stop monitor and exit the Python process (panel Close button)."""
    mon = _state.get("monitor")
    if mon:
        try:
            mon.stop()
        except Exception:
            pass
    try:
        _stop_all_puzzles()
    except Exception:
        pass
    log("info", "خروج کامل از برنامه")
    if os.environ.get("DIVAR_NO_EXIT") == "1" or "unittest" in sys.modules:
        return {"ok": True, "scheduled": False, "message": "برنامه بسته می‌شود"}

    def _die() -> None:
        time.sleep(0.4)
        os._exit(0)

    threading.Thread(target=_die, daemon=True).start()
    return {"ok": True, "scheduled": True, "message": "برنامه بسته می‌شود"}


@app.get("/", response_class=HTMLResponse)
def index():
    return (_STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/logo.png")
def logo_png():
    from fastapi.responses import FileResponse
    p = _STATIC / "logo.png"
    if not p.exists():
        raise HTTPException(404, "logo")
    return FileResponse(str(p), media_type="image/png")


@app.get("/favicon.ico")
def favicon():
    from fastapi.responses import FileResponse
    for name in ("favicon.ico", "logo.png"):
        p = _STATIC / name
        if p.exists():
            return FileResponse(str(p))
    raise HTTPException(404, "favicon")
