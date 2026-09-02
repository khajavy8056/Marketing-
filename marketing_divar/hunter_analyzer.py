# -*- coding: utf-8 -*-
"""آنالیزور حرفه‌ای شکارچی — هسته اصلی سیستم.

ایده: بهترین مدل سالم را مبنا کن، نه میانگین خام آگهی‌ها.
- هر نمونه را به «قیمت معادل سالم» نرمال کن: healthy_eq = price / (1+adj)
- پرت‌ها را با IQR حذف کن
- میانه سالم + صدک‌ها + انحراف معیار → بازار سالم
- آگهی هدف را با همان افت‌ها بسنج → تخفیف واقعی + سطح + اطمینان
- اگر جای خالی بحرانی → pending → مذاکره

این ماژول قلب شکارچی است — باید خیلی قوی و منعطف باشد.
"""

from __future__ import annotations

import math
import re
import statistics
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .hunter_profile import (
    adjustment_pct,
    build_questions,
    default_profile,
    extract_flags,
    mileage_adjustment,
    missing_ask_slots,
    year_adjustment,
)


def _parse_int(v: Any) -> int:
    try:
        return int(float(str(v).replace(",", "")))
    except Exception:
        return 0


def _iqr_filter(values: List[float]) -> Tuple[List[float], int]:
    """حذف پرت با IQR — برای بازار سالم."""
    if len(values) < 5:
        return values, 0
    try:
        vals = sorted(values)
        q1 = statistics.median(vals[: len(vals) // 2])
        q3 = statistics.median(vals[(len(vals) + 1) // 2 :])
        iqr = q3 - q1
        low = q1 - 1.5 * iqr
        high = q3 + 1.5 * iqr
        filtered = [x for x in vals if low <= x <= high]
        # حداقل 60% بماند
        if len(filtered) < len(vals) * 0.6:
            return vals, 0
        return filtered, len(vals) - len(filtered)
    except Exception:
        return values, 0


def _extract_sample_adjustment(sample: Dict[str, Any], profile: Dict[str, Any]) -> float:
    """افت نمونه از روی توضیحات + فیلدهای ذخیره شده."""
    text = " ".join(
        str(sample.get(k) or "") for k in ("title", "subtitle", "description", "inspect_summary")
    )
    flags = extract_flags(text, profile)
    # فیلدهای مستقیم
    if sample.get("chassis") == "hit":
        flags["chassis_hit"] = True
    if sample.get("paint") in ("repainted", "full", "panel"):
        # اگر رنگ دارد
        if not any(flags.get(x) for x in ("paint_full", "paint_all", "paint_panel", "paint_multi")):
            flags["paint_multi"] = True
    adj = adjustment_pct(flags, profile)
    # کارکرد
    mileage = sample.get("mileage_km") or sample.get("car_mileage") or 0
    year = sample.get("year") or sample.get("car_year") or 0
    if not mileage:
        try:
            from .vehicle import extract_mileage

            mileage = extract_mileage(text) or 0
        except Exception:
            pass
    if not year:
        try:
            from .vehicle import extract_year

            year = extract_year(text) or 0
        except Exception:
            pass
    km_per_year = float(profile.get("km_per_year") or 20000)
    m_adj = mileage_adjustment(mileage, year, km_per_year) if mileage else 0.0
    total = adj + m_adj
    return max(-45.0, min(5.0, total))


def normalize_to_healthy(price: int, adj_pct: float) -> float:
    """قیمت معادل سالم: اگر -14% افت دارد، سالم = قیمت / 0.86"""
    if price <= 0:
        return 0.0
    denom = 1.0 + adj_pct / 100.0
    if denom <= 0.3:  # جلوگیری از تقسیم خیلی کوچک
        denom = 0.3
    return float(price) / denom


def compute_market_stats(
    samples: Sequence[Any], profile: Dict[str, Any]
) -> Dict[str, Any]:
    """
    samples می‌تواند لیست قیمت ساده یا لیست دیکشنری با جزئیات باشد.
    خروجی: healthy_median, raw_median, p10, p25, p75, p90, mean, std, count, ...
    """
    if not samples:
        return {
            "healthy_median": 0,
            "raw_median": 0,
            "p10": 0,
            "p25": 0,
            "p75": 0,
            "p90": 0,
            "mean": 0,
            "std": 0,
            "count": 0,
            "healthy_count": 0,
            "outlier_count": 0,
            "warm": False,
        }

    # تبدیل به لیست قیمت و لیست دیکشنری
    raw_prices: List[int] = []
    healthy_equivs: List[float] = []

    for s in samples:
        if isinstance(s, dict):
            p = _parse_int(s.get("price") or s.get("price_toman") or 0)
            if p <= 0:
                continue
            raw_prices.append(p)
            adj = _extract_sample_adjustment(s, profile)
            healthy_equivs.append(normalize_to_healthy(p, adj))
        elif isinstance(s, (int, float)):
            p = int(s)
            if p <= 0:
                continue
            raw_prices.append(p)
            healthy_equivs.append(float(p))  # بدون اطلاعات افت → فرض سالم
        else:
            continue

    if len(raw_prices) < 3:
        return {
            "healthy_median": int(statistics.median(raw_prices)) if raw_prices else 0,
            "raw_median": int(statistics.median(raw_prices)) if raw_prices else 0,
            "p10": 0,
            "p25": 0,
            "p75": 0,
            "p90": 0,
            "mean": int(statistics.mean(raw_prices)) if raw_prices else 0,
            "std": 0,
            "count": len(raw_prices),
            "healthy_count": len(healthy_equivs),
            "outlier_count": 0,
            "warm": len(raw_prices) >= 3,
        }

    # فیلتر پرت روی healthy_equivs
    filtered_healthy, outlier_cnt = _iqr_filter(healthy_equivs)
    # raw متناظر را هم فیلتر کنیم تقریبی — از healthy فیلتر شده میانگین بگیریم
    # برای سادگی raw_median جدا حساب می‌شود با IQR خودش
    filtered_raw, _ = _iqr_filter([float(x) for x in raw_prices])

    def _pct(data: List[float], p: float) -> int:
        if not data:
            return 0
        try:
            # percentile ساده
            s = sorted(data)
            k = (len(s) - 1) * p / 100.0
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return int(s[int(k)])
            d0 = s[int(f)] * (c - k)
            d1 = s[int(c)] * (k - f)
            return int(d0 + d1)
        except Exception:
            return int(statistics.median(data)) if data else 0

    healthy_median = int(statistics.median(filtered_healthy)) if filtered_healthy else 0
    raw_median = int(statistics.median(filtered_raw)) if filtered_raw else 0

    return {
        "healthy_median": healthy_median,
        "raw_median": raw_median,
        "p10": _pct(filtered_healthy, 10),
        "p25": _pct(filtered_healthy, 25),
        "p75": _pct(filtered_healthy, 75),
        "p90": _pct(filtered_healthy, 90),
        "mean": int(statistics.mean(filtered_healthy)) if filtered_healthy else 0,
        "std": int(statistics.pstdev(filtered_healthy)) if len(filtered_healthy) > 1 else 0,
        "count": len(raw_prices),
        "healthy_count": len(filtered_healthy),
        "outlier_count": outlier_cnt,
        "warm": len(filtered_healthy) >= 3,
    }


def identify_product(text: str, category: str = "", keyword: str = "") -> Dict[str, Any]:
    """شناسایی محصول — برند، مدل، سال، مشخصات کلیدی."""
    from .matching import normalize

    n = normalize(text or "")
    out: Dict[str, Any] = {
        "category": category,
        "keyword": keyword,
        "brand": "",
        "model": "",
        "year": 0,
        "specs": {},
    }
    # سال
    try:
        from .vehicle import extract_year

        y = extract_year(text)
        if y:
            out["year"] = int(y)
    except Exception:
        pass
    # برند موبایل
    brands = {
        "apple": ["آیفون", "iphone", "اپل"],
        "samsung": ["سامسونگ", "samsung", "گلکسی"],
        "xiaomi": ["شیائومی", "xiaomi", "redmi", "poco"],
        "laptop": ["لپ تاپ", "لپ‌تاپ", "نوت بوک"],
    }
    for b, words in brands.items():
        if any(normalize(w) in n for w in words):
            out["brand"] = b
            break
    # مدل خودرو ساده
    car_models = ["پراید", "پژو", "سمند", "دنا", "شاهین", "تیبا", "کوییک", "پارس", "رانا", "تارا", "206", "405"]
    for cm in car_models:
        if normalize(cm) in n:
            out["model"] = cm
            break
    return out


def _maybe_enrich_with_web_price(
    market: Dict[str, Any],
    product: Dict[str, Any],
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    """اگر نمونه کم است، قیمت وب را هم به market اضافه کن (اختیاری)."""
    try:
        cnt = market.get("healthy_count") or market.get("count") or 0
        if cnt >= 5:
            return market
        # فقط اگر confidence پایین یا نمونه کم
        from .price_knowledge import fetch_market_price_from_web

        web_price = fetch_market_price_from_web(product, timeout=4, use_cache=True)
        if web_price and web_price > 0:
            # به عنوان یک شاهد اضافه کن — نه جایگزین median
            market["web_price"] = int(web_price)
            market["web_price_source"] = "torob"
            # اگر healthy_median صفر است، از web_price استفاده کن
            if not market.get("healthy_median"):
                market["healthy_median"] = int(web_price)
                market["raw_median"] = int(web_price)
    except Exception:
        pass
    return market


def evaluate_professional(
    price: int,
    samples: Sequence[Any],
    profile: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
    text: str = "",
    category: str = "",
    keyword: str = "",
    enable_web_price: bool = False,
) -> Dict[str, Any]:
    """
    آنالیزور حرفه‌ای:
    - بازار سالم → میانه سالم
    - افت هدف → ارزش منصفانه
    - تخفیف واقعی + سطح + اطمینان + جای‌خالی
    - اختیاری: قیمت وب اگر enable_web_price=True و نمونه کم
    """
    extra = extra or {}
    category = category or str(extra.get("category") or "")
    keyword = keyword or str(extra.get("keyword") or extra.get("matched_keywords") or "")

    if profile is None:
        profile = default_profile(category, keyword)

    if not profile.get("hunter", True):
        return {
            "healthy_median": 0,
            "raw_median": 0,
            "fair": 0,
            "price": int(price or 0),
            "discount_pct": None,
            "level": "none",
            "raw_level": "none",
            "adj_pct": 0,
            "adj_flags_pct": 0,
            "adj_mileage_pct": 0,
            "adj_year_pct": 0,
            "blocked": True,
            "reason": profile.get("reason") or "این دسته شکار نمی‌شود",
            "warm": False,
            "pending": False,
            "questions": "",
            "missing": [],
            "flags": {},
            "confidence": 0.0,
            "market": {},
            "product": {},
            "web_price": 0,
            "web_price_source": "",
        }

    # بازار سالم
    market = compute_market_stats(samples, profile)
    healthy_median = market.get("healthy_median") or market.get("raw_median") or 0
    raw_median = market.get("raw_median") or 0

    # افت هدف
    # متن کامل
    if not text:
        text = " ".join(str(extra.get(k) or "") for k in ("title", "subtitle", "description", "inspect_summary"))

    # پرچم‌ها
    flags: Dict[str, bool] = {}
    try:
        flags = dict(extra.get("hunter_flags") or extract_flags(text, profile))
    except Exception:
        flags = {}
    # فیلدهای مستقیم
    if extra.get("chassis") == "hit":
        flags["chassis_hit"] = True
    if extra.get("paint") in ("repainted", "full", "panel", "multi"):
        # اگر قبلاً چیزی نیست
        if not any(flags.get(x) for x in ("paint_full", "paint_all", "paint_panel", "paint_multi", "paint_two")):
            flags["paint_multi"] = True

    adj_flags = adjustment_pct(flags, profile)

    # کارکرد و سال
    mileage_km = extra.get("mileage_km") or extra.get("car_mileage") or 0
    year = extra.get("year") or extra.get("car_year") or 0
    if not mileage_km or not year:
        try:
            from .vehicle import extract_mileage, extract_year

            if not mileage_km:
                mileage_km = extract_mileage(text) or 0
            if not year:
                year = extract_year(text) or 0
        except Exception:
            pass

    km_per_year = float(profile.get("km_per_year") or 20000)
    mileage_adj = mileage_adjustment(mileage_km, year, km_per_year) if mileage_km else 0.0
    year_adj = 0.0
    # year_adjustment برای ارزش منصفانه نسبت به امسال — اما در حال حاضر فقط برای اطلاعات
    # چون healthy_median خودش سال‌های مختلف را نرمال نکرده، سال را جدا حساب می‌کنیم
    # اگر سال خیلی قدیمی باشد، ارزش کمتر است — پس fair کمتر می‌شود؟ نه، برعکس: سال قدیمی افت دارد
    # پس year_adj منفی → fair کمتر
    try:
        if year:
            # هر سال 5% افت نسبت به امسال
            dep = float(profile.get("year_depreciation_per_year") or 5.0)
            if year > 1300:
                age = max(0, 1404 - int(year))
            else:
                age = max(0, 2025 - int(year))
            # اگر نمونه‌ها میانگین سنی مشابه دارند، این افت را نصف کن تا سخت‌گیر نباشد
            year_adj = -(age * dep * 0.5)  # نصف اثر برای جلوگیری از افت شدید
            year_adj = max(-30.0, year_adj)
    except Exception:
        year_adj = 0.0

    total_adj = adj_flags + mileage_adj + year_adj
    total_adj = max(-50.0, min(10.0, total_adj))

    fair = int(healthy_median * (1.0 + total_adj / 100.0)) if healthy_median else 0

    # تخفیف واقعی
    discount_pct: Optional[float] = None
    if fair and fair > 0 and price and price > 0:
        discount_pct = round((fair - price) / fair * 100.0, 1)

    # سطح شکار — با آستانه‌های پروفایل + صدک‌ها
    good_pct = float(profile.get("good_pct") or 10.0)
    great_pct = float(profile.get("great_pct") or 18.0)
    suspicious_pct = float(profile.get("suspicious_pct") or 48.0)

    # صدک‌ها هم کمک کنند: اگر قیمت زیر p10 باشد → great حتی اگر آستانه نرسد
    raw_level = "market"
    if fair and price:
        if discount_pct is not None:
            if discount_pct >= suspicious_pct:
                raw_level = "suspicious"
            elif discount_pct >= great_pct:
                raw_level = "great"
            elif discount_pct >= good_pct:
                raw_level = "good"
            else:
                raw_level = "market"
        # تقویت با صدک
        if market.get("p10") and price and price > 0:
            if price <= market["p10"] and raw_level == "market":
                # خیلی ارزان‌تر از 90% بازار سالم
                raw_level = "good"
            if price <= market["p10"] * 0.9 and raw_level == "good":
                raw_level = "great"
    else:
        raw_level = "none"

    # اطمینان
    confidence = 0.5
    # تعداد نمونه
    cnt = market.get("healthy_count") or market.get("count") or 0
    if cnt >= 10:
        confidence += 0.2
    elif cnt >= 5:
        confidence += 0.1
    elif cnt >= 3:
        confidence += 0.05
    else:
        confidence -= 0.2

    # اگر پرچم‌های مهم داریم، اطمینان بیشتر
    if flags:
        confidence += 0.05
    # اگر سال و کارکرد داریم
    if mileage_km and year:
        confidence += 0.1
    # اگر قیمت خیلی پرت است (مشکوک) اطمینان کم
    if raw_level == "suspicious":
        confidence -= 0.15

    confidence = max(0.1, min(0.95, confidence))

    # جای خالی
    missing = missing_ask_slots(text, profile, extra)
    pending = False
    if profile.get("dealer_mode") and missing:
        pending = True
    # اگر اطمینان پایین و جای خالی بحرانی → pending
    if confidence < 0.6 and missing:
        # اگر شاسی یا رنگ برای خودرو ناقص است
        if profile.get("family") == "vehicle" and any(k in missing for k in ("chassis", "paint", "year", "mileage_km")):
            pending = True

    questions = ""
    if pending:
        questions = build_questions(profile, missing, str(extra.get("title") or ""))

    level = "pending" if pending else raw_level

    product = identify_product(text, category, keyword)

    # اختیاری: قیمت وب اگر نمونه کم و فعال باشد
    if enable_web_price:
        market = _maybe_enrich_with_web_price(market, product, profile)
        # healthy_median ممکن است با web_price پر شده باشد
        healthy_median = market.get("healthy_median") or healthy_median
        fair = int(healthy_median * (1.0 + total_adj / 100.0)) if healthy_median else fair
        if fair and price:
            discount_pct = round((fair - price) / fair * 100.0, 1)

    return {
        "healthy_median": int(healthy_median),
        "raw_median": int(raw_median),
        "median": int(healthy_median),  # برای سازگاری با قدیم
        "fair": int(fair),
        "price": int(price or 0),
        "discount_pct": discount_pct,
        "level": level,
        "raw_level": raw_level,
        "adj_pct": round(total_adj, 1),
        "adj_flags_pct": round(adj_flags, 1),
        "adj_mileage_pct": round(mileage_adj, 1),
        "adj_year_pct": round(year_adj, 1),
        "mileage_km": int(mileage_km) if mileage_km else 0,
        "year": int(year) if year else 0,
        "blocked": False,
        "warm": bool(market.get("warm")),
        "pending": pending,
        "questions": questions,
        "missing": missing,
        "flags": flags,
        "confidence": round(confidence, 2),
        "market": market,
        "product": product,
        "sample_count": cnt,
        "web_price": market.get("web_price", 0),
        "web_price_source": market.get("web_price_source", ""),
    }


def collect_samples_detailed(con, keyword: str, city: str, platform: str = "", limit: int = 80) -> List[Dict[str, Any]]:
    """نمونه‌ها با جزئیات برای نرمال‌سازی سالم."""
    q = (
        "SELECT token, title, subtitle, description, price, chassis, paint, car_year, mileage_km, "
        "platform, city, keyword FROM leads WHERE keyword=? AND city=? "
        "AND COALESCE(price,0)>0 "
        "AND COALESCE(price_kind,'cash') IN ('cash','') "
        "AND COALESCE(is_defect,0)=0 "
        "AND COALESCE(is_placeholder,0)=0 "
        "AND COALESCE(is_buyer,0)=0 "
    )
    args: List[Any] = [keyword, city]
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(leads)")}
    except Exception:
        cols = set()
    if platform and "platform" in cols:
        q += "AND COALESCE(platform,'divar')=? "
        args.append(platform)
    q += "ORDER BY id DESC LIMIT ?"
    args.append(limit)
    try:
        rows = con.execute(q, args).fetchall()
    except Exception:
        try:
            rows = con.execute(
                "SELECT token, title, price, chassis, paint, car_year, mileage_km FROM leads WHERE keyword=? AND COALESCE(price,0)>0 ORDER BY id DESC LIMIT ?",
                (keyword, limit),
            ).fetchall()
        except Exception:
            rows = []
    out: List[Dict[str, Any]] = []
    for r in rows:
        try:
            d = dict(r)
            out.append(d)
        except Exception:
            try:
                out.append({"price": int(r[0]), "title": ""})
            except Exception:
                continue
    return out
