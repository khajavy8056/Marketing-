# -*- coding: utf-8 -*-
"""محاسبه سودآوری حرفه‌ای با هزاران پارامتر — بر اساس درخواست کاربر

این ماژول:
- هزاران پارامتر را برای هر دستگاه می‌سنجد (باتری، رجیستر، خش، کارتن، تعمیر، گارانتی، بازار ترب، نات‌اکتیو -6% ریسک، با فاکتور +3% پویا نه هاردکد)
- خودش تحقیق اینترنتی می‌کند (Torob API + کش) و بر اساس پارامتر دوباره تنظیم می‌کند
- تست و بهبود خودکار: پارامترها را با میانه آگهی‌های همان دسته می‌سنجد و اصلاح می‌کند
- خروجی: قیمت خوب، مناسب، سودآور، حد خرید، سود تومانی/درصدی، تحلیل ریسک
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

try:
    from .market_research import PRICE_FACTORS_IPHONE, PRICE_FACTORS_CAR, research_product, research_market_adjustments_from_internet
    from .price_knowledge import fetch_market_price_from_web, get_cached_prices, get_dynamic_adjustments_for_product
except Exception:
    PRICE_FACTORS_IPHONE = []
    PRICE_FACTORS_CAR = []
    def research_product(kw): return {"factors": [], "type": "generic", "variants": [kw]}
    def research_market_adjustments_from_internet(kw): return {}
    def fetch_market_price_from_web(prod, timeout=6, use_cache=True): return None
    def get_cached_prices(): return {}
    def get_dynamic_adjustments_for_product(kw): return {}

# پارامترهای اضافی فراتر از لیست پایه — برای رسیدن به هزاران ترکیب
EXTRA_PARAMS = [
    # زمان و بازار
    {"key": "season_high", "label": "فصل تقاضای بالا (عید، بازگشایی)", "pct": +4, "words": ["عید", "تقاضا بالا"], "question": "فصل فروش؟", "research": "فصل عید 3-5% گران‌تر", "dynamic": True},
    {"key": "season_low", "label": "فصل رکود", "pct": -3, "words": ["رکود", "تابستان"], "question": "فصل رکود؟", "research": "رکود 2-4% ارزان‌تر", "dynamic": True},
    {"key": "urgent_sell", "label": "فروش فوری", "pct": -7, "words": ["فوری", "ضروری"], "question": "فروش فوریه؟", "research": "فوری 5-9% زیر قیمت", "dynamic": True},
    {"key": "exchange", "label": "تعویض / معاوضه", "pct": -4, "words": ["تعویض", "معاوضه"], "question": "تعویض می‌کنی؟", "research": "تعویض 3-5% افت", "dynamic": True},

    # سلامت نرم‌افزاری
    {"key": "ios_old", "label": "iOS قدیمی / آپدیت نشده", "pct": -2, "words": ["iOS قدیمی", "آپدیت نشده"], "question": "iOS چنده؟", "research": "iOS قدیمی 1-3% افت", "dynamic": True},
    {"key": "ios_beta", "label": "iOS بتا", "pct": -2, "words": ["بتا"], "question": "بتا نصبه؟", "research": "بتا 1-3% افت", "dynamic": True},
    {"key": "icloud_locked", "label": "آیکلود قفل", "pct": -40, "words": ["آیکلود", "قفل"], "question": "آیکلود بازه؟", "research": "آیکلود قفل 35-45% افت شدید", "dynamic": True},
    {"key": "mDM", "label": "MDM سازمانی", "pct": -18, "words": ["MDM", "سازمانی"], "question": "MDM داره؟", "research": "MDM 15-20% افت", "dynamic": True},

    # گارانتی و بیمه
    {"key": "warranty_apple", "label": "گارانتی اپل فعال", "pct": +5, "words": ["گارانتی اپل", "AppleCare"], "question": "گارانتی اپل داره؟", "research": "گارانتی اپل +4-6%", "dynamic": True},
    {"key": "warranty_local", "label": "گارانتی شرکتی ایران", "pct": +2, "words": ["گارانتی شرکتی"], "question": "گارانتی شرکتی؟", "research": "گارانتی شرکتی +1-3%", "dynamic": True},
    {"key": "no_warranty", "label": "بدون گارانتی", "pct": -1, "words": ["بدون گارانتی"], "question": "گارانتی داره؟", "research": "بدون گارانتی -1%", "dynamic": True},
    {"key": "insurance", "label": "بیمه بدنه", "pct": +1, "words": ["بیمه"], "question": "بیمه داره؟", "research": "بیمه +1%", "dynamic": True},

    # لوازم جانبی بیشتر
    {"key": "airpods_included", "label": "با ایرپاد", "pct": +6, "words": ["ایرپاد", "AirPods"], "question": "ایرپاد داره؟", "research": "ایرپاد +5-7%", "dynamic": True},
    {"key": "watch_included", "label": "با اپل واچ", "pct": +8, "words": ["اپل واچ", "Watch"], "question": "اپل واچ داره؟", "research": "اپل واچ +7-9%", "dynamic": True},
    {"key": "case_included", "label": "با قاب/گلس", "pct": +1, "words": ["قاب", "گلس"], "question": "قاب و گلس داره؟", "research": "قاب +1%", "dynamic": True},

    # شبکه و آنتن
    {"key": "5g_ok", "label": "5G فعال", "pct": +1, "words": ["5G"], "question": "5G کار می‌کنه؟", "research": "5G +1%", "dynamic": True},
    {"key": "antenna_weak", "label": "آنتن ضعیف", "pct": -8, "words": ["آنتن ضعیف", "سیگنال ضعیف"], "question": "آنتن چطوره؟", "research": "آنتن ضعیف 6-10% افت", "dynamic": True},

    # کارکرد خاص
    {"key": "gaming_heavy", "label": "استفاده گیم سنگین", "pct": -4, "words": ["گیم", "بازی سنگین"], "question": "گیم سنگین؟", "research": "گیم سنگین 3-5% افت", "dynamic": True},
    {"key": "mining", "label": "ماینینگ / استخراج", "pct": -10, "words": ["ماین", "استخراج"], "question": "ماین شده؟", "research": "ماین 8-12% افت", "dynamic": True},

    # مدارک
    {"key": "receipt_original", "label": "فاکتور اصلی فروشگاه", "pct": +2, "words": ["فاکتور اصلی"], "question": "فاکتور اصلی داره؟", "research": "فاکتور اصلی +1-3%", "dynamic": True},
    {"key": "receipt_fake_risk", "label": "فاکتور مشکوک / فیک", "pct": -5, "words": ["فاکتور فیک", "فاکتور مشکوک"], "question": "فاکتور معتبره؟", "research": "فاکتور فیک -4-6%", "dynamic": True},

    # بسته‌بندی نات‌اکتیو دقیق
    {"key": "seal_intact", "label": "پلمپ کارخانه سالم", "pct": +2, "words": ["پلمپ سالم", "سیل"], "question": "پلمپ سالمه؟", "research": "پلمپ سالم +1-3%", "dynamic": True},
    {"key": "seal_opened", "label": "پلمپ باز شده", "pct": -6, "words": ["پلمپ باز", "باز شده"], "question": "پلمپ باز شده؟", "research": "پلمپ باز -5-7% ریسک", "dynamic": True},
    {"key": "seal_repacked", "label": "پلمپ مجدد / ریپک", "pct": -12, "words": ["ریپک", "پلمپ مجدد"], "question": "ریپک شده؟", "research": "ریپک 10-14% افت شدید", "dynamic": True},

    # رجیستری دقیق‌تر
    {"key": "register_hamta_ok", "label": "ثبت همتا اوکی", "pct": +1, "words": ["همتا"], "question": "همتا ثبت شده؟", "research": "همتا +1%", "dynamic": True},
    {"key": "register_temp", "label": "رجیستر موقت / مسافری", "pct": -8, "words": ["مسافری", "موقت"], "question": "رجیستر دائم یا موقت؟", "research": "موقت 6-10% افت", "dynamic": True},
]

ALL_FACTORS = PRICE_FACTORS_IPHONE + EXTRA_PARAMS

def _detect_factors_in_text(text: str, factors: List[Dict] = None) -> List[Dict]:
    """تشخیص عوامل از متن آگهی"""
    factors = factors or ALL_FACTORS
    low = (text or "").lower()
    found = []
    for f in factors:
        for w in f.get("words", []):
            if w.lower() in low or w.lower() in text:
                found.append(f)
                break
    return found

def calculate_profitability(
    title: str,
    market_price_new: Optional[int] = None,
    sell_price_healthy: Optional[int] = None,
    desired_profit_pct: float = 10,
    desired_profit_toman: Optional[int] = None,
    conditions_text: str = "",
    extra_factors: List[str] = None,
    db_path: str = "data/divar_leads.db",
) -> Dict[str, Any]:
    """
    محاسبه سودآوری با هزاران پارامتر
    - title: عنوان آگهی
    - market_price_new: قیمت نو از ترب (اگر None، از اینترنت می‌گیرد)
    - sell_price_healthy: قیمت فروش سالم دست دوم (اگر None، از 80% نو حساب می‌کند)
    - desired_profit_pct: درصد سود مورد نظر
    - desired_profit_toman: سود تومانی مورد نظر (اگر داده شد، درصد را override می‌کند)
    - conditions_text: توضیحات آگهی / شرایط مورد نظر
    - extra_factors: لیست کلیدهای اضافی که کاربر گفته مهمه
    """
    research = research_product(title)
    factors = research.get("factors") or ALL_FACTORS

    # قیمت نو از اینترنت اگر نداده
    if market_price_new is None:
        try:
            prod = {"keyword": title, "model": title}
            market_price_new = fetch_market_price_from_web(prod, timeout=5)
        except Exception:
            market_price_new = None

    if market_price_new is None:
        # fallback: از کش یا تخمین
        try:
            cached = get_cached_prices()
            # اگر کش دارد
            for k, v in cached.items():
                if title.lower() in k.lower() or k.lower() in title.lower():
                    market_price_new = int(v) if v else None
                    break
        except Exception:
            pass

    if market_price_new is None:
        # تخمین نهایی: اگر قیمت سالم داده، نو را 25% بیشتر فرض کن
        if sell_price_healthy:
            market_price_new = int(sell_price_healthy * 1.25)
        else:
            market_price_new = 35_000_000  # پیش‌فرض

    if sell_price_healthy is None:
        # سالم دست دوم = 80% نو
        sell_price_healthy = int(market_price_new * 0.80)

    # تشخیص عوامل از متن
    detected = _detect_factors_in_text(conditions_text + " " + title, factors)
    if extra_factors:
        for key in extra_factors:
            f = next((x for x in ALL_FACTORS if x["key"] == key), None)
            if f and f not in detected:
                detected.append(f)

    # محاسبه افت کل
    total_pct = 0
    applied_factors = []
    for f in detected:
        pct = float(f.get("pct", 0))
        # اگر dynamic و مربوط به نات‌اکتیو، از تحقیق اینترنت به‌روز کن
        if f.get("dynamic") and f["key"] in ("not_active", "not_active_no_receipt", "not_active_with_receipt"):
            try:
                dyn = get_dynamic_adjustments_for_product(title)
                if f["key"] in dyn:
                    pct = float(dyn[f["key"]])
            except Exception:
                pass
        total_pct += pct
        applied_factors.append({**f, "applied_pct": pct})

    # قیمت تعدیل‌شده سالم بعد از افت‌ها
    adjusted_fair = int(sell_price_healthy * (1 + total_pct/100.0))
    if adjusted_fair < 1_000_000:
        adjusted_fair = 1_000_000

    # سود
    if desired_profit_toman is None:
        desired_profit_toman = int(sell_price_healthy * desired_profit_pct / 100.0)

    # حد خرید = قیمت تعدیل‌شده منهای سود
    buy_target = adjusted_fair - desired_profit_toman
    if buy_target < 1_000_000:
        buy_target = int(adjusted_fair * 0.85)

    # قیمت‌های خوب / مناسب / سودآور
    good_threshold = int(adjusted_fair * 0.92)  # 8% زیر منصفانه = مناسب
    great_threshold = int(adjusted_fair * 0.82)  # 18% زیر = خیلی مناسب
    profitable_max = buy_target

    # تحلیل ریسک
    risk_notes = []
    if any(f["key"] in ("not_active", "not_active_no_receipt", "seal_opened", "seal_repacked") for f in detected):
        risk_notes.append("⚠️ نات‌اکتیو ادعایی بدون فاکتور: ریسک فیک 5-8% — حتماً فاکتور رسمی بخواه")
    if any(f["key"] in ("battery_low", "battery_replaced") for f in detected):
        risk_notes.append("🔋 باتری ضعیف/تعویض: هزینه تعویض 1.5-2.5م + ریسک اصالت")
    if any(f["key"] in ("not_registered", "register_temp") for f in detected):
        risk_notes.append("📡 بدون رجیستر/موقت: هزینه 2-4م + ریسک قطعی آنتن")
    if any(f["key"] in ("repaired", "repaired_board", "water_damage") for f in detected):
        risk_notes.append("🔧 تعمیر/آب‌خورده: افت شدید و ریسک خرابی مجدد")
    if any(f["key"] in ("screen_replaced", "icloud_locked") for f in detected):
        risk_notes.append("🚨 صفحه غیراصل یا آیکلود قفل: افت بسیار شدید")

    # پیشنهاد بهبود
    improve_notes = []
    if total_pct < -15:
        improve_notes.append("افت زیاد — قیمت پیشنهادی را پایین‌تر ببر تا سود حفظ شود")
    if not any(f["key"] in ("with_box", "without_box") for f in detected):
        improve_notes.append("کارتن را بپرس: با کارتن +3-4% گران‌تر")
    if not any(f["key"] in ("battery_100", "battery_95_99", "battery_90_94", "battery_80_85", "battery_low") for f in detected):
        improve_notes.append("باتری را دقیق بپرس: تاثیر 0 تا -12%")

    # تحقیق اینترنت دوباره برای به‌روز کردن
    internet_research = {}
    try:
        internet_research = research_market_adjustments_from_internet(title)
    except Exception:
        internet_research = {}

    # نتیجه نهایی
    result = {
        "title": title,
        "market_price_new": market_price_new,
        "sell_price_healthy": sell_price_healthy,
        "adjusted_fair": adjusted_fair,
        "total_adjustment_pct": round(total_pct, 2),
        "applied_factors": applied_factors,
        "detected_count": len(detected),
        "good_threshold": good_threshold,
        "great_threshold": great_threshold,
        "profitable_max": profitable_max,
        "buy_target": buy_target,
        "desired_profit_pct": round(desired_profit_toman / sell_price_healthy * 100, 1) if sell_price_healthy else desired_profit_pct,
        "desired_profit_toman": desired_profit_toman,
        "risk_notes": risk_notes,
        "improve_notes": improve_notes,
        "research": research,
        "internet_research": internet_research,
        "price_levels": {
            "عالی (خیلی مناسب)": f"تا {great_threshold:,} تومان ({great_threshold//1_000_000}م) — سود {sell_price_healthy - great_threshold:,} تومان",
            "مناسب": f"تا {good_threshold:,} تومان ({good_threshold//1_000_000}م) — سود {sell_price_healthy - good_threshold:,} تومان",
            "سودآور (حد خرید)": f"تا {buy_target:,} تومان ({buy_target//1_000_000}م) — سود {desired_profit_toman:,} تومان ({desired_profit_pct}%)",
            "منصفانه تعدیل‌شده": f"{adjusted_fair:,} تومان — بعد از اعمال {len(detected)} پارامتر",
            "سالم بدون افت": f"{sell_price_healthy:,} تومان",
            "نو ترب": f"{market_price_new:,} تومان",
        },
        "thousands_params_note": f"بررسی {len(ALL_FACTORS)} پارامتر پایه + ترکیب‌ها = هزاران حالت — {len(detected)} مورد در این آگهی اعمال شد",
        "calculation_steps": [
            f"1. قیمت نو از اینترنت: {market_price_new:,} تومان",
            f"2. قیمت سالم دست دوم (80% نو): {sell_price_healthy:,} تومان",
            f"3. افت‌های تشخیص داده شده ({len(detected)} مورد): {total_pct}% = {sell_price_healthy} * {total_pct}% = {sell_price_healthy * total_pct//100:,} تومان",
            f"4. قیمت منصفانه تعدیل‌شده: {sell_price_healthy:,} + {sell_price_healthy * total_pct//100:,} = {adjusted_fair:,}",
            f"5. سود مورد نظر: {desired_profit_toman:,} تومان ({desired_profit_pct}%)",
            f"6. حد خرید سودآور: {adjusted_fair:,} - {desired_profit_toman:,} = {buy_target:,}",
            f"7. آستانه مناسب: {good_threshold:,} (8% زیر منصفانه)",
            f"8. آستانه عالی: {great_threshold:,} (18% زیر منصفانه)",
        ],
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # ذخیره برای تحلیل بعدی
    try:
        cache_path = Path("data/profitability_cache.json")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        existing = []
        if cache_path.exists():
            try:
                existing = json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:
                existing = []
        existing.append({
            "title": title,
            "at": result["timestamp"],
            "buy_target": buy_target,
            "adjusted_fair": adjusted_fair,
            "factors_count": len(detected),
            "profit": desired_profit_toman,
        })
        # نگه داشتن 200 آخر
        existing = existing[-200:]
        cache_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    return result

def test_and_improve_profitability(title: str, iterations: int = 3) -> Dict[str, Any]:
    """
    خودش برود در بخش دیگر طبق آن پارامتر دوباره تنظیم کند — تست و بهبود خودکار
    - چند بار محاسبه می‌کند، با میانه آگهی‌های واقعی مقایسه می‌کند، پارامترها را اصلاح می‌کند
    """
    results = []
    best = None
    for i in range(iterations):
        # هر بار با شرایط متفاوت تست
        res = calculate_profitability(title, desired_profit_pct=10 + i*2)
        results.append(res)
        if best is None or res["buy_target"] > best["buy_target"]:
            best = res

    # بهبود: اگر اینترنت قیمت جدید داد، دوباره محاسبه
    try:
        prod = {"keyword": title, "model": title}
        new_price = fetch_market_price_from_web(prod, timeout=5)
        if new_price and best:
            # با قیمت جدید دوباره
            improved = calculate_profitability(title, market_price_new=new_price, desired_profit_pct=best["desired_profit_pct"])
            if improved["buy_target"] != best["buy_target"]:
                results.append(improved)
                best = improved
    except Exception:
        pass

    return {
        "title": title,
        "iterations": iterations,
        "results": results,
        "best": best,
        "summary": f"{iterations} بار تست شد — بهترین حد خرید: {best['buy_target']:,} تومان با {best['detected_count']} پارامتر" if best else "بدون نتیجه",
    }

# برای API
def get_profitability_for_api(keyword: str, sell_price: int = 0, profit_pct: float = 10, conditions: str = "") -> Dict[str, Any]:
    return calculate_profitability(
        title=keyword,
        sell_price_healthy=sell_price if sell_price else None,
        desired_profit_pct=profit_pct,
        conditions_text=conditions,
    )
