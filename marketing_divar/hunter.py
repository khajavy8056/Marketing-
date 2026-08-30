# -*- coding: utf-8 -*-
"""شکارچی قیمت نسبت به میانهٔ همان پایش، با افت پروفایل دسته."""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Sequence

from .hunter_profile import (
    adjustment_pct, build_questions, default_profile, extract_flags,
    mileage_adjustment, missing_ask_slots,
)


def median_of(prices: Sequence[int]) -> Optional[float]:
    vals = [int(p) for p in prices if isinstance(p, (int, float)) and int(p) > 0]
    if len(vals) < 3:
        return None
    return float(statistics.median(vals))


def deal_level(price: int, median: Optional[float],
               good_pct: float = 8.0, great_pct: float = 15.0,
               suspicious_pct: float = 55.0) -> str:
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


def _merge_flags(text: str, profile: Dict[str, Any],
                 extra: Dict[str, Any]) -> Dict[str, bool]:
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


def evaluate(price: int, samples: Sequence[int],
             cfg: Optional[Dict[str, Any]] = None,
             extra: Optional[Dict[str, Any]] = None,
             profile: Optional[Dict[str, Any]] = None,
             text: str = "") -> Dict[str, Any]:
    """میانه → ارزش تعدیل‌شده → سطح شکار. جای‌خالی → pending."""
    cfg = cfg or {}
    extra = extra or {}
    blocked = {
        "median": 0, "fair": 0, "sample_count": len([p for p in samples if p]),
        "warm": False, "level": "none", "raw_level": "none",
        "discount_pct": None, "adj_pct": 0.0, "blocked": True,
        "pending": False, "questions": "", "missing": [], "flags": {},
    }
    if extra.get("hunter_block") or extra.get("is_placeholder") or extra.get("is_buyer"):
        return blocked
    if profile is None:
        profile = default_profile(str(extra.get("category") or ""),
                                  str(extra.get("keyword") or ""))
    if not profile.get("hunter", True):
        blocked["reason"] = profile.get("reason") or "این دسته شکار نمی‌شود"
        return blocked
    flags = _merge_flags(text, profile, extra)
    adj = adjustment_pct(flags, profile)
    # کارکرد و سال — افت جدا بر اساس تحقیق
    mileage_km = extra.get("mileage_km") or extra.get("car_mileage")
    year = extra.get("year") or extra.get("car_year")
    # اگر از متن استخراج نشده، از متن آگهی بخوان
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
    # جمع افت = پرچم‌ها + کارکرد
    total_adj = adj + mileage_adj
    total_adj = max(-45.0, min(5.0, total_adj))
    med = median_of(samples)
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
        "fair": int(fair) if fair else 0,
        "sample_count": len([p for p in samples if p]),
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
    }


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
    """میانه فقط از نقد سالم (نه معیوب، نه جای‌نگهدار، نه خریدار)."""
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
