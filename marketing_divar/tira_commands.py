# -*- coding: utf-8 -*-
"""تیرا v4 — طبقه‌بند دستور + اجرای واقعی (نه فقط راهنما).

هدف: کاربر به زبان طبیعی بگوید چه می‌خواهد؛ تیرا انجام بدهد:
- راهنمای پنل پیامکی / ربات‌ها
- ست کردن متن پیامک و چت
- پایش کل یک دسته (مثلاً همه موبایل‌ها) بدون شکارچی
- استخراج شماره + ارسال پیامک/چت
- شکار کالاهای غیرمعمول مثل جاروبرقی
- تشخیص اتصال ملی‌پیامک
- دریافت همان دستورها از تلگرام / بله / روبیکا
- خبر پاسخ فروشنده (به‌خصوص موبایل) روی روبیکا
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .matching import normalize


# ─── کالا → دسته دیوار ──────────────────────────────────────────────
# (کلمات، اسلاگ، خانواده شکار، عنوان فارسی)
PRODUCT_MAP: List[Tuple[Tuple[str, ...], str, str, str]] = [
    (("جاروبرقی", "جارو برقی", "vacuum", "جارو"), "vacuum-cleaner", "appliance", "جاروبرقی"),
    (("لباسشویی", "ماشین لباسشویی"), "washers", "appliance", "ماشین لباسشویی"),
    (("یخچال", "فریزر", "ساید"), "refrigerator-freezer", "appliance", "یخچال و فریزر"),
    (("کولر", "اسپلیت", "پکیج", "بخاری"), "heating-cooling", "appliance", "سرمایش و گرمایش"),
    (("آیفون", "iphone"), "apple", "phone", "آیفون / اپل"),
    (("سامسونگ", "گلکسی", "samsung"), "samsung", "phone", "سامسونگ"),
    (("شیائومی", "xiaomi", "redmi", "poco", "ردمی"), "xiaomi", "phone", "شیائومی"),
    (("گوشی", "موبایل", "تلفن همراه", "موبایل‌ها", "موبایلا"), "mobile-phones", "phone", "موبایل"),
    (("تبلت", "آیپد"), "tablet", "phone", "تبلت"),
    (("لپ تاپ", "لپ‌تاپ", "لپتاپ", "laptop", "مک بوک", "مک‌بوک"), "laptops", "laptop", "لپ‌تاپ"),
    (("پراید", "پژو", "سمند", "دنا", "تیبا", "شاهین", "خودرو", "ماشین"), "light", "vehicle", "خودرو سواری"),
    (("موتور", "موتورسیکلت"), "motorcycles", "vehicle", "موتورسیکلت"),
]


def _db_path() -> str:
    return os.environ.get("DIVAR_DB_PATH", "data/divar_leads.db")


def guess_product(text: str) -> Dict[str, str]:
    """از متن آزاد، کالا و دسته را حدس می‌زند (جاروبرقی هم شامل)."""
    n = normalize(text or "")
    raw = text or ""
    for words, slug, family, title in PRODUCT_MAP:
        if any(normalize(w) in n or w in raw for w in words):
            return {"slug": slug, "family": family, "title": title, "keyword": words[0]}
    return {"slug": "", "family": "generic", "title": "", "keyword": ""}


def extract_template_body(text: str) -> str:
    """متن قالب را از دستور «بذار / بگذار / این باشه / :» جدا می‌کند."""
    t = (text or "").strip()
    for sep in ("بگذار", "بذار", "ست کن", "این باشه", "باشه:", "برابر", "="):
        if sep in t:
            part = t.split(sep, 1)[-1].strip(" :«»\"'\n\t")
            if len(part) >= 3:
                return part
    # بعد از «متن پیامک» یا «قالب پیامک»
    m = re.search(
        r"(?:متن|قالب)\s*(?:پیامک|چت|اس‌ام‌اس|sms|chat)?\s*[:：]\s*(.+)$",
        t, re.I | re.S)
    if m and len(m.group(1).strip()) >= 3:
        return m.group(1).strip(" «»\"'")
    return ""


def classify_intent(text: str, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """قبل از گفتگوی شکار، دستور اجرایی / راهنما / پایش دسته را تشخیص می‌دهد."""
    t = (text or "").strip()
    if not t:
        return {"kind": ""}
    n = normalize(t)
    low = t.lower()
    state = state or {}
    step = str(state.get("step") or "start")
    in_hunt = step not in ("start", "guide_sms", "system_control", "done", "")

    prod = guess_product(t)

    # 1) راهنمای پیامک / اتصال ملی‌پیامک — حتی جمله بلند
    sms_words = ("پیامک", "sms", "ملی پیامک", "ملی‌پیامک", "melipayamak",
                 "خط خدماتی", "پترن", "پنل پیامک", "پنل پیامکی")
    guide_words = ("چطور", "چگونه", "راهنما", "راهنمایی", "تنظیم", "وصل",
                   "متصل", "اتصال", "ستاپ", "setup", "کمک")
    if any(w in n or w in low for w in sms_words) and any(w in n for w in guide_words):
        return {"kind": "guide_sms", "product": prod}
    if any(p in n for p in ("چطور پیامک", "چگونه پیامک", "پنل پیامکی",
                            "وصل کنم", "متصلش کنم", "متصل کنم")):
        return {"kind": "guide_sms", "product": prod}

    # 2) وضعیت / تشخیص اتصال پیامک
    if any(w in n for w in ("وضعیت پیامک", "اتصال پیامک", "وصل هست", "کامل هست",
                            "ملی پیامک اوکی", "sms ready", "بررسی پیامک")):
        return {"kind": "sms_status"}

    # 3) قالب پیامک / چت — اجرایی
    wants_set = any(w in n for w in ("بذار", "بگذار", "ست کن", "این باشه", "عوض کن"))
    if ("قالب پیامک" in n or "متن پیامک" in n or "متن sms" in low
            or "پیامک این" in n) and (wants_set or ":" in t or "=" in t or extract_template_body(t)):
        return {"kind": "set_sms_template", "text": extract_template_body(t)}
    if ("قالب چت" in n or "متن چت" in n or "متن چت دیوار" in n) and (
            wants_set or ":" in t or extract_template_body(t)):
        return {"kind": "set_chat_template", "text": extract_template_body(t)}

    # 4) روشن/خاموش ارسال خودکار
    if any(w in n for w in ("پیامک خودکار", "ارسال خودکار پیامک", "خودکار پیامک")):
        on = not any(w in n for w in ("خاموش", "غیرفعال", "قطع"))
        return {"kind": "enable_sms", "on": on}
    if any(w in n for w in ("چت خودکار", "ارسال خودکار چت")):
        on = not any(w in n for w in ("خاموش", "غیرفعال", "قطع"))
        return {"kind": "enable_chat", "on": on}

    # 5) ربات‌ها
    if any(w in n for w in ("روبیکا", "بله", "تلگرام", "ربات")) and any(
            w in n for w in ("دستور", "پیام", "وصل", "دریافت", "چطور", "راهنما")):
        return {"kind": "guide_bots"}

    # 6) پایش دسته — همه موبایل‌ها / شماره‌ها را بکش / پیام بده (نه شکارچی)
    browse_marks = (
        "هرچی", "هر چی", "همه ", "همه‌", "دسته‌بندی", "دسته بندی", "دسته ",
        "شماره هاشون", "شماره‌هاشون", "شماره ها را", "شماره‌ها را",
        "بکش بیرون", "بکشیم بیرون", "آگهی ها", "آگهی‌ها",
        "پیام بره", "پیام بده", "پیام بدیم", "پیامک بره", "پیامک بده",
    )
    wants_browse = any(m in n or m in t for m in browse_marks)
    wants_sms_send = any(w in n for w in ("پیام بره", "پیام بده", "پیام بدیم",
                                          "پیامک", "اس ام اس", "sms"))
    wants_numbers = any(w in n for w in ("شماره", "موبایل هست", "استخراج"))
    if wants_browse and (prod.get("slug") or "موبایل" in n or "گوشی" in n):
        slug = prod.get("slug") or "mobile-phones"
        title = prod.get("title") or "موبایل"
        return {
            "kind": "browse_category",
            "category": slug,
            "title": title,
            "send_sms": wants_sms_send or wants_numbers,
            "send_chat": "چت" in n,
            "hunter": "شکار" in n,
            "product": prod,
        }

    # 7) شروع / توقف مانیتور
    if any(w in n for w in ("مانیتور را روشن", "اسکن را شروع", "شروع اسکن",
                            "موتور را روشن", "پایش را شروع")):
        return {"kind": "start_monitor"}
    if any(w in n for w in ("مانیتور را خاموش", "توقف اسکن", "بایست")):
        return {"kind": "stop_monitor"}

    # 8) قیمت روز
    if any(w in n for w in ("قیمت روز", "قیمتش چنده", "چند می ارزه", "ترب")):
        return {"kind": "price", "query": t, "product": prod}

    # 9) وسط گفتگوی شکار — دستور کنترل را قطع نکن؛ بقیه را ادامه بده
    if in_hunt:
        return {"kind": "continue"}

    # 10) شکار / کالای مشخص (جاروبرقی، آیفون، …)
    if prod.get("slug") or any(w in n for w in ("شکار", "شکارچی", "بگرد")):
        return {"kind": "hunt", "product": prod}

    return {"kind": ""}


def sms_connection_report(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """آیا اتصال ملی‌پیامک برای کاری که می‌خواهیم کامل است؟"""
    from .sms import sms_ready

    if cfg is None:
        try:
            from .store import settings_all
            cfg = settings_all(_db_path())
        except Exception:
            cfg = {}
    cfg = cfg or {}
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    provider = (cfg.get("sms_provider") or "none")
    add("سرویس‌دهنده", provider == "melipayamak",
        "ملی‌پیامک" if provider == "melipayamak" else f"الان: {provider} — باید melipayamak باشد")

    user = (cfg.get("sms_username") or "").strip()
    pwd = (cfg.get("sms_password") or cfg.get("sms_api_key") or "").strip()
    add("نام کاربری و رمز", bool(user and pwd),
        "ذخیره شده" if user and pwd else "در تب تنظیمات وارد کنید")

    use_pat = bool(cfg.get("sms_use_pattern"))
    bodyid = (cfg.get("sms_pattern_bodyid") or "").strip()
    line = (cfg.get("sms_line_number") or "").strip()
    if use_pat:
        add("پترن (خط خدماتی)", bool(bodyid),
            f"bodyId={bodyid}" if bodyid else "کد پترن خالی است — در پنل ملی‌پیامک ثبت و تأیید کنید")
        add("متن پترن", bool((cfg.get("sms_pattern_text") or "").strip()),
            "متن پترن در برنامه هست" if cfg.get("sms_pattern_text") else "اختیاری — برای کپی به پنل")
    else:
        add("خط اختصاصی", bool(line),
            line if line else "شماره خط ارسال خالی است — یا پترن را روشن کنید")

    ready, why = sms_ready(cfg)
    add("sms_ready", ready, why)

    tpl = ""
    try:
        from .store import template_get
        rec = template_get(_db_path(), "sms") or {}
        tpl = rec.get("text") or ""
    except Exception:
        tpl = ""
    add("قالب پیامک", bool(tpl.strip()),
        "قالب ذخیره شده" if tpl.strip() else "در تب پیام‌ها قالب بگذارید یا به تیرا بگویید")

    auto = bool(cfg.get("sms_auto_on_new"))
    add("ارسال خودکار", auto,
        "روشن — به محض شماره، پیامک می‌رود" if auto else "خاموش — تیک را بزنید یا به تیرا بگویید روشن کند")

    inbox = bool(cfg.get("sms_inbox_on", True))
    add("صندوق پاسخ", inbox,
        "پولینگ GetMessages روشن است" if inbox else "خاموش است — پاسخ فروشنده خوانده نمی‌شود")

    missing = [c["name"] for c in checks if not c["ok"]]
    complete = ready and provider == "melipayamak" and bool(user and pwd)
    work_ok = complete and (auto or True)  # ارسال دستی حتی بدون auto کار می‌کند
    msg_lines = ["وضعیت اتصال ملی‌پیامک:"]
    for c in checks:
        mark = "✓" if c["ok"] else "✗"
        msg_lines.append(f"{mark} {c['name']}: {c['detail']}")
    if complete and auto:
        msg_lines.append("\nبرای کاری که می‌خواهید (استخراج شماره + پیامک خودکار) اتصال کامل و آماده است.")
    elif complete and not auto:
        msg_lines.append("\nاتصال API اوکی است، ولی ارسال خودکار خاموش است — بگویید «پیامک خودکار را روشن کن».")
    else:
        msg_lines.append("\nهنوز کامل نیست. موارد ✗ را طبق راهنما پر کنید.")
    return {
        "ok": complete,
        "ready": ready,
        "auto": auto,
        "work_ready": work_ok and auto,
        "checks": checks,
        "missing": missing,
        "message": "\n".join(msg_lines),
        "why": why,
    }


def apply_category_watch(category: str, keyword: str = "", *,
                         hunter: bool = False, vip: bool = False,
                         send_sms: bool = True, sms_text: str = "",
                         chat_text: str = "",
                         db_path: str = "") -> Dict[str, Any]:
    """پایش دسته (browse) — همه آگهی‌های آن دسته، نه فقط شکارچی."""
    db_path = db_path or _db_path()
    from .store import keywords_add, settings_set, template_set

    cat = category or ""
    kw = keyword or ""
    if cat == "vacuum-cleaner" and not kw:
        kw = "جاروبرقی"

    added = keywords_add(
        db_path, keyword=kw, category=cat,
        hunter=bool(hunter), vip=bool(vip))
    actions = [f"پایش دسته «{category}» اضافه شد (شکارچی={'روشن' if hunter else 'خاموش'})"]
    if send_sms:
        settings_set(db_path, "sms_provider", "melipayamak")
        settings_set(db_path, "sms_auto_on_new", True)
        settings_set(db_path, "sms_inbox_on", True)
        actions.append("ارسال خودکار پیامک روشن شد")
    if sms_text:
        template_set(db_path, "sms", sms_text)
        actions.append("قالب پیامک ست شد")
    if chat_text:
        template_set(db_path, "chat", chat_text)
        actions.append("قالب چت ست شد")
    report = sms_connection_report()
    return {
        "ok": True,
        "added": added,
        "category": category,
        "hunter": hunter,
        "actions": actions,
        "sms": report,
    }


def execute_intent(intent: Dict[str, Any], agent: Any = None,
                   db_path: str = "") -> Optional[Dict[str, Any]]:
    """اجرای دستور تشخیص‌داده‌شده. None = بگذار ایجنت شکار ادامه دهد."""
    kind = (intent or {}).get("kind") or ""
    if not kind or kind in ("hunt", "continue", ""):
        return None
    db_path = db_path or _db_path()

    if kind == "guide_sms":
        from .tira_agent import get_system_guide
        guide = get_system_guide("sms")
        report = sms_connection_report()
        reply = guide + "\n\n—— وضعیت فعلی اتصال ——\n" + report["message"]
        return {"reply": reply, "step": "guide_sms", "guide": "sms",
                "sms": report, "kind": kind}

    if kind == "guide_bots":
        reply = (
            "📡 **دستور تیرا از ربات‌ها**\n\n"
            "تیرا همان دستورهای پنل را از تلگرام، بله و روبیکا هم می‌گیرد "
            "اگر توکن و شناسه گفتگو در تنظیمات ذخیره شده باشد.\n\n"
            "• تلگرام: BotFather → توکن → Chat ID خودتان\n"
            "• بله: بازوی بله → توکن → شناسه گفتگو (عدد، نه شناسه بازو)\n"
            "• روبیکا: پنل بات روبیکا → توکن → chat_id\n\n"
            "بعد از ذخیره، دکمه «بررسی اتصال» را بزنید. پیام «ارتباط برقرار شد» باید برسد.\n\n"
            "در ربات می‌توانید بنویسید:\n"
            "— «همه موبایل‌ها را بگیر و پیامک بده»\n"
            "— «چطور پنل پیامکی را تنظیم کنم؟»\n"
            "— «متن پیامک را بگذار سلام {title}»\n"
            "— /status /leads /all /alerts /export مثل قبل کار می‌کنند.\n\n"
            "اگر فروشنده موبایل جواب داد، خبر همان لحظه روی روبیکا (و بقیه کانال‌های روشن) می‌آید."
        )
        return {"reply": reply, "step": "guide_bots", "kind": kind}

    if kind == "sms_status":
        report = sms_connection_report()
        return {"reply": report["message"], "step": "sms_status",
                "sms": report, "kind": kind}

    if kind == "set_sms_template":
        body = (intent.get("text") or "").strip()
        if len(body) < 3:
            return {"reply": "متن قالب پیامک را کامل بگو. مثلاً:\n"
                             "متن پیامک را بگذار سلام، آگهی «{title}» را در {city} دیدم.",
                    "step": "ask_sms_template", "kind": kind}
        from .store import template_set
        template_set(db_path, "sms", body)
        return {"reply": f"✅ قالب پیامک ذخیره شد:\n«{body[:180]}»",
                "step": "system_control", "kind": kind,
                "action": {"type": "template_set", "channel": "sms"}}

    if kind == "set_chat_template":
        body = (intent.get("text") or "").strip()
        if len(body) < 3:
            return {"reply": "متن قالب چت را کامل بگو. مثلاً:\n"
                             "متن چت را بگذار {greeting} آگهی «{title}» را دیدم. {closing}",
                    "step": "ask_chat_template", "kind": kind}
        from .store import template_set
        template_set(db_path, "chat", body)
        return {"reply": f"✅ قالب چت ذخیره شد:\n«{body[:180]}»",
                "step": "system_control", "kind": kind,
                "action": {"type": "template_set", "channel": "chat"}}

    if kind == "enable_sms":
        on = bool(intent.get("on", True))
        from .store import settings_set
        settings_set(db_path, "sms_auto_on_new", on)
        if on:
            settings_set(db_path, "sms_provider", "melipayamak")
        report = sms_connection_report()
        extra = ""
        if on and not report.get("ready"):
            extra = "\n⚠️ خودکار روشن شد ولی هنوز آماده نیست:\n" + report["message"]
        return {"reply": ("✅ ارسال خودکار پیامک روشن شد." if on else "✅ ارسال خودکار پیامک خاموش شد.") + extra,
                "step": "system_control", "kind": kind, "sms": report,
                "action": {"type": "sms_auto", "on": on}}

    if kind == "enable_chat":
        on = bool(intent.get("on", True))
        from .store import settings_set
        settings_set(db_path, "chat_auto_on_new", on)
        return {"reply": "✅ چت خودکار روشن شد." if on else "✅ چت خودکار خاموش شد.",
                "step": "system_control", "kind": kind,
                "action": {"type": "chat_auto", "on": on}}

    if kind == "browse_category":
        cat = intent.get("category") or "mobile-phones"
        title = intent.get("title") or cat
        hunter = bool(intent.get("hunter"))
        send_sms = bool(intent.get("send_sms", True))
        res = apply_category_watch(
            cat, keyword="", hunter=hunter, send_sms=send_sms, db_path=db_path)
        sms = res.get("sms") or {}
        lines = [
            f"✅ پایش دسته «{title}» ({cat}) ثبت شد — "
            + ("با شکارچی" if hunter else "بدون شکارچی؛ همه آگهی‌های این دسته"),
            "موتور آگهی‌ها را می‌گردد، شماره را می‌کشد، و اگر پیامک خودکار روشن باشد همان لحظه پیام می‌فرستد.",
            "",
            "برای اجرا: اکانت دیوار را لاگین کنید و مانیتور را از داشبورد روشن کنید.",
        ]
        if send_sms:
            if sms.get("ready") and sms.get("auto"):
                lines.append("✉️ اتصال ملی‌پیامک آماده است — پیامک خودکار می‌رود.")
            else:
                lines.append("✉️ پیامک خودکار را روشن کردم، ولی اتصال هنوز کامل نیست:")
                lines.append(sms.get("message") or "")
        return {"reply": "\n".join(lines), "step": "browse_done",
                "kind": kind, "config": res, "sms": sms,
                "ready": True, "browse": True}

    if kind == "price":
        from .tira_agent import research_any_product
        q = intent.get("query") or ""
        prod = intent.get("product") or {}
        kw = prod.get("keyword") or q
        res = research_any_product(kw)
        prices = res.get("prices") or []
        pt = "\n".join(
            f"• {p.get('model')}: {p.get('price_million')} میلیون ({p.get('source')})"
            for p in prices[:8]
        ) or "قیمت اینترنتی پیدا نشد — بدون نت هم شکارچی با میانه آگهی کار می‌کند."
        msg = (f"🔍 «{kw}» — دسته {prod.get('title') or res.get('type')}\n\n"
               f"{res.get('market_note','')}\n\n{pt}")
        return {"reply": msg, "step": "price_info", "research": res, "kind": kind}

    if kind == "start_monitor":
        return {"reply": "برای شروع اسکن از داشبورد دکمه «شروع» را بزن "
                         "(اول کلمه/دسته و اکانت لازم است). "
                         "اگر بخواهی دسته موبایل را همین حالا ست کنم بگو «همه موبایل‌ها را بگیر».",
                "step": "start_monitor", "kind": kind}

    if kind == "stop_monitor":
        return {"reply": "توقف مانیتور از داشبورد با دکمه توقف است. "
                         "اگر دستور مشخص‌تری داری بگو.",
                "step": "stop_monitor", "kind": kind}

    return None


def is_mobile_lead(lead: Optional[Dict[str, Any]]) -> bool:
    if not lead:
        return False
    blob = " ".join(str(lead.get(k) or "") for k in
                    ("category", "keyword", "title", "family")).lower()
    n = normalize(blob)
    return any(w in n or w in blob for w in (
        "mobile", "phone", "apple", "samsung", "xiaomi",
        "موبایل", "گوشی", "ایفون", "آیفون", "سامسونگ", "شیائومی", "گلکسی"))


def format_reply_alert(lead: Dict[str, Any], body: str,
                       nlu: Optional[Dict[str, Any]], channel: str) -> str:
    title = str(lead.get("title") or "")[:70]
    phone = str(lead.get("phone") or "")
    intent = (nlu or {}).get("intent") or ""
    summary = (nlu or {}).get("summary_fa") or ""
    lines = [
        "📩 پاسخ فروشنده آمد",
        f"کانال: {channel}",
        f"آگهی: {title or '—'}",
    ]
    if phone:
        lines.append(f"شماره: {phone}")
    if body:
        lines.append(f"متن: {(body or '')[:240]}")
    if summary or intent:
        lines.append(f"تحلیل تیرا: {summary or intent}")
    return "\n".join(lines)


def notify_seller_reply(lead: Dict[str, Any], body: str,
                        nlu: Optional[Dict[str, Any]] = None,
                        channel: str = "sms",
                        cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """خبر پاسخ — برای موبایل حتماً روبیکا (اگر وصل باشد) + بقیه کانال‌ها."""
    out = {"sent": [], "mobile": is_mobile_lead(lead)}
    try:
        from . import store
        from .config import load_config
        from .notifier import notify, rubika_configured, send_rubika
        cfg = cfg or store.effective_config(_db_path(), load_config())
        text = format_reply_alert(lead, body, nlu, channel)
        if out["mobile"]:
            text = "📱 پاسخ آگهی موبایل\n" + text
            if rubika_configured(cfg):
                if send_rubika(cfg, text):
                    out["sent"].append("rubika")
        notify(cfg, text, important=True)
        out["sent"].append("notify")
    except Exception as e:
        out["error"] = str(e)
    return out


def handle_tira_from_bot(text: str, db_path: str = "",
                         session_id: str = "bot") -> str:
    """ورودی ربات تلگرام/بله/روبیکا → پاسخ تیرا."""
    from .tira_agent import get_tira_agent
    prev = os.environ.get("DIVAR_DB_PATH")
    if db_path:
        os.environ["DIVAR_DB_PATH"] = db_path
    try:
        ag = get_tira_agent(session_id)
        if not ag.state.get("messages"):
            ag.start()
        res = ag.handle_user(text or "")
        return str(res.get("reply") or "متوجه نشدم. مثلاً بگو «همه موبایل‌ها را بگیر و پیامک بده».")
    except Exception as e:
        return f"تیرا الان نتوانست جواب بدهد: {e}"
    finally:
        if db_path:
            if prev is None:
                os.environ.pop("DIVAR_DB_PATH", None)
            else:
                os.environ["DIVAR_DB_PATH"] = prev
