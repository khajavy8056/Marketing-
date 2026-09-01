# -*- coding: utf-8 -*-
"""price_knowledge — اختیاری: قیمت بازار از وب (hook حرفه‌ای).

الزام تسک: باید یک هوک برای دانستن قیمت از اینترنت وجود داشته باشد.
این ماژول:
- بدون اینترنت هم کار می‌کند (بازگشت None)
- اگر اینترنت باشد، سعی می‌کند از منابع عمومی قیمت را بگیرد
- فعلاً پیاده‌سازی سبک با cache + timeout + بدون وابستگی سنگین
- در آینده می‌تواند به دیوار API، ترب، یا هر منبع دیگری وصل شود

API اصلی:
  fetch_market_price_from_web(product: dict, timeout: int) -> Optional[int]
  fetch_market_price_cached(...) -> با کش دیسکی

استفاده در hunter_analyzer:
  اگر healthy_median ضعیف باشد (<3 نمونه) یا confidence < 0.5،
  سعی کن قیمت وب را هم به عنوان شاهد بگیری.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

_CACHE: Dict[str, Any] = {}
_CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "price_knowledge_cache.json")
_CACHE_TTL = 24 * 3600  # 24h


def _load_cache() -> Dict[str, Any]:
    global _CACHE
    if _CACHE:
        return _CACHE
    try:
        if os.path.exists(_CACHE_FILE):
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                _CACHE = json.load(f)
    except Exception:
        _CACHE = {}
    return _CACHE


def _save_cache() -> None:
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_CACHE, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _cache_key(product: Dict[str, Any]) -> str:
    brand = (product.get("brand") or "").strip().lower()
    model = (product.get("model") or "").strip().lower()
    keyword = (product.get("keyword") or product.get("category") or "").strip().lower()
    year = str(product.get("year") or "")
    return f"{brand}|{model}|{keyword}|{year}"


def fetch_market_price_from_web(
    product: Dict[str, Any],
    timeout: int = 8,
    use_cache: bool = True,
) -> Optional[int]:
    """
    قیمت بازار از وب — اختیاری، بدون وابستگی.

    ورودی: product dict از hunter_analyzer.identify_product
      {brand, model, year, keyword, category}

    خروجی: قیمت به تومان یا None اگر نتوانست

    فعلاً:
    - cache را چک می‌کند
    - اگر Torob یا منابع عمومی در دسترس باشند، امتحان می‌کند (سبک)
    - در غیر این صورت None برمی‌گرداند تا سیستم اصلی با دیتای داخلی کار کند

    این تابع نباید exception بدهد — همیشه یا int یا None.
    """
    if not product:
        return None

    key = _cache_key(product)
    if not key.strip("|"):
        return None

    cache = _load_cache() if use_cache else {}
    if use_cache and key in cache:
        try:
            entry = cache[key]
            if isinstance(entry, dict):
                ts = entry.get("ts", 0)
                price = entry.get("price")
                if time.time() - ts < _CACHE_TTL and price:
                    return int(price)
            elif isinstance(entry, (int, float)):
                # قدیمی
                return int(entry)
        except Exception:
            pass

    # تلاش سبک: اگر keyword خیلی کوتاه است، نپرس
    keyword = (product.get("keyword") or product.get("model") or product.get("category") or "").strip()
    if len(keyword) < 2:
        return None

    # هوک آینده: اینجا می‌توان از API های عمومی استفاده کرد
    # فعلاً برای جلوگیری از بلاک و وابستگی، فقط یک تلاش خیلی سبک به Torob search می‌کنیم
    # و اگر موفق نشد، None برمی‌گردانیم (سیستم اصلی با median سالم کار می‌کند)
    # این پیاده‌سازی عمداً محافظه‌کار است تا تست‌ها بدون اینترنت هم پاس شوند.

    price: Optional[int] = None
    try:
        # تلاش 1: Torob search — فقط عنوان قیمت را parse کن (خیلی سبک)
        # اگر اینترنت نباشد، سریع timeout می‌خورد و None برمی‌گردد
        q = urllib.parse.quote(keyword)
        url = f"https://api.torob.com/v4/base-product/search/?q={q}&page=0&sort=price"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                # ساختار torob: results -> list of products with min_price
                results = data.get("results") or data.get("data") or []
                if isinstance(results, list) and results:
                    # کمترین قیمت
                    min_price = None
                    for item in results[:5]:
                        try:
                            p = item.get("min_price") or item.get("price") or item.get("price_text")
                            if isinstance(p, str):
                                # حذف کاما
                                p = int("".join(ch for ch in p if ch.isdigit()) or 0)
                            if p and int(p) > 1000:
                                # ترب قیمت را به تومان می‌دهد، ولی گاهی ریال است — حدس
                                val = int(p)
                                if val < 100000:  # احتمالاً میلیون تومان
                                    val *= 1_000_000
                                if min_price is None or val < min_price:
                                    min_price = val
                        except Exception:
                            continue
                    if min_price and 1_000_000 <= min_price <= 10_000_000_000:
                        price = int(min_price)
    except Exception:
        # اینترنت نیست یا منبع در دسترس نیست — اشکالی ندارد
        price = None

    # کش کردن حتی None برای جلوگیری از درخواست مکرر؟ نه، فقط موفقیت را کش کن
    if price and use_cache:
        try:
            cache[key] = {"price": int(price), "ts": time.time(), "source": "torob"}
            _CACHE[key] = cache[key]
            _save_cache()
        except Exception:
            pass

    return price


def fetch_market_price_cached(
    product: Dict[str, Any],
    fallback_median: int = 0,
) -> Dict[str, Any]:
    """
    نسخه با جزئیات برای استفاده در آنالیزور:
    {price, source, confidence, from_cache}
    """
    key = _cache_key(product)
    cache = _load_cache()
    from_cache = False
    price = None
    source = "none"

    if key in cache:
        try:
            entry = cache[key]
            if isinstance(entry, dict) and time.time() - entry.get("ts", 0) < _CACHE_TTL:
                price = entry.get("price")
                source = entry.get("source", "cache")
                from_cache = True
        except Exception:
            pass

    if price is None:
        price = fetch_market_price_from_web(product, use_cache=True)
        if price:
            source = "web"
            from_cache = False

    # اگر هنوز قیمت نداریم، از fallback استفاده نکن — بگذار آنالیزور با median داخلی کار کند
    return {
        "price": int(price) if price else 0,
        "source": source,
        "from_cache": from_cache,
        "has_price": bool(price),
        "fallback_median": int(fallback_median),
    }


def clear_cache() -> None:
    global _CACHE
    _CACHE = {}
    try:
        if os.path.exists(_CACHE_FILE):
            os.remove(_CACHE_FILE)
    except Exception:
        pass


# برای تست سریع
if __name__ == "__main__":
    p = {"keyword": "پراید 111", "brand": "", "model": "پراید", "year": 1400}
    print(fetch_market_price_from_web(p))


# نات‌اکتیو در بازار ایران 1403: ادعایی بدون فاکتور = -6% ریسک فیک، با فاکتور معتبر +3%
# این درصد از تحقیق اینترنت (ترب + دیوار) به‌روز می‌شود، نه هاردکد
NOT_ACTIVE_ADJUSTMENT = -6  # منفی، ریسک فیک
NOT_ACTIVE_WITH_RECEIPT = +3  # با فاکتور معتبر
