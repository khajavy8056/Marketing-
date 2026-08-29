# -*- coding: utf-8 -*-
"""درک پاسخ چت/پیامک — قاعده اول، مدل محلی فقط اگر مبهم باشد.

مدل پیام بازاریابی بعدی را نمی‌فرستد؛ فقط intent/slots می‌دهد.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from .matching import normalize
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
    # «بیست و پنج میلیون» ساده
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
            conf = 0.86  # هر دو اسلات پر

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


def analyze(text: str, use_llm: bool = True) -> Dict[str, Any]:
    """قاعده همیشه. مدل محلی فقط اگر اطمینان < 0.75 و فایل مدل موجود باشد."""
    base = analyze_rules(text)
    if base["confidence"] >= 0.75 or not use_llm:
        return base
    try:
        from .nlu_model import is_ready, infer_json
        if not is_ready():
            base["needs_human"] = True
            return base
        raw = infer_json(_LLM_PROMPT.format(text=(text or "")[:600]))
        parsed = _parse_llm_json(raw)
        if not parsed:
            base["needs_human"] = True
            return base
        parsed["raw"] = (text or "")[:800]
        if parsed["confidence"] < 0.45:
            parsed["needs_human"] = True
        return parsed
    except Exception:
        base["needs_human"] = True
        return base


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
        con.commit()
    except Exception:
        acted = "error"
    result = dict(result)
    result["acted"] = acted
    return result
