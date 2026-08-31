# -*- coding: utf-8 -*-
"""مذاکره‌گر حرفه‌ای شکارچی — تعامل انسانی، چندمرحله‌ای، ضد تشخیص ربات.

اهداف:
- استعلام جای خالی (سال، کارکرد، شاسی، رنگ، باتری، ...) با لحن انسانی
- مذاکره قیمت بعد از اینکه فهمیدیم شکار است
- فروشنده متوجه ربات نشود — لحن عامیانه، مودب، تهرانی، نه دلال
- در نهایت VIP آلارم با قیمت مذاکره‌شده

وضعیت‌ها:
- inquiry: سوال اولیه برای پر کردن جای خالی
- negotiating: چانه‌زنی
- negotiated: توافق نهایی
- vip: شکار قطعی با قیمت نهایی

مدل محلی (Qwen) اگر آماده باشد استفاده می‌شود، وگرنه fallback قاعده‌ای.
"""

from __future__ import annotations

import json
import random
import re
from typing import Any, Dict, List, Optional, Tuple

from .hunter_profile import build_questions, default_profile


# لحن‌های انسانی برای تنوع — هر بار یکی
_GREETINGS = [
    "سلام، وقت بخیر",
    "سلام بزرگوار، وقتتون بخیر",
    "درود، وقت بخیر",
    "سلام عزیز، وقت بخیر",
    "سلام، خسته نباشید",
]

_CLOSINGS = [
    "ممنون از وقتی که می‌ذارید 🙏",
    "لطف می‌کنید جواب بدید",
    "ممنون می‌شم راهنمایی کنید",
    "سپاس 🌹",
    "ممنون از لطفتون",
]

_NEGOTIATION_OPENERS = [
    "ممنون بابت اطلاعات کامل 🙏",
    "خیلی لطف کردید بابت توضیحات",
    "ممنون، خیلی واضح بود",
]

_MARKET_REFERENCES = [
    "من چند مورد مشابه دیدم، قیمت‌ها حول و حوش {market} بود",
    "توی بازار همین مدل حدود {market} می‌چرخه",
    "راستش من چندتا آگهی مشابه چک کردم، حدود {market} بودن",
]


def _random_greeting() -> str:
    return random.choice(_GREETINGS)


def _random_closing() -> str:
    return random.choice(_CLOSINGS)


def _format_price(p: int) -> str:
    if not p or p <= 0:
        return "نامشخص"
    if p >= 1_000_000_000:
        return f"{p/1_000_000_000:.2f} میلیارد"
    if p >= 1_000_000:
        return f"{p/1_000_000:.0f} میلیون"
    return f"{p:,} تومان"


def _is_model_ready() -> bool:
    try:
        from .nlu_model import is_ready, backend_name

        # اگر backend fallback-smart است، برای مذاکره انسانی fallback قاعده‌ای بهتر است
        # تا پیام JSON ندهد — پس ready را False برمی‌گردانیم تا قاعده‌ای استفاده شود
        bn = backend_name()
        if bn == "fallback-smart":
            return False
        return bool(is_ready())
    except Exception:
        return False


def _infer(prompt: str) -> str:
    try:
        from .nlu_model import backend_name, is_ready

        if backend_name() == "fallback-smart":
            return ""
    except Exception:
        pass
    try:
        from .nlu_model import infer_json

        # infer_json JSON می‌دهد، اما ما متن آزاد می‌خواهیم — از infer_text اگر هست
        from .nlu_model import infer_text  # type: ignore

        return infer_text(prompt)
    except ImportError:
        try:
            from .nlu_model import infer_json

            raw = infer_json(prompt)
            # اگر JSON بود (fallback هوشمند)، خالی برگردان تا قاعده‌ای استفاده شود
            if raw.strip().startswith("{") and "\"intent\"" in raw:
                return ""
            # اگر JSON بود، سعی کن متن داخلش را بکشی
            m = re.search(r'"message"\s*:\s*"([^"]+)"', raw)
            if m:
                return m.group(1)
            m = re.search(r'"text"\s*:\s*"([^"]+)"', raw)
            if m:
                return m.group(1)
            # اگر هنوز JSON است، خالی
            if raw.strip().startswith("{"):
                return ""
            return raw
        except Exception:
            return ""
    except Exception:
        return ""


def generate_inquiry_message(
    profile: Dict[str, Any],
    missing: List[str],
    title: str = "",
    extra: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    پیام استعلام جای خالی — انسانی، کوتاه، مودب.
    اگر مدل آماده باشد، با پرامپت حرفه‌ای تولید می‌شود.
    """
    extra = extra or {}
    # سوالات ثابت از پروفایل
    questions_text = build_questions(profile, missing, title)

    # اگر مدل آماده نیست — fallback انسانی
    if not _is_model_ready() or not questions_text:
        greet = _random_greeting()
        close = _random_closing()
        # سوالات را به فارسی روان تبدیل کن
        qs = []
        for i, key in enumerate(missing[:3], 1):
            # از پروفایل سوال را بکش
            slot = next((s for s in (profile.get("slots") or []) if s.get("key") == key), None)
            adj = next((a for a in (profile.get("adjustments") or []) if a.get("key") == key), None)
            q = (slot or adj or {}).get("question") or key
            qs.append(f"{i}) {q}")
        body = "\n".join(qs) if qs else "می‌شه لطفاً جزئیات بیشتری بفرمایید؟"
        if title:
            return f"{greet} 🌹\nبرای آگهی «{title[:50]}»:\n{body}\n{close}"
        return f"{greet}\n{body}\n{close}"

    # مدل آماده — پرامپت حرفه‌ای
    # نقش: خریدار معمولی، نه دلال، تهرانی، مودب، کوتاه
    prompt = (
        "تو یک خریدار معمولی و مودب ایرانی هستی، نه دلال، نه ربات. "
        "وظیفه: از روی سوالات ثابت زیر، یک پیام کوتاه، طبیعی، عامیانه ولی مودب برای فروشنده بنویس. "
        "لحن: خودمانی، تهرانی، با احترام، بدون اینکه بگی ربات هستی. "
        "از ایموجی خیلی کم استفاده کن (حداکثر یکی). "
        "سوالات را عوض نکن، فقط مودبانه پشت هم بگذار. قیمت نساز، معامله نبند.\n"
        "سوالات ثابت:\n"
        f"{questions_text}\n"
        f"عنوان آگهی: {title[:60]}\n"
        "فقط متن پیام را بده، بدون توضیح اضافه.\n"
    )
    # اگر تاریخچه داریم، اضافه کن
    if history:
        last = history[-2:]  # دو پیام آخر
        hist_txt = "\n".join(f"{'فروشنده' if h.get('role')=='seller' else 'من'}: {h.get('text','')[:100]}" for h in last)
        prompt += f"\nگفتگوی قبلی:\n{hist_txt}\n"

    txt = _infer(prompt)
    if not txt or len(txt.strip()) < 10:
        # fallback
        greet = _random_greeting()
        return f"{greet}\n{questions_text}\n{_random_closing()}"
    # تمیزکاری
    txt = txt.strip()
    # حذف ``` و ...
    txt = re.sub(r"^```.*?\n", "", txt, flags=re.S)
    txt = re.sub(r"\n```$", "", txt)
    # اگر خیلی طولانی شد، کوتاه کن
    if len(txt) > 400:
        txt = txt[:400].rsplit(" ", 1)[0] + "…"
    return txt


def generate_negotiation_message(
    context: Dict[str, Any],
    history: Optional[List[Dict[str, Any]]] = None,
    stage: str = "opener",
) -> str:
    """
    پیام مذاکره — انسانی، مرحله‌ای.

    stage:
    - opener: تشکر + اشاره به بازار + سوال تخفیف
    - offer: پیشنهاد قیمت پایین‌تر
    - final: پیشنهاد نهایی + آمادگی برای معامله

    context: price, fair, healthy_median, discount_pct, flags, title, product, etc.
    """
    price = int(context.get("price") or context.get("original_price") or 0)
    fair = int(context.get("fair") or context.get("fair_price") or 0)
    healthy = int(context.get("healthy_median") or context.get("market_median") or 0)
    discount = context.get("discount_pct") or 0
    title = str(context.get("title") or "")[:50]

    # قیمت هدف برای پیشنهاد — 5-10% پایین‌تر از قیمت فعلی اگر شکار است
    target_offer = price
    if price and fair:
        # اگر 20% زیر fair است، 5% دیگر چانه بزن
        if discount and discount >= 15:
            target_offer = int(price * 0.95)
        elif discount and discount >= 8:
            target_offer = int(price * 0.93)
        else:
            target_offer = int(price * 0.90)
    elif price:
        target_offer = int(price * 0.92)

    market_txt = _format_price(healthy or fair or price)

    if not _is_model_ready():
        # fallback قاعده‌ای — خیلی انسانی
        greet = _random_greeting()
        if stage == "opener":
            ref = random.choice(_MARKET_REFERENCES).format(market=market_txt)
            return (
                f"{greet}\n"
                f"{random.choice(_NEGOTIATION_OPENERS)}، {ref}. "
                f"برای آگهی «{title}» قیمتتون مقداری قابل مذاکره هست؟ "
                f"{_random_closing()}"
            )
        elif stage == "offer":
            return (
                f"{greet}\n"
                f"ممنون بابت پاسختون. راستش بودجه من حدود {_format_price(target_offer)} هست. "
                f"اگر براتون مقدوره با این قیمت معامله کنیم، من امروز نقد آماده‌ام. "
                f"{_random_closing()}"
            )
        else:  # final
            return (
                f"{greet}\n"
                f"خیلی ممنون از وقتی که گذاشتید. من می‌تونم تا {_format_price(target_offer)} نقد همین امروز اقدام کنم. "
                f"اگر موافقید بفرمایید تا هماهنگ کنیم. "
                f"{_random_closing()}"
            )

    # مدل آماده — پرامپت مذاکره حرفه‌ای
    history_txt = ""
    if history:
        hist_lines = []
        for h in history[-4:]:
            role = "فروشنده" if h.get("role") == "seller" else "من (خریدار)"
            hist_lines.append(f"{role}: {h.get('text','')[:120]}")
        history_txt = "\n".join(hist_lines)

    if stage == "opener":
        prompt = (
            "تو یک خریدار واقعی، مودب، تهرانی، نه دلال هستی. می‌خوای برای یک آگهی که قیمتش مناسب است، "
            "خیلی طبیعی و انسانی سوال کنی آیا تخفیف دارد. لحن خودمانی، محترمانه، کوتاه. "
            "از اصطلاحات عامیانه ملایم استفاده کن (مثلاً «بزرگوار»، «لطف می‌کنید»). "
            "نباید بگی ربات هستی. نباید قیمت جدید پیشنهاد بدی، فقط بپرس قابل مذاکره است.\n"
            f"عنوان: {title}\n"
            f"قیمت آگهی: {_format_price(price)}\n"
            f"قیمت بازار سالم: {market_txt}\n"
            f"تخفیف نسبت به منصفانه: {discount}%\n"
            f"گفتگوی قبلی:\n{history_txt}\n"
            "فقط متن پیام را بده، حداکثر 2 جمله، بدون توضیح اضافه."
        )
    elif stage == "offer":
        prompt = (
            "تو خریدار جدی هستی، بودجه محدود داری، می‌خوای پیشنهاد قیمت پایین‌تر بدی ولی مودبانه و منطقی. "
            "لحن انسانی، تهرانی، نه دلال. بگو بودجه‌ات چقدر است و نقد آماده‌ای. "
            "قیمت پیشنهادی را خیلی پایین نگو، فقط 5-8% کمتر از قیمت آگهی.\n"
            f"عنوان: {title}\n"
            f"قیمت فعلی: {_format_price(price)}\n"
            f"پیشنهاد تو: {_format_price(target_offer)}\n"
            f"گفتگو:\n{history_txt}\n"
            "فقط پیام پیشنهاد را بده، کوتاه، مودب، با یک دلیل منطقی (مثلاً بودجه، مقایسه بازار)."
        )
    else:  # final
        prompt = (
            "تو خریدار جدی هستی که می‌خوای معامله را نهایی کنی. یک پیشنهاد نهایی مودبانه بده، "
            "بگو نقد امروز آماده‌ای، اگر موافق است هماهنگ کنید. لحن خیلی انسانی، صمیمی ولی محترم.\n"
            f"عنوان: {title}\n"
            f"قیمت نهایی پیشنهادی: {_format_price(target_offer)}\n"
            f"گفتگو:\n{history_txt}\n"
            "فقط متن نهایی را بده، کوتاه، با احترام."
        )

    txt = _infer(prompt)
    if not txt or len(txt.strip()) < 10:
        # fallback
        return generate_negotiation_message(context, history, stage="opener" if _is_model_ready() else stage)

    txt = txt.strip()
    txt = re.sub(r"^```.*?\n", "", txt, flags=re.S)
    txt = re.sub(r"\n```$", "", txt)
    if len(txt) > 450:
        txt = txt[:450].rsplit(" ", 1)[0] + "…"
    return txt


def analyze_negotiation_reply(text: str) -> Dict[str, Any]:
    """تحلیل پاسخ فروشنده در مذاکره."""
    from .matching import normalize
    from .pricing import parse_toman

    n = normalize(text or "")
    out: Dict[str, Any] = {
        "agreed": False,
        "refused": False,
        "new_price": None,
        "needs_human": False,
        "sentiment": "neutral",  # positive, negative, neutral
    }

    price = parse_toman(text)
    if price and price >= 10_000:
        out["new_price"] = price

    # توافق
    if any(w in n for w in ("باشه", "قبوله", "اوکی", "اوکیه", "حله", "بیا", "باشه میشه", "موردی نیست")):
        out["agreed"] = True
        out["sentiment"] = "positive"
    # رد
    if any(w in n for w in ("نه", "نمیشه", "نمی‌شه", "تخفیف نداره", "قیمت همینه", "زیر قیمت نمیدم")):
        out["refused"] = True
        out["sentiment"] = "negative"
        if out["agreed"]:
            out["agreed"] = False  # اگر هر دو بود، رد غالب است

    if any(w in n for w in ("ممنون", "لطف", "بزرگوار", "عزیز")):
        out["sentiment"] = "positive" if out["sentiment"] != "negative" else out["sentiment"]

    return out


def should_start_negotiation(evaluation: Dict[str, Any]) -> bool:
    """آیا مذاکره ارزش دارد؟"""
    level = evaluation.get("level") or evaluation.get("raw_level") or ""
    discount = evaluation.get("discount_pct") or 0
    confidence = evaluation.get("confidence") or 0.5
    warm = evaluation.get("warm", False)

    if not warm:
        return False
    if level in ("great", "good"):
        return confidence >= 0.5
    if level == "market" and discount and discount >= 5:
        # نزدیک به good — با مذاکره می‌تواند good شود
        return confidence >= 0.6
    return False


def should_continue_negotiation(history: List[Dict[str, Any]], evaluation: Dict[str, Any]) -> Tuple[bool, str]:
    """ادامه مذاکره؟ و مرحله بعدی چیست؟"""
    if not history:
        return True, "opener"
    # تعداد دورها
    buyer_msgs = [h for h in history if h.get("role") != "seller"]
    if len(buyer_msgs) >= 3:
        return False, "final"  # بیش از 3 پیام خریدار → تمام

    last_seller = next((h for h in reversed(history) if h.get("role") == "seller"), None)
    if not last_seller:
        return True, "opener"

    analysis = analyze_negotiation_reply(last_seller.get("text") or "")
    if analysis.get("agreed"):
        return False, "negotiated"
    if analysis.get("refused") and len(buyer_msgs) >= 2:
        return False, "refused"

    # مرحله بعدی
    if len(buyer_msgs) == 1:
        return True, "offer"
    return True, "final"


def build_vip_payload(
    token: str,
    title: str,
    original_price: int,
    negotiated_price: Optional[int],
    fair_price: int,
    healthy_median: int,
    discount_pct: Optional[float],
    level: str,
    flags: Dict[str, bool],
    confidence: float,
    market: Dict[str, Any],
    negotiation_history: List[Dict[str, Any]],
    url: str = "",
    phone: str = "",
    city: str = "",
) -> Dict[str, Any]:
    """ساخت payload برای VIP آلارم ویژه."""
    final_price = negotiated_price or original_price
    final_discount = discount_pct
    if fair_price and final_price:
        final_discount = round((fair_price - final_price) / fair_price * 100.0, 1)

    # خلاصه مذاکره
    neg_summary = ""
    if negotiation_history:
        # آخرین 2-3 پیام
        last = negotiation_history[-3:]
        neg_summary = " | ".join(f"{'فروشنده' if h.get('role')=='seller' else 'من'}: {h.get('text','')[:60]}" for h in last)

    return {
        "token": token,
        "title": title[:80],
        "original_price": int(original_price or 0),
        "negotiated_price": int(negotiated_price or 0) if negotiated_price else None,
        "final_price": int(final_price or 0),
        "fair_price": int(fair_price or 0),
        "healthy_median": int(healthy_median or 0),
        "discount_pct": final_discount,
        "level": level,
        "flags": flags,
        "confidence": confidence,
        "market": market,
        "negotiation_history": negotiation_history,
        "neg_summary": neg_summary,
        "url": url,
        "phone": phone,
        "city": city,
        "is_vip": True,
        "vip_reason": f"شکار {level} — {final_discount}% زیر منصفانه" if final_discount else f"شکار {level}",
    }
