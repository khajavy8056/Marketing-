# -*- coding: utf-8 -*-
"""شکارچی قیمت — نسخه حرفه‌ای با آنالیزور سالم + مذاکره.

قدیمی: میانه خام → افت → سطح
جدید: نمونه‌ها → معادل سالم → میانه سالم (با IQR) → ارزش منصفانه → تخفیف واقعی + اطمینان + مذاکره
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Sequence

from .hunter_profile import (
    adjustment_pct,
    build_questions,
    default_profile,
    extract_flags,
    mileage_adjustment,
    missing_ask_slots,
)


def median_of(prices: Sequence[int]) -> Optional[float]:
    vals = [int(p) for p in prices if isinstance(p, (int, float)) and int(p) > 0]
    if len(vals) < 3:
        return None
    return float(statistics.median(vals))


def deal_level(
    price: int,
    median: Optional[float],
    good_pct: float = 8.0,
    great_pct: float = 15.0,
    suspicious_pct: float = 55.0,
) -> str:
    """بازار / مناسب / خیلی_مناسب / مشکوک."""
    if not median or median <= 0 or not price or price <= 0:
        return "none"
    discount = (median - price) / median * 100.0
    if discount >= suspicious_pct:
        return "suspicious"
    if discount >= great_pct:
        return "great"
    if discount >= good_pct:
        return "good"
    return "market"


def _merge_flags(text: str, profile: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, bool]:
    flags = dict(extra.get("hunter_flags") or extract_flags(text, profile))
    if extra.get("chassis") == "hit":
        flags["chassis_hit"] = True
    if extra.get("paint") == "repainted":
        if not flags.get("paint_full") and not flags.get("paint_panel"):
            flags["paint_multi"] = True
    if extra.get("accident"):
        flags["accident"] = True
    if extra.get("mechanical"):
        flags["mechanical"] = True
    return flags


def evaluate(
    price: int,
    samples: Sequence[Any],
    cfg: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
    profile: Optional[Dict[str, Any]] = None,
    text: str = "",
) -> Dict[str, Any]:
    """ارزیابی حرفه‌ای — اول آنالیزور جدید، اگر نشد fallback قدیمی."""
    cfg = cfg or {}
    extra = extra or {}
    # سعی کن با آنالیزور حرفه‌ای
    try:
        from .hunter_analyzer import evaluate_professional

        prof = profile or default_profile(str(extra.get("category") or ""), str(extra.get("keyword") or ""))
        # cfg thresholds را به پروفایل تزریق کن اگر کاربر تنظیم کرده
        if cfg:
            for k in ("hunter_good_pct", "hunter_great_pct", "hunter_suspicious_pct"):
                if k in cfg and cfg[k] not in (None, ""):
                    try:
                        if k == "hunter_good_pct":
                            prof["good_pct"] = float(cfg[k])
                        elif k == "hunter_great_pct":
                            prof["great_pct"] = float(cfg[k])
                        elif k == "hunter_suspicious_pct":
                            prof["suspicious_pct"] = float(cfg[k])
                    except Exception:
                        pass
        res = evaluate_professional(
            price,
            samples,
            profile=prof,
            extra=extra,
            text=text,
            category=str(extra.get("category") or ""),
            keyword=str(extra.get("keyword") or ""),
        )
        # برای سازگاری با قدیم، فیلدهای قدیمی را هم پر کن
        res.setdefault("median", res.get("healthy_median") or res.get("raw_median") or 0)
        res.setdefault("sample_count", res.get("market", {}).get("count") or len([p for p in samples if p]))
        res.setdefault("warm", bool(res.get("market", {}).get("warm")))
        res.setdefault("blocked", False)
        # اگر pending بود، questions قبلاً پر است
        return res
    except Exception as e:
        # fallback قدیمی
        pass

    # --- fallback قدیمی (همان قبلی) ---
    blocked = {
        "median": 0,
        "fair": 0,
        "sample_count": len([p for p in samples if isinstance(p, (int, float)) and p]),
        "warm": False,
        "level": "none",
        "raw_level": "none",
        "discount_pct": None,
        "adj_pct": 0.0,
        "blocked": True,
        "pending": False,
        "questions": "",
        "missing": [],
        "flags": {},
        "confidence": 0.0,
    }
    if extra.get("hunter_block") or extra.get("is_placeholder") or extra.get("is_buyer"):
        return blocked
    if profile is None:
        profile = default_profile(str(extra.get("category") or ""), str(extra.get("keyword") or ""))
    if not profile.get("hunter", True):
        blocked["reason"] = profile.get("reason") or "این دسته شکار نمی‌شود"
        return blocked
    flags = _merge_flags(text, profile, extra)
    adj = adjustment_pct(flags, profile)
    mileage_km = extra.get("mileage_km") or extra.get("car_mileage")
    year = extra.get("year") or extra.get("car_year")
    if not mileage_km or not year:
        try:
            from .vehicle import extract_mileage, extract_year

            if not mileage_km:
                mileage_km = extract_mileage(text)
            if not year:
                year = extract_year(text)
        except Exception:
            pass
    try:
        km_per_year = float(profile.get("km_per_year") or 20000)
    except Exception:
        km_per_year = 20000.0
    mileage_adj = mileage_adjustment(mileage_km, year, km_per_year) if mileage_km else 0.0
    total_adj = adj + mileage_adj
    total_adj = max(-45.0, min(5.0, total_adj))
    # samples ممکن است دیکشنری باشد — فقط قیمت‌ها را بکش
    simple_prices: List[int] = []
    for s in samples:
        if isinstance(s, dict):
            try:
                simple_prices.append(int(s.get("price") or 0))
            except Exception:
                continue
        elif isinstance(s, (int, float)):
            simple_prices.append(int(s))
    med = median_of(simple_prices)
    fair = (med * (1.0 + total_adj / 100.0)) if med else None
    good = float(profile.get("good_pct") or cfg.get("hunter_good_pct") or 8)
    great = float(profile.get("great_pct") or cfg.get("hunter_great_pct") or 15)
    sus = float(profile.get("suspicious_pct") or cfg.get("hunter_suspicious_pct") or 55)
    raw = deal_level(int(price or 0), fair, good, great, sus)
    pct = None
    if fair and fair > 0 and price:
        pct = round((fair - price) / fair * 100.0, 1)
    missing = missing_ask_slots(text, profile, extra)
    pending = bool(extra.get("needs_inquiry"))
    if profile.get("dealer_mode") and missing:
        pending = True
    questions = ""
    if pending or (profile.get("dealer_mode") and missing):
        questions = build_questions(profile, missing, str(extra.get("title") or ""))
    level = "pending" if pending else raw
    return {
        "median": int(med) if med else 0,
        "healthy_median": int(med) if med else 0,
        "raw_median": int(med) if med else 0,
        "fair": int(fair) if fair else 0,
        "sample_count": len([p for p in simple_prices if p]),
        "warm": med is not None,
        "level": level,
        "raw_level": raw,
        "discount_pct": pct,
        "adj_pct": round(total_adj, 1),
        "adj_flags_pct": round(adj, 1),
        "adj_mileage_pct": round(mileage_adj, 1),
        "mileage_km": int(mileage_km) if mileage_km else 0,
        "year": int(year) if year else 0,
        "blocked": False,
        "pending": pending,
        "questions": questions,
        "missing": missing,
        "flags": flags,
        "confidence": 0.6 if med else 0.3,
        "market": {"count": len(simple_prices), "warm": med is not None},
    }


def analyze_lead(lead: Optional[Dict[str, Any]] = None, keyword: str = "",
                 **kwargs) -> Dict[str, Any]:
    """تحلیل یک آگهی برای تست تیرا / API — بدون دیتابیس."""
    lead = dict(lead or {})
    kw = keyword or str(lead.get("keyword") or kwargs.get("keyword") or "")
    cat = str(lead.get("category") or kwargs.get("category") or "")
    try:
        price = int(lead.get("price") or 0)
    except (TypeError, ValueError):
        price = 0
    text = " ".join(str(lead.get(k) or "") for k in
                    ("title", "subtitle", "description", "inspect_summary"))
    extra = dict(lead)
    extra["keyword"] = kw
    extra["category"] = cat
    prof = default_profile(cat, kw)
    return evaluate(price, [], extra=extra, profile=prof, text=text)


def score_lead(price: int, samples: Sequence[int],
               cfg: Optional[Dict[str, Any]] = None,
               extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    extra = extra or {}
    text = " ".join(str(extra.get(k) or "") for k in
                    ("title", "subtitle", "description", "inspect_summary"))
    sc = evaluate(price, samples, cfg=cfg, extra=extra, text=text)
    return {
        "median": sc.get("median") or 0,
        "sample_count": sc.get("sample_count") or 0,
        "warm": bool(sc.get("warm")),
        "level": sc.get("level") or "none",
        "discount_pct": sc.get("discount_pct"),
        "blocked": bool(sc.get("blocked")),
        "fair": sc.get("fair") or 0,
        "adj_pct": sc.get("adj_pct") or 0,
        "pending": bool(sc.get("pending")),
        "questions": sc.get("questions") or "",
    }


def collect_samples(con, keyword: str, city: str, platform: str = "",
                    hours: int = 72, limit: int = 80) -> List[int]:
    """میانه فقط از نقد سالم — نسخه ساده برای سازگاری."""
    try:
        from .hunter_analyzer import collect_samples_detailed

        detailed = collect_samples_detailed(con, keyword, city, platform, limit)
        # برای سازگاری قدیمی، فقط قیمت‌ها را برگردان
        return [int(d.get("price") or 0) for d in detailed if int(d.get("price") or 0) > 0]
    except Exception:
        pass
    q = ("SELECT price FROM leads WHERE keyword=? AND city=? "
         "AND COALESCE(price,0)>0 "
         "AND COALESCE(price_kind,'cash') IN ('cash','') "
         "AND COALESCE(is_defect,0)=0 "
         "AND COALESCE(is_placeholder,0)=0 "
         "AND COALESCE(is_buyer,0)=0 ")
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
        rows = con.execute(
            "SELECT price FROM leads WHERE keyword=? AND COALESCE(price,0)>0 "
            "ORDER BY id DESC LIMIT ?", (keyword, limit)).fetchall()
    out = []
    for r in rows:
        try:
            n = int(r["price"] if hasattr(r, "keys") else r[0] or 0)
        except (TypeError, ValueError, IndexError):
            n = 0
        if n > 0:
            out.append(n)
    return out


def collect_samples_detailed(con, keyword: str, city: str, platform: str = "", limit: int = 80) -> List[Dict[str, Any]]:
    """نمونه‌ها با جزئیات برای آنالیزور حرفه‌ای."""
    try:
        from .hunter_analyzer import collect_samples_detailed as _detailed

        return _detailed(con, keyword, city, platform, limit)
    except Exception:
        # fallback ساده
        simple = collect_samples(con, keyword, city, platform, limit=limit)
        return [{"price": p, "title": ""} for p in simple]
