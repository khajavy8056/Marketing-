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

app = FastAPI(title="خواجوی لید — دیوار لید", version="1.8.0")

# --------------------------------------------------------- وضعیت سراسری --
_state: Dict[str, Any] = {
    "monitor": None,        # نمونه Monitor در حال اجرا
    "thread": None,         # نخ اجرایی مانیتور
    "started_at": None,
    "pending_logins": {},   # name -> phone (بین دو مرحله OTP)
    "include_existing": False,
}


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
    return {"accounts": mgr().snapshot(DB_PATH)}


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
    mgr().set_status(name, "active", note="")
    log("success", f"اکانت «{name}» با موفقیت لاگین شد ({phone})")
    return {"ok": True, "message": "لاگین موفق"}


@app.post("/api/accounts/action")
def accounts_action(req: AccountAction):
    m = mgr()
    if not m.has_token(req.name):
        raise HTTPException(404, "چنین اکانتی لاگین نشده است")
    if req.action == "release":
        m.release(req.name)
        log("info", f"اکانت «{req.name}» آزاد شد")
    elif req.action == "disable":
        m.set_status(req.name, "disabled")
        log("info", f"اکانت «{req.name}» غیرفعال شد")
    elif req.action == "enable":
        m.set_status(req.name, "active", note="")
    return {"ok": True}


# --------------------------------------------------------- API کلمات کلیدی --
@app.get("/api/categories")
def categories_get():
    from ..categories import public_list
    return {"categories": public_list()}


@app.get("/api/keywords")
def keywords_get():
    return {"keywords": store.keywords_list(DB_PATH)}


@app.post("/api/keywords")
def keywords_add(req: KeywordAdd):
    if not (req.keyword or "").strip() and not (req.category or "").strip():
        raise HTTPException(400, "کلمه کلیدی یا دسته‌بندی دیوار را انتخاب کنید")
    added = store.keywords_add(DB_PATH, req.keyword, req.cities, req.category)
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
              "sms_line_number", "sms_auto_on_new", "sms_daily_limit"):
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


# ------------------------------------------------------------ API مانیتور --
@app.post("/api/monitor/start")
def monitor_start(req: MonitorStart):
    if _state["thread"] and _state["thread"].is_alive():
        raise HTTPException(409, "مانیتور از قبل در حال اجراست")
    specs = store.keywords_active_specs(DB_PATH)
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
        breakdown = {
            "total": total_leads,
            "new": _cnt("phone_status='pending'"),
            "matched": total_leads,
            "processing": _cnt("phone_status='processing'"),
            "contact_found": found,
            "no_contact": _cnt("phone_status='hidden'"),
            "failed": _cnt("phone_status='error'"),
        }
        acc_snap = mgr().snapshot(DB_PATH)
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
        "sms_ready": sms_ready(store.settings_all(DB_PATH))[0],
        "data_dir": os.environ.get("DIVAR_DATA_DIR") or str(Path(DB_PATH).resolve().parent),
        "breakdown": breakdown, "accounts_breakdown": acc_break,
        "accounts": acc_snap,
        "keywords": store.keywords_list(DB_PATH),
        "logs": logging_util.recent(50),
        "stats_by_keyword": st,
    }


@app.post("/api/monitor/pause")
def monitor_pause():
    mon = _state.get("monitor")
    if mon:
        mon.paused = not mon.paused
        log("info", "مانیتور " + ("متوقف موقت شد" if mon.paused else "ادامه یافت"))
        return {"ok": True, "paused": mon.paused}
    raise HTTPException(404, "مانیتور در حال اجرا نیست")


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
            f"phone_checked_at FROM leads WHERE {where} "
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
    """ربات تلگرام ادمین — فقط اگر توکن ذخیره شده باشد درخواست می‌زند."""
    from ..telegram_bot import start_bot

    def _cfg():
        return store.effective_config(DB_PATH, load_config())

    def _st():
        mon = _state.get("monitor")
        return {"running": bool(_state.get("thread") and _state["thread"].is_alive()),
                "tick": mon.tick if mon else 0}

    start_bot(_cfg, DB_PATH, _st)


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
        r = send_melipayamak(user, pwd, req.to.strip(), line, "تست خواجوی لید")
    else:
        r = credit_melipayamak(user, pwd)
    log("info" if r.get("ok") else "error",
        f"ملی‌پیامک: {r.get('message')}")
    return r


@app.post("/api/telegram/test")
def telegram_test():
    from ..notifier import notify
    from ..telegram_bot import build_status_text
    cfg = store.effective_config(DB_PATH, load_config())
    mon = _state.get("monitor")
    running = bool(_state.get("thread") and _state["thread"].is_alive())
    text = build_status_text(DB_PATH, cfg, running=running,
                             tick=mon.tick if mon else 0)
    tok = ((cfg.get("notify") or {}).get("telegram_bot_token") or "")
    if ":" in tok:
        notify(cfg, text)
    return {"ok": True, "preview": text}


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


@app.get("/", response_class=HTMLResponse)
def index():
    return (_STATIC / "index.html").read_text(encoding="utf-8")
