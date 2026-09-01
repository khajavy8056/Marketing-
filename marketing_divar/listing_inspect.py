# -*- coding: utf-8 -*-
"""بررسی آگهی (متن + تصویر) برای هر سه پلتفرم.

قاعده اول؛ مدل محلی فقط اگر مبهم باشد. تصویر اگر موتور بینایی محلی باشد.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence
from .categories import is_vehicle, normalize_slug
from .classify import classify_post
from .matching import normalize
from .nlu_role import image_prompt, listing_prompt
from .vehicle import inspect_vehicle

_IMG = re.compile(
    r"https?://[^\"'\s<>]+?\.(?:jpg|jpeg|png|webp)(?:\?[^\"'\s<>]*)?",
    re.I,
)


def extract_image_urls(post: Dict[str, Any], html: str = "") -> List[str]:
    found: List[str] = []
    for key in ("images", "photos", "image_urls"):
        val = post.get(key)
        if isinstance(val, (list, tuple)):
            for u in val:
                if isinstance(u, str) and u.startswith("http"):
                    found.append(u)
        elif isinstance(val, str) and val.startswith("http"):
            found.append(val)
    blob = " ".join(str(post.get(k) or "") for k in
                    ("html", "description", "subtitle", "title"))
    blob += " " + (html or "")
    for u in _IMG.findall(blob):
        found.append(u)
    out, seen = [], set()
    for u in found:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= 8:
            break
    return out


def inspect_images(urls: Sequence[str], infer_fn=None) -> Dict[str, Any]:
    """اگر infer_fn باشد هر تصویر را می‌فرستد؛ وگرنه فقط شمارش."""
    urls = [u for u in (urls or []) if u]
    if not urls:
        return {"reviewed": False, "count": 0, "notes": "تصویری در آگهی نبود",
                "paint": "unknown", "damage": False}
    if infer_fn is None:
        return {"reviewed": False, "count": len(urls),
                "notes": "موتور بینایی محلی نیست — فقط تعداد عکس ثبت شد",
                "paint": "unknown", "damage": False, "urls": list(urls)[:8]}
    paint, damage, notes = "unknown", False, []
    reviewed = False
    for u in list(urls)[:4]:
        try:
            raw = infer_fn(image_prompt(), u)
        except Exception:
            raw = ""
        if not raw:
            continue
        reviewed = True
        n = normalize(raw)
        if any(w in n for w in ("رنگ شده", "دوررنگ", "گلگیر", "خط و خش")):
            paint = "repainted"
        if any(w in n for w in ("شاسی", "ضربه", "تصادف", "شکست")):
            damage = True
        notes.append(str(raw)[:160])
    return {
        "reviewed": reviewed,
        "count": len(urls),
        "paint": paint,
        "damage": damage,
        "notes": " | ".join(notes) or "تصویر خوانده نشد",
        "urls": list(urls)[:8],
    }


def inspect_listing(post: Dict[str, Any], use_llm: bool = True,
                    infer_fn=None, vision_fn=None) -> Dict[str, Any]:
    """خروجی واحد برای دیوار/شیپور."""
    from .nlu_role import parse_llm_json

    category = normalize_slug(post.get("category") or "")
    blob = " ".join(str(post.get(k) or "") for k in
                    ("title", "subtitle", "description", "top", "bottom",
                     "condition", "status_text", "price_text"))
    cls = classify_post(post, category=category)
    veh = inspect_vehicle(blob) if is_vehicle(category) or _looks_car(blob) else None
    images = inspect_images(extract_image_urls(post), infer_fn=vision_fn)
    # معیوب سخت / جای‌نگهدار / خریدار شکار نیستند. رنگ تصویر فقط افت قیمت است.
    hunter_block = bool(cls.get("is_placeholder") or cls.get("is_buyer"))
    if cls.get("is_defect") and not veh:
        hunter_block = True
    if images.get("paint") == "repainted" or images.get("damage"):
        if veh:
            veh = dict(veh)
            veh["hunter_block"] = False
            if images.get("paint") == "repainted":
                veh["paint"] = "repainted"
            if images.get("damage") and veh.get("chassis") != "ok":
                veh["chassis"] = "hit"

    summary = cls.get("price_kind") or ""
    if veh:
        summary = veh.get("summary_fa") or summary
    if images.get("reviewed"):
        summary = (summary + " · تصویر: " + str(images.get("notes") or ""))[:240]

    out: Dict[str, Any] = {
        "platform": str(post.get("platform") or "divar"),
        "category": category,
        "price_kind": cls.get("price_kind"),
        "is_defect": bool(cls.get("is_defect") or (veh and veh.get("is_defect"))),
        "is_buyer": bool(cls.get("is_buyer")),
        "is_placeholder": bool(cls.get("is_placeholder")),
        "needs_inquiry": bool(cls.get("needs_inquiry")),
        "hunter_block": hunter_block,
        "vehicle": veh,
        "images": images,
        "summary_fa": summary or "بررسی شد",
        "source": "rules",
    }
    if use_llm and infer_fn and (not veh or veh.get("chassis") == "unknown"):
        try:
            raw = infer_fn(listing_prompt(blob, out["platform"]))
            parsed = parse_llm_json(raw) if raw else None
            if parsed:
                out["source"] = "local_llm"
                if parsed.get("summary_fa"):
                    out["summary_fa"] = parsed["summary_fa"]
        except Exception:
            pass
    return out


def _looks_car(text: str) -> bool:
    n = normalize(text)
    keys = ("پراید", "پژو", "سمند", "تیبا", "دنا", "شاهین", "کوییک",
            "هیوندای", "تویوتا", "کیلومتر", "شاسی", "گیربکس", "مدل 13",
            "خودرو", "ماشین")
    return any(k in n for k in keys)


def apply_inspect_to_post(post: Dict[str, Any], ins: Dict[str, Any]) -> Dict[str, Any]:
    post = dict(post)
    post["inspect_summary"] = ins.get("summary_fa") or ""
    post["hunter_block"] = bool(ins.get("hunter_block"))
    if ins.get("is_defect"):
        post["is_defect"] = True
    veh = ins.get("vehicle") or {}
    post["chassis"] = veh.get("chassis") or ""
    post["paint"] = veh.get("paint") or ""
    post["car_year"] = veh.get("year") or 0
    post["mileage_km"] = veh.get("mileage_km") or 0
    imgs = ins.get("images") or {}
    post["image_count"] = int(imgs.get("count") or 0)
    if ins.get("hunter_block"):
        post["hunter_level"] = ""
    return post
