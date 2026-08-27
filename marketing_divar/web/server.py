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

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
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

app = FastAPI(title=f"{APP_NAME_FA} — {APP_NAME_EN}", version="2.2.0")

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
    """گام ۱ لاگین: ارسال کد پیامکی به شماره."""
    name = req.name.strip().lower().replace(" ", "-")
    if not name:
        raise HTTPException(400, "نام اکانت الزامی است")
    if not (req.phone.startswith("09") and len(req.phone) == 11
            and req.phone.isdigit()):
        raise HTTPException(400, "شماره باید ۱۱ رقم و با ۰۹ شروع شود")
    cl = DivarClient(session_path=str(mgr().session_path(name)),
                     base_url=_base_url())
    try:
        cl.request_otp(req.phone)
    except (DivarBlockedError, RuntimeError) as e:
        log("error", f"ارسال کد برای {req.phone} ناموفق: {e}")
        raise HTTPException(429, f"ارسال کد ناموفق: {e}")
    _state["pending_logins"][name] = req.phone
    log("info", f"کد تایید برای اکانت «{name}» به {req.phone} ارسال شد")
    return {"ok": True, "message": "کد تایید پیامک شد؛ گام بعدی را انجام دهید"}


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


def _profile_name(raw: str) -> str:
    from ..chromium_profile import safe_name
    try:
        return safe_name(raw)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/accounts/profile/create")
def accounts_profile_create(req: ProfileReq):
    """پوشهٔ chromium جدا + باز کردن همیشه تهران."""
    from ..chromium_profile import create_and_open
    name = _profile_name(req.name)
    phone = (req.phone or "").strip()
    if phone and not (phone.startswith("09") and len(phone) == 11 and phone.isdigit()):
        raise HTTPException(400, "شماره باید ۱۱ رقم و با ۰۹ شروع شود (یا خالی بماند)")
    try:
        res = create_and_open(ACCOUNTS_DIR, name, phone)
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    mgr().set_status(name, "active", note="پروفایل ساخته شد — لاگین دیوار در Chromium")
    log("info", f"پروفایل Chromium «{name}» ساخته شد و تهران باز شد")
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
        log("success", f"پروفایل «{name}» ذخیره شد")
    else:
        mgr().set_site_verified(name, False)
        log("warning", f"ذخیره پروفایل «{name}»: لاگین دیده نشد")
    return res


@app.post("/api/accounts/profile/open")
def accounts_profile_open(req: ProfileReq):
    from ..chromium_profile import HOME_URL, open_profile
    name = _profile_name(req.name)
    try:
        res = open_profile(ACCOUNTS_DIR, name, HOME_URL)
    except Exception as e:
        raise HTTPException(400, str(e)) from e
    log("info", f"پروفایل Chromium «{name}» روی تهران باز شد")
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
def categories_get():
    from ..categories import public_list
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
    from ..pricing import million_to_toman
    added = store.keywords_add(
        DB_PATH, req.keyword, req.cities, req.category,
        price_min=million_to_toman(req.price_min),
        price_max=million_to_toman(req.price_max),
        vip=bool(req.vip))
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


# ------------------------------------------------------------- API پیام‌ها --
@app.get("/api/templates")
def templates_get():
    chat = store.template_get(DB_PATH, "chat") or {"text": DEFAULTS["chat_template"]}
    sms = store.template_get(DB_PATH, "sms") or {"text": DEFAULTS["chat_template"]}
    return {"chat": chat["text"], "sms": sms["text"]}


@app.post("/api/templates")
def templates_set(req: TemplateUpdate):
    if req.channel not in ("chat", "sms"):
        raise HTTPException(400, "channel باید chat یا sms باشد")
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
              "chat_auto_on_new", "chat_auto_daily_limit", "chat_auto_delay_sec",
              "per_account_daily_limit", "adaptive_until_captcha",
              "ip_daily_limit", "phone_delay_sec"):
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
    """روشن/خاموش کردن ارسال خودکار چت دیوار — همان لحظه روی مانیتور اعمال می‌شود."""
    store.settings_set(DB_PATH, "chat_auto_on_new", bool(req.on))
    _apply_sms_to_monitor()
    if req.on:
        log("warning", "ارسال خودکار چت روشن شد — پرریسک؛ سقف/تأخیر را رعایت کنید")
        return {"ok": True, "on": True, "ready": True,
                "message": "ارسال خودکار چت روشن شد — به محض «فقط چت»، پیام چت می‌رود"}
    log("info", "ارسال خودکار چت خاموش شد")
    return {"ok": True, "on": False, "ready": False,
            "message": "ارسال خودکار چت خاموش شد — فقط نیمه‌خودکار"}


class ChatSend(BaseModel):
    token: str


@app.post("/api/leads/{token}/chat")
def lead_send_chat(token: str):
    """ارسال دستی/آزمایشی همان قالب چت به سرنخ فقط‌چت با اکانت لاگین‌شده."""
    from ..chat import compose_chat, send_divar_chat
    from ..db import bump_quota, now as _now
    con = connect(DB_PATH)
    try:
        row = con.execute("SELECT * FROM leads WHERE token=?", (token,)).fetchone()
        if not row:
            raise HTTPException(404, "سرنخ پیدا نشد")
        if row["phone_status"] != "hidden":
            raise HTTPException(400, "این سرنخ فقط‌چت نیست (شماره دارد)")
        m = mgr()
        name = m.pick(DB_PATH)
        if not name:
            raise HTTPException(400, "اکانت آمادهٔ لاگین‌شده نیست — اول اکانت اضافه کنید")
        cl = DivarClient(session_path=str(m.session_path(name)), base_url=_base_url())
        tpl = (store.template_get(DB_PATH, "chat") or {}).get("text") or ""
        text = compose_chat(tpl, dict(row))
        r = send_divar_chat(cl, token, text)
        st = "sent" if r.get("ok") else "requires_operator"
        try:
            con.execute(
                "UPDATE leads SET chat_status=?, lead_status=? WHERE token=?",
                (st, "contacted" if r.get("ok") else "new", token))
            if r.get("ok"):
                bump_quota(con, "chats")
                con.execute("UPDATE leads SET lead_status='contacted' WHERE token=?",
                            (token,))
            con.commit()
        except Exception:
            pass
        log("success" if r.get("ok") else "warning",
            f"چت {token[:16]}: {r.get('message')}")
        return r
    finally:
        con.close()


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
        "chat_today": q.get("chats", 0),
        "ip_daily_limit": store.settings_all(DB_PATH).get("ip_daily_limit", 240),
        "sms_auto_on_new": bool(store.settings_all(DB_PATH).get("sms_auto_on_new")),
        "sms_ready": sms_ready(store.settings_all(DB_PATH))[0],
        "chat_auto_on_new": bool(store.settings_all(DB_PATH).get("chat_auto_on_new")),
        "chat_auto_daily_limit": store.settings_all(DB_PATH).get("chat_auto_daily_limit", 20),
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
        else:
            where, args = "1=1", ()
        rows = con.execute(
            f"SELECT token,title,subtitle,description,phone,phone_status,keyword,"
            f"matched_keywords,city,lead_status,chat_status,sms_status,url,first_seen_at,"
            f"phone_checked_at,last_error FROM leads WHERE {where} "
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
        else:
            where = "1=1"
        rows = con.execute(
            f"SELECT token,title,subtitle,description,phone,phone_status,keyword,"
            f"matched_keywords,city,lead_status,chat_status,sms_status,url,"
            f"first_seen_at,phone_checked_at,published_at,sms_sent_at "
            f"FROM leads WHERE {where} "
            f"ORDER BY id DESC").fetchall()
    finally:
        con.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["توکن", "عنوان", "توضیح میانی", "متن", "شماره تماس", "وضعیت شماره",
                "کلمه کلیدی", "کلمات منطبق", "شهر", "وضعیت پیگیری", "وضعیت چت",
                "وضعیت پیامک", "لینک", "تاریخ‌ساعت کشف", "تاریخ‌ساعت استخراج شماره",
                "زمان انتشار آگهی", "تاریخ‌ساعت ارسال پیامک"])
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
                    "UPDATE leads SET sms_status='sent', sms_sent_at=? WHERE token=?",
                    (_now(), token))
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


class ChatTest(BaseModel):
    token: str = ""


@app.post("/api/chat/test")
def chat_test(req: ChatTest):
    """آزمایش ارسال چت: توکن بدهید یا اولین سرنخ فقط‌چت را خودش پیدا می‌کند."""
    from ..chat import compose_chat, send_divar_chat
    token = (req.token or "").strip()
    con = connect(DB_PATH)
    try:
        if not token:
            row = con.execute(
                "SELECT token FROM leads WHERE phone_status='hidden' AND "
                "lead_status='new' ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                return {"ok": False, "status": "none",
                        "message": "سرنخ فقط‌چت‌ی برای آزمایش نیست — اول مانیتور را اجرا کنید"}
            token = row["token"]
        row = con.execute("SELECT * FROM leads WHERE token=?", (token,)).fetchone()
        if not row:
            raise HTTPException(404, "سرنخ پیدا نشد")
        m = mgr()
        name = m.pick(DB_PATH)
        if not name:
            raise HTTPException(400, "اکانت آمادهٔ لاگین‌شده نیست")
        cl = DivarClient(session_path=str(m.session_path(name)), base_url=_base_url())
        tpl = (store.template_get(DB_PATH, "chat") or {}).get("text") or ""
        text = compose_chat(tpl, dict(row))
        r = send_divar_chat(cl, token, text)
        r["preview"] = text
        r["token"] = token
        r["account"] = name
        log("success" if r.get("ok") else "warning",
            f"تست چت {token[:16]}: {r.get('message')}")
        return r
    finally:
        con.close()


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
