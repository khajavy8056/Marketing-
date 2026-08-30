# -*- coding: utf-8 -*-
"""درک پاسخ چت/پیامک — قاعده اول، مدل محلی فقط اگر مبهم باشد + حافظه + رویداد.

این نسخه کاملاً تعاملی است مثل n8n:
- هر تحلیل → حافظه (nlu_memory) به‌روز می‌شود تا درکش اضافه شود
- هر تحلیل → رویداد reply_received → شکارچی دوباره امتیاز می‌دهد
- تنظیمات پیشرفته (hunter_profile) در پرامپت اعمال می‌شود
- مدل نقش ثابت دارد (nlu_role.ROLE_FA) و فقط JSON می‌دهد

مدل پیام بازاریابی بعدی را نمی‌فرستد؛ فقط intent/slots می‌دهد.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from .matching import normalize
from .nlu_role import reply_prompt
from .pricing import parse_toman

INTENTS = (
    "price_quote", "defect_admit", "gone", "scam_deposit", "negotiate",
    "available_yes", "available_no", "refuse_discount", "greeting",
    "question", "unclear",
)

_GONE = ("فروخته", "فروختم", "رفته", "موجود نیست", "دیگه نیست", "کنسل",
         "لغو شد", "حذف شد", "تمام شد")
_DEFECT = ("معیوب", "معيوب", "شکسته", "تعمیره", "تعمیر میخواد", "ترک داره",
           "اوراق", "سالم نیست", "ایراد داره")
_DEPOSIT = ("بیعانه", "بیعانه بده", "کارت به کارت", "شبا بده", "اول واریز")
_YES = ("بله", "آره", "اره", "موجوده", "هست هنوز", "در خدمتم", "اوکی")
_NO = ("نه", "نیست", "ندارم", "نمیفروشم")
_REFUSE = ("تخفیف نداره", "تخفیف نمیدم", "قیمت همینه", "سر قیمت")
_GREET = ("سلام", "درود", "خوبی", "وقت بخیر")
_QUESTION = ("چنده", "کجایی", "کی میای", "عکس بده", " hol")


def _slots_price(text: str) -> Optional[int]:
    n = parse_toman(text)
    if n and n >= 10_000:
        return n
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(میلیون|ملیون)", text or "")
    if m:
        try:
            return int(float(m.group(1).replace(",", ".")) * 1_000_000)
        except ValueError:
            return None
    return None


def analyze_rules(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    n = normalize(raw)
    if not n:
        return {"intent": "unclear", "confidence": 0.2, "slots": {},
                "summary_fa": "متن خالی", "source": "rules"}

    slots: Dict[str, Any] = {
        "price_toman": None, "price_kind": None, "condition": "unknown",
        "wants_deposit": False, "deadline": None,
    }
    intent = "unclear"
    conf = 0.4

    if any(normalize(w) in n for w in _DEPOSIT):
        intent, conf = "scam_deposit", 0.92
        slots["wants_deposit"] = True
    if any(normalize(w) in n for w in _GONE):
        intent, conf = "gone", 0.93
    if any(normalize(w) in n for w in _DEFECT):
        if intent not in ("gone", "scam_deposit"):
            intent, conf = "defect_admit", 0.9
        slots["condition"] = "defective"

    price = _slots_price(raw)
    if price:
        slots["price_toman"] = price
        slots["price_kind"] = "cash"
        if intent in ("unclear", "greeting", "available_yes", "negotiate"):
            intent, conf = "price_quote", 0.88
        elif intent == "defect_admit":
            conf = 0.86

    if intent == "unclear":
        if any(normalize(w) in n for w in _REFUSE):
            intent, conf = "refuse_discount", 0.75
        elif any(normalize(w) in n for w in _YES) and "نه" not in n[:8]:
            intent, conf = "available_yes", 0.7
        elif any(normalize(w) in n for w in _NO):
            intent, conf = "available_no", 0.7
        elif "?" in raw or "؟" in raw:
            intent, conf = "question", 0.65
        elif any(normalize(w) in n for w in _GREET) and len(n) < 40:
            intent, conf = "greeting", 0.7
        elif "بیا پایین" in n or "چانه" in n or "توافق" in n:
            intent, conf = "negotiate", 0.6

    summaries = {
        "price_quote": "قیمت نقد اعلام شد",
        "defect_admit": "کالا معیوب/تعمیری است",
        "gone": "آگهی دیگر موجود نیست",
        "scam_deposit": "درخواست بیعانه — مشکوک",
        "negotiate": "مذاکره بدون عدد قطعی",
        "available_yes": "هنوز موجود است",
        "available_no": "موجود نیست / رد",
        "refuse_discount": "تخفیف نمی‌دهد",
        "greeting": "سلام بدون اطلاعات",
        "question": "سؤال برگشتی",
        "unclear": "نیاز به خواندن",
    }
    return {
        "intent": intent,
        "confidence": conf,
        "slots": slots,
        "summary_fa": summaries.get(intent, "نیاز به خواندن"),
        "source": "rules",
        "raw": raw[:800],
    }


_LLM_PROMPT = (
    "تو فقط طبقه‌بند پاسخ کوتاه فارسی آگهی هستی. JSON بده نه حرف اضافه.\n"
    "intent یکی از: price_quote, defect_admit, gone, scam_deposit, negotiate, "
    "available_yes, available_no, refuse_discount, greeting, question, unclear\n"
    "اگر بیعانه خواست scam_deposit. قول معامله نساز.\n"
    "خروجی: {{\"intent\":\"...\",\"confidence\":0.0,\"price_toman\":null,"
    "\"condition\":\"unknown|new|used|defective\",\"wants_deposit\":false,"
    "\"summary_fa\":\"یک خط\"}}\n"
    "متن:\n{text}\n"
)


def _parse_llm_json(blob: str) -> Optional[Dict[str, Any]]:
    if not blob:
        return None
    t = blob.strip()
    m = re.search(r"\{.*\}", t, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    intent = str(data.get("intent") or "unclear")
    if intent not in INTENTS:
        intent = "unclear"
    try:
        conf = float(data.get("confidence") or 0.5)
    except (TypeError, ValueError):
        conf = 0.5
    price = data.get("price_toman")
    try:
        price = int(price) if price not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        price = None
    return {
        "intent": intent,
        "confidence": max(0.0, min(1.0, conf)),
        "slots": {
            "price_toman": price,
            "price_kind": "cash" if price else None,
            "condition": str(data.get("condition") or "unknown"),
            "wants_deposit": bool(data.get("wants_deposit")),
            "deadline": None,
        },
        "summary_fa": str(data.get("summary_fa") or "")[:160] or "تحلیل مدل محلی",
        "source": "local_llm",
        "raw": "",
    }


def analyze(text: str, use_llm: bool = True, keyword: str = "", category: str = "") -> Dict[str, Any]:
    """قاعده همیشه. مدل محلی فقط اگر اطمینان < 0.75 و فایل مدل موجود باشد.
    
    با حافظه گره خورده: اگر کلمه/دسته داده شود، پرامپت با حافظه غنی می‌شود.
    """
    base = analyze_rules(text)
    # اگر اطمینان بالا یا LLM خاموش → همان قاعده + حافظه
    if base["confidence"] >= 0.75 or not use_llm:
        # حتی در این حالت حافظه برای یادگیری
        try:
            from .nlu_memory import remember_reply
            # ذخیره نمی‌کنیم چون هنوز token نداریم، ولی stats
        except Exception:
            pass
        return base
    try:
        from .nlu_model import is_ready, infer_json
        from .nlu_memory import enrich_prompt_with_memory
        if not is_ready():
            base["needs_human"] = True
            return base
        # پرامپت با حافظه غنی می‌شود — هر بار که کاربر چیزی اضافه می‌کند درک اضافه می‌شود
        prompt_base = reply_prompt(text or "")
        prompt = enrich_prompt_with_memory(prompt_base, keyword=keyword, category=category)
        raw = infer_json(prompt)
        parsed = _parse_llm_json(raw)
        if not parsed:
            base["needs_human"] = True
            base["llm_raw"] = raw[:500]
            return base
        parsed["raw"] = (text or "")[:800]
        parsed["llm_raw"] = raw[:500]
        if parsed["confidence"] < 0.45:
            parsed["needs_human"] = True
        # اگر مدل بهتر از قاعده بود، آن را بده
        if parsed["confidence"] > base["confidence"]:
            return parsed
        return base
    except Exception as e:
        base["needs_human"] = True
        base["error"] = str(e)[:200]
        return base


def analyze_for_platform(text: str, platform: str = "divar",
                         use_llm: bool = True, keyword: str = "", category: str = "") -> Dict[str, Any]:
    """همان تحلیل برای دیوار/شیپور/رینگ — زبان پاسخ فارسی است."""
    out = analyze(text, use_llm=use_llm, keyword=keyword, category=category)
    out["platform"] = str(platform or "divar")
    # رویداد — مدل فعال است
    try:
        from .events import emit
        emit("reply_received", {
            "platform": out["platform"],
            "intent": out.get("intent"),
            "confidence": out.get("confidence"),
            "text": text[:200],
            "source": out.get("source"),
        })
    except Exception:
        pass
    return out


def apply_to_lead(con, token: str, result: Dict[str, Any],
                  context: str = "marketing") -> Dict[str, Any]:
    """وضعیت سرنخ را از intent به‌روز می‌کند — پیام آزاد نمی‌فرستد."""
    intent = result.get("intent") or "unclear"
    slots = result.get("slots") or {}
    acted = "none"
    try:
        con.execute(
            "UPDATE leads SET last_reply_intent=?, last_reply_at=datetime('now'), "
            "lead_status=CASE WHEN lead_status IN ('new','contacted') "
            "THEN 'replied' ELSE lead_status END WHERE token=?",
            (intent, token))
        if intent == "gone":
            con.execute(
                "UPDATE leads SET phone_status='removed', removed_reason='gone' "
                "WHERE token=?", (token,))
            acted = "removed"
        elif intent == "defect_admit":
            con.execute(
                "UPDATE leads SET is_defect=1, hunter_level='', vip=0 WHERE token=?",
                (token,))
            acted = "defect"
        elif intent == "scam_deposit":
            con.execute(
                "UPDATE leads SET hunter_level='suspicious', vip=0 WHERE token=?",
                (token,))
            acted = "scam"
        elif intent == "price_quote" and slots.get("price_toman") and context == "inquire":
            price = int(slots["price_toman"])
            con.execute(
                "UPDATE leads SET price=?, price_kind='cash', inquiry_status='answered' "
                "WHERE token=?", (price, token))
            acted = "price"
        if context == "inquire" or intent in ("price_quote", "available_yes", "defect_admit"):
            _apply_hunter_reply(con, token, result)
        con.commit()
    except Exception:
        acted = "error"
    result = dict(result)
    result["acted"] = acted
    # حافظه و رویداد
    try:
        from .nlu_memory import remember_reply
        remember_reply(token, intent, float(result.get("confidence") or 0),
                       text=result.get("raw") or "", slots=slots)
    except Exception:
        pass
    try:
        from .events import emit
        emit("reply_received", {
            "token": token,
            "intent": intent,
            "confidence": result.get("confidence"),
            "acted": acted,
            "context": context,
        })
    except Exception:
        pass
    return result


def _apply_hunter_reply(con, token: str, result: Dict[str, Any]) -> None:
    """اسلات پروفایل از پاسخ فروشنده + امتیاز دوباره شکارچی."""
    try:
        row = con.execute("SELECT * FROM leads WHERE token=?", (token,)).fetchone()
        if not row:
            return
        from .hunter import collect_samples, evaluate
        from .hunter_profile import default_profile, fill_from_reply, merge_overrides
        keyword = row["keyword"] if "keyword" in row.keys() else ""
        adv: Dict[str, Any] = {}
        cat = ""
        try:
            kwrow = con.execute(
                "SELECT category, hunter_adv FROM keywords WHERE keyword=?",
                (keyword,)).fetchone()
            if kwrow:
                cat = kwrow["category"] or ""
                raw = kwrow["hunter_adv"] or ""
                if raw:
                    adv = json.loads(raw)
        except Exception:
            pass
        prof = merge_overrides(default_profile(cat, keyword), adv)
        text = result.get("raw") or ""
        filled = fill_from_reply(text, prof)
        chassis = filled.get("chassis") or (
            row["chassis"] if "chassis" in row.keys() else "")
        paint = filled.get("paint") or (
            row["paint"] if "paint" in row.keys() else "")
        year = filled.get("year") or (
            row["car_year"] if "car_year" in row.keys() else 0)
        km = filled.get("mileage_km") or (
            row["mileage_km"] if "mileage_km" in row.keys() else 0)
        price = filled.get("price_toman") or (
            row["price"] if "price" in row.keys() else 0)
        extra = {
            "title": row["title"] if "title" in row.keys() else "",
            "chassis": chassis, "paint": paint,
            "hunter_flags": filled.get("flags") or {},
            "category": cat, "keyword": keyword,
            "is_defect": bool(row["is_defect"]) if "is_defect" in row.keys() else False,
            "is_placeholder": False,
            "is_buyer": bool(row["is_buyer"]) if "is_buyer" in row.keys() else False,
        }
        city = row["city"] if "city" in row.keys() else ""
        plat = row["platform"] if "platform" in row.keys() else "divar"
        samples = collect_samples(con, keyword, city, plat)
        sc = evaluate(int(price or 0), samples, extra=extra, profile=prof, text=text)
        level = sc.get("level") or ""
        if result.get("intent") == "defect_admit":
            level = ""
        try:
            con.execute(
                "UPDATE leads SET chassis=?, paint=?, car_year=?, mileage_km=?, "
                "hunter_level=?, hunter_adj_pct=?, hunter_questions=?, "
                "inquiry_status=CASE WHEN inquiry_status IN ('pending','sent') "
                "THEN 'answered' ELSE inquiry_status END WHERE token=?",
                (str(chassis or ""), str(paint or ""), int(year or 0), int(km or 0),
                 level, float(sc.get("adj_pct") or 0),
                 str(sc.get("questions") or "")[:400], token))
        except Exception:
            con.execute(
                "UPDATE leads SET chassis=?, paint=? WHERE token=?",
                (str(chassis or ""), str(paint or ""), token))
        # رویداد شکارچی
        try:
            from .events import emit
            emit("hunter_evaluated", {
                "token": token,
                "level": level,
                "price": price,
                "chassis": chassis,
                "paint": paint,
            })
        except Exception:
            pass
    except Exception:
        return
