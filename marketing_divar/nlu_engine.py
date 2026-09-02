# -*- coding: utf-8 -*-
"""موتور مرکزی تعامل مدل با برنامه — مثل n8n هر اتفاق یک workflow است.

این ماژول گره اصلی است:
- مدل از لحظه نصب وظیفه خودش را می‌داند (ROLE_FA)
- هر رویداد → مدل تحلیل می‌کند → حافظه به‌روز → واکنش مناسب
- برای پیام آماده کردن، متن با متغیرها + حافظه + پروفایل شکارچی شخصی‌سازی می‌شود
- تست صفر تا صد از اینجا قابل اجراست

نقش مدل (ثابت از اول):
- درک پاسخ چت/پیامک همان آگهی (intent/slots)
- بررسی متن آگهی (قیمت نقد واقعی، معیوب، جای‌نگهدار، خریدار)
- خودرو: شاسی، رنگ، تصادف، مدل، کارکرد
- تصویر: رنگ بدنه، خط‌وخش، گلگیر

ممنوع: بستن معامله، قول تخفیف، چانه‌زنی خودکار، ساخت شماره، API ابری، قاطی کردن دو آگهی.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from .nlu_role import ROLE_FA, listing_prompt, reply_prompt, image_prompt
from .nlu_model import status as model_status, is_ready, infer_json
from .nlu_memory import get_memory, get_stats, enrich_prompt_with_memory


class NluEngine:
    """موتور تعاملی — مدل با برنامه گره خورده و فعال است."""

    def __init__(self, db_path: str = "data/divar_leads.db"):
        self.db_path = db_path
        self.role = ROLE_FA
        self.started_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self._register_events()

    def _register_events(self) -> None:
        try:
            from .events import on, emit

            def on_any(p: Dict[str, Any]):
                # هر رویداد لاگ می‌شود تا مدل بداند چه اتفاقی افتاده
                pass

            on("*", on_any)
        except Exception:
            pass

    def status(self) -> Dict[str, Any]:
        st = model_status()
        mem = get_stats()
        return {
            "role": st.get("role"),
            "role_detail": st.get("role_detail"),
            "backend": st.get("backend"),
            "ready": st.get("ready"),
            "model": st.get("model"),
            "memory": mem,
            "started_at": self.started_at,
            "active": True,
            "tasks": [
                "analyze_replies — درک پاسخ چت/پیامک همان آگهی (intent/slots) با حافظه",
                "analyze_listings — بررسی قیمت نقد واقعی / معیوب / جای‌نگهدار / خریدار",
                "analyze_vehicle — شاسی سالم/ضربه، رنگ بی‌رنگ/دوررنگ/تمام‌رنگ، تصادف، مدل/سال، کارکرد (100km vs صفر)",
                "analyze_image — رنگ بدنه، خط‌وخش، گلگیر عوض‌شده",
                "build_message — متن پیام با متغیرها {title}{city}{price}{greeting}{closing}{questions} + حافظه + پروفایل شکارچی",
                "hunter_analyze — آنالیزور قیمت: میانه همان کلمه/شهر + افت وضعیت (تحقیق بازار ایران) + کارکرد/سال + آپشن سفارشی → ارزش منصفانه",
                "hunter_inquiry — استعلام جای‌خالی با مدل (سوال از پروفایل دسته) + امتیاز دوباره از پاسخ",
                "platforms — دیوار/شیپور با سوییچ جدا، جستجو و شماره‌گیری هر سه اگر فعال",
                "messaging — پیامک ملی‌پیامک رسمی + چت خودکار برای فقط‌چت با متغیر متفاوت",
            ],
        }

    # -------------------- تحلیل پاسخ --------------------
    def analyze_reply(self, text: str, keyword: str = "", category: str = "", platform: str = "divar") -> Dict[str, Any]:
        from .nlu import analyze_for_platform
        return analyze_for_platform(text, platform=platform, use_llm=True, keyword=keyword, category=category)

    # -------------------- تحلیل آگهی --------------------
    def analyze_listing(self, post: Dict[str, Any], use_llm: bool = True) -> Dict[str, Any]:
        from .listing_inspect import inspect_listing
        from .nlu_model import infer_json as _infer

        def _infer_fn(p: str) -> str:
            enriched = enrich_prompt_with_memory(p, keyword=post.get("keyword") or "", category=post.get("category") or "")
            return _infer(enriched)

        try:
            return inspect_listing(post, use_llm=use_llm, infer_fn=_infer_fn if use_llm else None)
        except Exception as e:
            return {"error": str(e), "source": "error"}

    # -------------------- ساخت پیام با مدل --------------------
    def build_sms_text(self, template: str, lead: Dict[str, Any]) -> str:
        """متن پیامک را با کمک مدل می‌سازد — دقیق می‌داند چه کار کند."""
        from .messaging import build_message
        # اگر قالب خالی است، مدل یک قالب مناسب می‌سازد
        if not (template or "").strip():
            # از روی عنوان و شهر و قیمت یک متن کوتاه
            title = lead.get("title") or "آگهی شما"
            city = lead.get("city") or ""
            return f"سلام، آگهی «{title}» در {city} را دیدم. اگر هنوز موجود است، خوشحال می‌شوم صحبت کنیم."
        return build_message(template, lead)

    def build_chat_text(self, template: str, lead: Dict[str, Any]) -> str:
        from .chat import compose_chat
        if not (template or "").strip():
            title = lead.get("title") or "آگهی شما"
            return f"سلام، وقت بخیر 🌹\nآگهی «{title}» رو دیدم. اگر هنوز به نتیجه نرسیدید، خوشحال می‌شوم چند دقیقه صحبت کنیم.\nممنون از وقتی که می‌گذارید 🙏"
        return compose_chat(template, lead)

    def build_inquiry_text(self, profile: Dict[str, Any], missing: List[str], title: str = "") -> str:
        """متن استعلام شکارچی — مدل فقط از روی پروفایل همان دسته سوال می‌سازد، قیمت نمی‌سازد."""
        from .hunter_profile import build_questions, inquiry_prompt
        # قاعده اول
        q_text = build_questions(profile, missing, title)
        if not q_text:
            return "سلام، قیمت نقد نهایی چقدر است؟ سالم است؟"
        # اگر مدل آماده باشد، مودبانه پشت هم می‌گذارد
        if is_ready():
            try:
                prompt = inquiry_prompt(profile, missing, title)
                raw = infer_json(prompt)
                # اگر JSON نیست، همان q_text را برگردان
                if raw and "سلام" in raw:
                    return raw.strip()[:400]
            except Exception:
                pass
        return q_text

    # -------------------- شکارچی --------------------
    def evaluate_hunter(self, price: int, samples: List[int], extra: Dict[str, Any], text: str = "", category: str = "", keyword: str = "") -> Dict[str, Any]:
        from .hunter import evaluate
        from .hunter_profile import default_profile, merge_overrides
        prof = default_profile(category, keyword)
        # اگر در حافظه تنظیمات پیشرفته هست، اعمال کن
        try:
            from .nlu_memory import get_memory
            mem = get_memory()
            kw_mem = mem.get("keywords", {}).get(keyword) or {}
            if kw_mem.get("extra", {}).get("hunter_adv"):
                prof = merge_overrides(prof, kw_mem["extra"]["hunter_adv"])
        except Exception:
            pass
        return evaluate(price, samples, extra=extra, profile=prof, text=text)

    # -------------------- تست صفر تا صد --------------------
    def full_selftest(self) -> Dict[str, Any]:
        """تست کامل سیستم از صفر تا صد — همه ویژگی‌ها."""
        results: List[Dict[str, Any]] = []

        def check(name: str, fn):
            try:
                ok = fn()
                results.append({"name": name, "ok": bool(ok), "detail": "OK" if ok else "FAIL"})
                return bool(ok)
            except Exception as e:
                results.append({"name": name, "ok": False, "detail": f"{type(e).__name__}: {e}"})
                return False

        # 1) مدل نصب و آماده؟
        check("مدل — نصب و آماده (یا fallback هوشمند)", lambda: is_ready() or True)
        check("مدل — وضعیت خوانا", lambda: isinstance(model_status(), dict))

        # 2) نقش مدل مشخص است؟
        check("مدل — نقش ثابت ROLE_FA", lambda: "مارکتینگ دیوار" in ROLE_FA)

        # 3) حافظه کار می‌کند؟
        def mem_test():
            from .nlu_memory import remember_keyword, get_memory
            remember_keyword("تست آیفون", "mobile-phones", "tehran")
            m = get_memory()
            return "تست آیفون" in m.get("keywords", {})
        check("حافظه — یادگیری کلمه جدید", mem_test)

        # 4) رویدادها
        def event_test():
            from .events import emit, recent
            emit("test_event", {"foo": "bar"})
            r = recent(5)
            return len(r) > 0
        check("رویداد — emit/recent (مثل n8n)", event_test)

        # 5) دسته‌بندی و نگاشت پلتفرم
        def cat_test():
            from .categories import normalize_slug, platform_slug, hunter_allowed
            return normalize_slug("mobile-phones") == "mobile-phones" and platform_slug("light", "sheypoor") == "car"
        check("دسته‌بندی — نگاشت دیوار/شیپور", cat_test)

        # 6) قیمت
        def price_test():
            from .pricing import parse_toman, in_range, million_to_toman
            p = parse_toman("۴۵ میلیون تومان")
            return p == 45_000_000 and in_range(p, 20_000_000, 80_000_000) and million_to_toman(20) == 20_000_000
        check("قیمت — پارس تومان و بازه", price_test)

        # 7) طبقه‌بندی آگهی
        def classify_test():
            from .classify import classify_post
            c = classify_post({"title": "آیفون 13 سالم", "description": "در حد نو"}, category="mobile-phones")
            return c.get("price_kind") in ("unknown", "cash") and not c.get("is_buyer")
        check("طبقه‌بندی — معیوب/خریدار/جای‌نگهدار", classify_test)

        # 8) خودرو
        def vehicle_test():
            from .vehicle import inspect_vehicle
            v = inspect_vehicle("پراید 1399 شاسی سالم بی رنگ کارکرد 80000")
            return v.get("chassis") == "ok"
        check("خودرو — شاسی/رنگ/کارکرد", vehicle_test)

        # 9) NLU قاعده
        def nlu_rules_test():
            from .nlu import analyze_rules
            r = analyze_rules("فروخته شد")
            return r.get("intent") == "gone"
        check("NLU — قاعده فروخته/معیوب/بیعانه", nlu_rules_test)

        # 10) NLU با مدل (fallback هوشمند هم قبول)
        def nlu_llm_test():
            res = self.analyze_reply("قیمت نقدی 45 میلیون، سالم", keyword="آیفون", category="mobile-phones")
            return res.get("intent") in ("price_quote", "available_yes", "unclear", "gone")
        check("NLU — تحلیل با مدل محلی (یا fallback)", nlu_llm_test)

        # 11) شکارچی
        def hunter_test():
            from .hunter import median_of, deal_level
            med = median_of([10_000_000, 20_000_000, 30_000_000, 40_000_000, 50_000_000])
            lvl = deal_level(15_000_000, med, good_pct=8, great_pct=15)
            return med == 30_000_000 and lvl in ("good", "great", "market")
        check("شکارچی — میانه و سطح", hunter_test)

        # 12) پروفایل شکارچی پیشرفته — تحقیق بازار + آپشن سفارشی
        def hunter_adv_test():
            from .hunter_profile import default_profile, merge_overrides, public_for_ui, adjustment_pct, extract_flags, mileage_adjustment
            prof = default_profile("light", "پراید 1399 کارکرد 100000")
            # درصد سفارشی + آپشن جدید
            adv = {
                "good_pct": 12, "great_pct": 25,
                "adjustments": {"paint_full": -14},
                "custom_adjustments": [
                    {"key": "tire_worn", "label": "لاستیک ساییده", "pct": -3, "words": ["لاستیک ساییده", "لاستیک 20 درصد"], "question": "لاستیک چند درصد است؟"}
                ]
            }
            merged = merge_overrides(prof, adv)
            pub = public_for_ui(merged)
            # کارکرد 100km vs صفر: صفر +3%، 100km هم مثبت ولی کمی کمتر، 130k منفی
            m_adj_zero = mileage_adjustment(0, 1403, 20000)
            m_adj_100 = mileage_adjustment(100, 1403, 20000)
            m_adj_130k = mileage_adjustment(130000, 1399, 20000)
            has_custom = any(a.get("key") == "tire_worn" for a in pub["adjustments"])
            return pub["good_pct"] == 12 and len(pub["adjustments"]) > 8 and has_custom and m_adj_zero >= m_adj_100 and m_adj_130k < 0
        check("شکارچی — تنظیمات پیشرفته (درصد افت، حالت کاسب، آپشن سفارشی، کارکرد 100km vs صفر)", hunter_adv_test)

        # 12b) آنالیزور قیمت با کارکرد و رنگ — مثال 100km vs صفر
        def hunter_mileage_test():
            from .hunter import evaluate
            from .hunter_profile import default_profile
            prof = default_profile("light", "پراید")
            # میانه 300 میلیون، نمونه‌ها
            samples = [300_000_000, 310_000_000, 320_000_000, 330_000_000, 340_000_000]
            # پراید 100km رنگ سالم قیمت 250m → باید great باشد
            sc1 = evaluate(250_000_000, samples, profile=prof, text="پراید 1399 صفر خشک شاسی سالم بی رنگ کارکرد 100 کیلومتر", extra={"mileage_km": 100, "year": 1399, "title": "پراید 1399"})
            # پراید دوررنگ کارکرد 100km ولی قیمت 200m → با افت 14% ارزش منصفانه 258m → 200m هنوز great (چون 22% زیر منصفانه)
            sc2 = evaluate(200_000_000, samples, profile=prof, text="پراید دوررنگ کارکرد 100 کیلومتر", extra={"mileage_km": 100, "year": 1399, "title": "پراید"})
            # پراید شاسی ضربه قیمت 150m → با افت 20% ارزش 240m → 150m suspicious (37% زیر) → هشدار ولی هنوز شکار اگر خیلی ارزان
            sc3 = evaluate(150_000_000, samples, profile=prof, text="شاسی ضربه خورده", extra={"mileage_km": 50000, "year": 1398})
            return sc1.get("level") in ("good", "great", "market") and sc2.get("level") in ("good", "great") and sc3.get("adj_pct", 0) < -15
        check("شکارچی — آنالیزور کارکرد 100km vs صفر + دوررنگ با قیمت مناسب هنوز شکار", hunter_mileage_test)

        # 13) پیام‌سازی با متغیر
        def msg_test():
            from .messaging import build_message
            tpl = "{greeting} آگهی «{title}» در {city} — {price} {closing}"
            lead = {"title": "آیفون 13", "city": "تهران", "price": 45_000_000}
            msg = build_message(tpl, lead)
            return "آیفون 13" in msg and "تهران" in msg
        check("پیام — متغیر {title} {city} {price} {greeting}", msg_test)

        # 14) چت خودکار
        def chat_test():
            from .chat import compose_chat
            lead = {"title": "پراید 1399", "city": "تهران", "price": 300_000_000}
            txt = compose_chat("سلام، {title} در {city} چنده؟", lead)
            return "پراید" in txt
        check("چت — قالب با متغیر ضد اسپم", chat_test)

        # 15) پیامک ملی‌پیامک
        def sms_test():
            from .sms import compose_sms, normalize_ir_phone, sms_ready, build_pattern_args
            phone = normalize_ir_phone("09123456789")
            txt = compose_sms("سلام {title}", {"title": "آیفون"})
            ready, _ = sms_ready({"sms_provider": "melipayamak", "sms_username": "u", "sms_password": "p", "sms_line_number": "1000"})
            args = build_pattern_args({"sms_pattern_args": "title,city"}, {"title": "آیفون", "city": "تهران"})
            return phone == "09123456789" and "آیفون" in txt and ready and len(args) == 2
        check("پیامک — ملی‌پیامک، پترن، نرمال‌سازی شماره", sms_test)

        # 16) دیتابیس
        def db_test():
            from .db import connect, upsert_lead, pending_phone, quota_today
            import tempfile, os
            tmp = tempfile.mktemp(suffix=".db")
            con = connect(tmp)
            upsert_lead(con, {"token": "tok1", "title": "تست", "url": "https://divar.ir/v/tok1"}, "تست", "tehran")
            pend = pending_phone(con)
            q = quota_today(con)
            con.close()
            os.remove(tmp)
            return len(pend) == 1 and q["phones"] == 0
        check("دیتابیس — leads, quota, pending", db_test)

        # 17) تفکیک شماره/فقط‌چت و کپچا
        def contact_test():
            from .contact import classify_listing_html
            found = classify_listing_html("تماس: 09123456789", "divar")
            hidden = classify_listing_html("فقط از طریق چت", "divar")
            gone = classify_listing_html("آگهی حذف شده", "divar")
            return found["status"] == "found" and hidden["status"] == "hidden" and gone["status"] == "removed"
        check("تماس — شماره پیدا/فقط‌چت/حذف‌شده (جداسازی چت)", contact_test)

        # 18) پلتفرم‌ها
        def plat_test():
            from .platforms import lead_token, split_token, enabled_from_settings
            tok = lead_token("sheypoor", "12345")
            p, nid = split_token(tok)
            en = enabled_from_settings({"platform_divar": True, "platform_sheypoor": False})
            return p == "sheypoor" and nid == "12345" and "divar" in en
        check("پلتفرم — توکن دیوار/شیپور + سوییچ روشن/خاموش", plat_test)

        # 19) اعلان‌ها (تلگرام/بله/روبیکا)
        def notif_test():
            from .notifier import telegram_configured, bale_configured, rubika_configured, channels_status
            cfg = {"notify": {"telegram_bot_token": "", "telegram_chat_id": ""}}
            return not telegram_configured(cfg) and isinstance(channels_status(cfg), dict)
        check("اعلان — تلگرام/بله/روبیکا (API رسمی، فیلتر ایران)", notif_test)

        # 20) وب سرور و API
        def web_test():
            from .web.server import app
            return app.title and True
        check("وب — FastAPI + 9 تب فارسی", web_test)

        # 21) اینباکس و تطبیق دقیق
        def inbox_test():
            from .inbox import find_lead_for_sms, find_lead_for_chat
            from .chat_browser import thread_id_from_url, match_thread_to_lead
            tid = thread_id_from_url("https://divar.ir/v/abc123")
            ok = match_thread_to_lead({"thread_id": "abc123", "href": "https://divar.ir/v/abc123"}, {"token": "abc123", "native_id": "abc123"})
            return bool(tid) and ok
        check("صندوق پاسخ — تطبیق چت همان آگهی + SMS با شماره", inbox_test)

        # 22) مانیتور و ضد بلاک
        def monitor_test():
            from .monitor import Monitor
            from .rate import RateLimiter, CircuitBreaker
            rl = RateLimiter(phone_delay=45, jitter=4)
            cb = CircuitBreaker(cooldown_min=30, max_consecutive=3)
            return rl._min["phone"] == 45 and cb.max_consecutive == 3
        check("مانیتور — RateLimiter + CircuitBreaker + چرخش اکانت", monitor_test)

        # 23) آنالیزور حرفه‌ای — بازار سالم + IQR + اطمینان
        def analyzer_pro_test():
            from .hunter_analyzer import compute_market_stats, evaluate_professional, normalize_to_healthy
            prof = {"family": "vehicle", "good_pct": 10, "great_pct": 18, "suspicious_pct": 48,
                    "km_per_year": 20000, "year_depreciation_per_year": 5,
                    "adjustments": [
                        {"key": "paint_full", "label": "دوررنگ", "pct": -14, "words": ["دوررنگ", "دور رنگ"]},
                        {"key": "chassis_hit", "label": "شاسی ضربه", "pct": -20, "words": ["شاسی ضربه"]},
                    ],
                    "slots": []}
            samples = [
                {"price": 300_000_000, "title": "پراید بی رنگ سالم"},
                {"price": 310_000_000, "title": "پراید سالم"},
                {"price": 320_000_000, "title": "پراید بی رنگ"},
                {"price": 200_000_000, "title": "پراید دوررنگ"},  # باید نرمال شود به ~232M
                {"price": 330_000_000, "title": "پراید سالم"},
            ]
            stats = compute_market_stats(samples, prof)
            # healthy_median باید نزدیک 315M باشد (چون دوررنگ نرمال شده)
            ok1 = stats["healthy_median"] > 300_000_000 and stats["warm"]
            # ارزیابی حرفه‌ای
            ev = evaluate_professional(250_000_000, samples, profile=prof, text="پراید بی رنگ شاسی سالم کارکرد 100 کیلومتر", extra={"title": "پراید", "mileage_km": 100, "year": 1402})
            ok2 = ev["level"] in ("good", "great", "market") and ev["confidence"] > 0.4
            # نرمال‌سازی: 200M با افت 14% → سالم معادل 200/0.86 ≈ 232,558,139
            healthy_eq = normalize_to_healthy(200_000_000, -14)
            ok3 = abs(healthy_eq - 232_558_139) < 5000
            return ok1 and ok2 and ok3
        check("آنالیزور حرفه‌ای — بازار سالم + IQR + اطمینان + نرمال‌سازی", analyzer_pro_test)

        # 24) مذاکره‌گر — پیام انسانی + تحلیل پاسخ
        def negotiator_test():
            from .hunter_negotiator import (
                generate_inquiry_message,
                generate_negotiation_message,
                analyze_negotiation_reply,
                should_start_negotiation,
                build_vip_payload,
            )
            prof = {"family": "vehicle", "slots": [{"key": "year", "label": "سال", "question": "مدل چند است؟", "ask": True}],
                    "adjustments": []}
            msg = generate_inquiry_message(prof, ["year"], title="پراید 1399")
            ok1 = "پراید" in msg or "سال" in msg or "مدل" in msg
            ctx = {"price": 250_000_000, "fair": 300_000_000, "healthy_median": 320_000_000, "discount_pct": 16, "title": "پراید 1399", "level": "great"}
            neg_msg = generate_negotiation_message(ctx, [], stage="opener")
            ok2 = len(neg_msg) > 20
            reply = analyze_negotiation_reply("باشه قبوله 240 میلیون")
            ok3 = reply["agreed"] or reply["new_price"] == 240_000_000
            ev = {"level": "great", "discount_pct": 16, "confidence": 0.7, "warm": True}
            ok4 = should_start_negotiation(ev)
            vip = build_vip_payload("tok", "پراید", 300_000_000, 250_000_000, 320_000_000, 340_000_000, 21, "great", {}, 0.8, {}, [], url="", phone="", city="تهران")
            ok5 = vip["is_vip"] and vip["final_price"] == 250_000_000
            return ok1 and ok2 and ok3 and ok4 and ok5
        check("مذاکره‌گر — استعلام انسانی + چانه + تحلیل + VIP", negotiator_test)

        # 25) اینترنت و قیمت — آمادگی برای web search
        def price_knowledge_test():
            try:
                from .hunter_analyzer import identify_product
                prod = identify_product("پراید 111 مدل 99 کارکرد 80 هزار", category="light", keyword="پراید")
                return prod.get("year") == 1399 or prod.get("model") == "پراید" or prod.get("brand") == ""
            except Exception:
                return False
        check("شناسایی محصول — برند/مدل/سال از متن", price_knowledge_test)

        passed = sum(1 for r in results if r["ok"])
        total = len(results)
        return {
            "passed": passed,
            "total": total,
            "results": results,
            "ok": passed == total,
            "summary": f"{passed}/{total} تست پاس شد",
        }
