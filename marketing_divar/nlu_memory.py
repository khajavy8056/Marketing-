# -*- coding: utf-8 -*-
"""حافظه پایدار مدل محلی — یادگیری از کلمات، دسته‌ها، پاسخ‌ها و شکارچی.

این ماژول مثل حافظه n8n عمل می‌کند:
- هر کلمه کلیدی جدید → درک اضافه می‌شود (دسته، خانواده، اسلات‌ها)
- هر پاسخ جدید → intent و اسلات ذخیره و برای تحلیل‌های بعدی استفاده می‌شود
- هر آگهی بررسی‌شده → پروفایل شکارچی همان دسته به‌روز می‌شود
- تنظیمات پیشرفته → درصدها و افت‌ها در حافظه می‌مانند

ذخیره در: user_data_dir()/nlu-memory.json + nlu-model/memory.json
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import user_data_dir
from .nlu_model import model_dir as _model_dir


def memory_path() -> Path:
    # اول پوشه پایدار کاربر، بعد کنار مدل
    try:
        base = user_data_dir()
        return base / "nlu-memory.json"
    except Exception:
        return _model_dir() / "memory.json"


def _load() -> Dict[str, Any]:
    p = memory_path()
    if not p.exists():
        return {"version": 1, "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "keywords": {}, "categories": {}, "intents": {},
                "hunter": {}, "replies": [], "stats": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "keywords": {}, "categories": {}, "intents": {}, "hunter": {}, "replies": [], "stats": {}}


def _save(data: Dict[str, Any]) -> None:
    p = memory_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    # کپی کنار مدل هم برای بک‌آپ
    try:
        alt = _model_dir() / "memory.json"
        alt.parent.mkdir(parents=True, exist_ok=True)
        alt.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def remember_keyword(keyword: str, category: str = "", city: str = "", extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """وقتی کاربر کلمه جدید اضافه می‌کند، درکش اضافه می‌شود."""
    data = _load()
    kw = (keyword or "").strip()
    if not kw and not category:
        return data
    key = kw or f"cat:{category}"
    rec = data["keywords"].get(key) or {}
    rec.update({
        "keyword": kw,
        "category": category,
        "city": city,
        "seen_count": int(rec.get("seen_count") or 0) + 1,
        "last_seen": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    if extra:
        rec["extra"] = extra
    # حدس خانواده برای شکارچی
    try:
        from .hunter_profile import default_profile, family_of, guess_category
        cat = guess_category(kw, category)
        fam = family_of(cat) if cat else "generic"
        prof = default_profile(category, kw)
        rec["family"] = fam
        rec["profile_hint"] = prof.get("family")
    except Exception:
        rec["family"] = rec.get("family") or "generic"
    data["keywords"][key] = rec
    # دسته
    if category:
        c = data["categories"].get(category) or {"count": 0, "keywords": []}
        c["count"] = int(c.get("count") or 0) + 1
        if kw and kw not in c.get("keywords", []):
            c.setdefault("keywords", []).append(kw)
        c["last_seen"] = rec["last_seen"]
        data["categories"][category] = c
    _save(data)
    return rec


def remember_reply(token: str, intent: str, confidence: float, text: str = "", slots: Optional[Dict[str, Any]] = None) -> None:
    data = _load()
    # آمار intent
    st = data.setdefault("stats", {})
    st[intent] = int(st.get(intent) or 0) + 1
    # لیست آخرین 100 پاسخ
    lst = data.setdefault("replies", [])
    lst.append({
        "token": token,
        "intent": intent,
        "confidence": confidence,
        "text": (text or "")[:200],
        "slots": slots or {},
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    if len(lst) > 100:
        data["replies"] = lst[-100:]
    _save(data)


def remember_listing(token: str, category: str, hunter_level: str = "", price: int = 0, is_defect: bool = False) -> None:
    data = _load()
    h = data.setdefault("hunter", {})
    if category:
        rec = h.get(category) or {"seen": 0, "defect": 0, "levels": {}}
        rec["seen"] = int(rec.get("seen") or 0) + 1
        if is_defect:
            rec["defect"] = int(rec.get("defect") or 0) + 1
        if hunter_level:
            lv = rec.setdefault("levels", {})
            lv[hunter_level] = int(lv.get(hunter_level) or 0) + 1
        rec["last_price"] = price
        rec["last_seen"] = time.strftime("%Y-%m-%d %H:%M:%S")
        h[category] = rec
        _save(data)


def get_memory() -> Dict[str, Any]:
    return _load()


def get_keyword_understanding(keyword: str) -> Dict[str, Any]:
    data = _load()
    return data["keywords"].get(keyword) or {}


def get_stats() -> Dict[str, Any]:
    data = _load()
    return {
        "keywords_count": len(data.get("keywords") or {}),
        "categories_count": len(data.get("categories") or {}),
        "replies_count": len(data.get("replies") or {}),
        "intents": data.get("stats") or {},
        "hunter": data.get("hunter") or {},
    }


def enrich_prompt_with_memory(base_prompt: str, keyword: str = "", category: str = "") -> str:
    """وقتی کاربر چیزی اضافه می‌کند، درکش به پرامپت اضافه می‌شود تا آنالیز بهتر شود."""
    data = _load()
    hints = []
    if keyword:
        rec = data["keywords"].get(keyword)
        if rec:
            hints.append(f"کلمه «{keyword}» قبلاً {rec.get('seen_count',1)} بار دیده شده؛ خانواده: {rec.get('family','')}")
    if category:
        crec = data["categories"].get(category)
        if crec:
            hints.append(f"دسته {category} تاکنون {crec.get('count',0)} کلمه دارد")
    if hints:
        return base_prompt + "\n\n[حافظه سیستم — از قبل می‌دانی]:\n" + "\n".join(hints) + "\n"
    return base_prompt
