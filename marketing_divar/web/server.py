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
from ..db import chat_queue, connect, pending_phone, quota_today, stats
from ..monitor import Monitor

DB_PATH = os.environ.get("DIVAR_DB_PATH", "data/divar_leads.db")
ACCOUNTS_DIR = os.environ.get("DIVAR_ACCOUNTS_DIR", "data/accounts")
def _base_url():
    """آدرس پایه دیوار (برای تست: متغیر محیطی DIVAR_BASE_URL)."""
    return os.environ.get("DIVAR_BASE_URL")

logging_util.setup()
log = logging_util.log

app = FastAPI(title="دیوار لید — سیستم جمع‌آوری سرنخ", version="1.0")

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
    keyword: str            # می‌تواند «a,b,c» باشد
    cities: Optional[List[int]] = None


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
@app.get("/api/keywords")
def keywords_get():
    return {"keywords": store.keywords_list(DB_PATH)}


@app.post("/api/keywords")
def keywords_add(req: KeywordAdd):
    added = store.keywords_add(DB_PATH, req.keyword, req.cities)
    log("info", f"کلمات کلیدی اضافه شد: {req.keyword}")
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


@app.post("/api/settings")
def settings_update(req: SettingsUpdate):
    saved = [k for k, v in req.values.items() if store.settings_set(DB_PATH, k, v)]
    log("info", f"تنظیمات ذخیره شد: {', '.join(saved)}")
    return {"ok": True, "saved": saved}


# ------------------------------------------------------------ API مانیتور --
@app.post("/api/monitor/start")
def monitor_start(req: MonitorStart):
    if _state["thread"] and _state["thread"].is_alive():
        raise HTTPException(409, "مانیتور از قبل در حال اجراست")
    specs = store.keywords_active_specs(DB_PATH)
    if not specs:
        raise HTTPException(400, "اول حداقل یک کلمه کلیدی فعال اضافه کنید")
    if not mgr().list_accounts():
        raise HTTPException(400, "اول حداقل یک اکانت لاگین کنید")

    cfg = store.effective_config(DB_PATH, load_config())
    # گزینه «موارد موجود هم گرفته شوند؟»
    if not req.include_existing:
        con = connect(DB_PATH)
        with con:
            con.execute("UPDATE leads SET phone_status='legacy' "
                        "WHERE phone_status='pending'")
        con.close()
        log("info", "حالت «فقط آگهی‌های جدید» — سرنخ‌های قدیمی نادیده گرفته شدند")
    else:
        log("info", "حالت «موارد موجود هم گرفته شوند» فعال شد")

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
        total_leads = con.execute("SELECT COUNT(*) c FROM leads").fetchone()["c"]
        found = con.execute(
            "SELECT COUNT(*) c FROM leads WHERE phone_status='found'").fetchone()["c"]
    finally:
        con.close()
    return {
        "running": running, "started_at": _state.get("started_at"),
        "tick": mon.tick if mon else 0, "paused": mon.paused if mon else False,
        "queue": queue_len, "chat_queue": chat_len, "total_leads": total_leads,
        "phones_found": found, "phones_today": q["phones"],
        "searches_today": q["searches"],
        "accounts": mgr().snapshot(DB_PATH),
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
            f"SELECT token,title,subtitle,phone,phone_status,keyword,city,"
            f"lead_status,url,first_seen_at FROM leads WHERE {where} "
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
            f"SELECT token,title,subtitle,phone,phone_status,keyword,city,"
            f"lead_status,url,first_seen_at FROM leads WHERE {where} "
            f"ORDER BY id DESC").fetchall()
    finally:
        con.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["توکن", "عنوان", "توضیح", "شماره تماس", "وضعیت شماره",
                "کلمه کلیدی", "شهر", "وضعیت پیگیری", "لینک", "زمان"])
    for r in rows:
        w.writerow(list(r))
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition":
                 f"attachment; filename=leads_{filter}_{time.strftime('%Y%m%d')}.csv"})


# ------------------------------------------------------------ صفحه اصلی --
_STATIC = Path(__file__).parent / "static"


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
