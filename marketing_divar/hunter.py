# -*- coding: utf-8 -*-
"""شکارچی قیمت نسبت به میانهٔ همان پایش (نه فقط فیلتر بودجه)."""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Sequence


def median_of(prices: Sequence[int]) -> Optional[float]:
    vals = [int(p) for p in prices if isinstance(p, (int, float)) and int(p) > 0]
    if len(vals) < 5:
        return None
    return float(statistics.median(vals))


def deal_level(price: int, median: Optional[float],
               good_pct: float = 10.0, great_pct: float = 22.0,
               suspicious_pct: float = 45.0) -> str:
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


def score_lead(price: int, samples: Sequence[int],
               cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = cfg or {}
    med = median_of(samples)
    level = deal_level(
        price, med,
        good_pct=float(cfg.get("hunter_good_pct") or 10),
        great_pct=float(cfg.get("hunter_great_pct") or 22),
        suspicious_pct=float(cfg.get("hunter_suspicious_pct") or 45),
    )
    pct = None
    if med and med > 0 and price:
        pct = round((med - price) / med * 100.0, 1)
    return {
        "median": int(med) if med else 0,
        "sample_count": len([p for p in samples if p]),
        "warm": med is not None,
        "level": level,
        "discount_pct": pct,
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
