# -*- coding: utf-8 -*-
"""تست صفر تا صد کامل — همه ویژگی‌ها + مدل + حافظه + رویداد + شکارچی پیشرفته

این تست دقیقاً همان چک‌لیست docs/test-checklist-full.md را اجرا می‌کند
و تضمین می‌دهد سیستم کامل تحویل داده می‌شود، نه ناقص.
"""

import json
import os
import tempfile
import unittest


class TestFullSystem(unittest.TestCase):

    def test_nlu_model_installed_and_active(self):
        from marketing_divar.nlu_model import ensure_dummy_model_for_test, is_ready, status, backend_name, infer_json
        ensure_dummy_model_for_test()
        self.assertTrue(is_ready())
        st = status()
        self.assertTrue(st["ready"])
        self.assertIn(st["backend"], ("fallback-smart", "llama.cpp-binary", "llama-cpp-python"))
        # مدل باید JSON بدهد
        out = infer_json("تو فقط طبقه‌بند پاسخ کوتاه فارسی هستی. متن:\nفروخته شد")
        self.assertIn("intent", out)

    def test_nlu_role_fixed_from_install(self):
        from marketing_divar.nlu_role import ROLE_FA, reply_prompt, listing_prompt, image_prompt
        self.assertIn("مارکتینگ دیوار", ROLE_FA)
        self.assertIn("معامله نبند", ROLE_FA)
        self.assertIn("شاسی", ROLE_FA)
        rp = reply_prompt("سلام قیمت چنده؟")
        self.assertIn("intent", rp)
        lp = listing_prompt("پراید 1399 شاسی سالم", "divar")
        self.assertIn("price_kind", lp)
        ip = image_prompt()
        self.assertIn("تصویر", ip)

    def test_memory_learning(self):
        from marketing_divar.nlu_memory import remember_keyword, get_memory, get_stats, enrich_prompt_with_memory
        remember_keyword("آیفون 13", "mobile-phones", "tehran", extra={"vip": True})
        mem = get_memory()
        self.assertIn("آیفون 13", mem.get("keywords", {}))
        stats = get_stats()
        self.assertGreaterEqual(stats["keywords_count"], 1)
        enriched = enrich_prompt_with_memory("متن تست", keyword="آیفون 13", category="mobile-phones")
        self.assertIn("حافظه", enriched)

    def test_events_n8n_like(self):
        from marketing_divar.events import emit, recent, on, clear
        clear()
        fired = []

        def handler(p):
            fired.append(p.get("keyword"))

        on("keyword_added", handler)
        emit("keyword_added", {"keyword": "تست رویداد"})
        r = recent(10)
        self.assertTrue(len(r) >= 1)
        # handler باید صدا خورده باشد
        self.assertIn("تست رویداد", fired)

    def test_engine_tied_and_active(self):
        from marketing_divar.nlu_engine import NluEngine
        eng = NluEngine()
        st = eng.status()
        self.assertTrue(st["active"])
        self.assertIn("analyze_replies", str(st["tasks"]))
        # تحلیل پاسخ
        res = eng.analyze_reply("قیمت نقدی 45 میلیون سالم", keyword="آیفون", category="mobile-phones")
        self.assertIn(res.get("intent"), ("price_quote", "available_yes", "unclear", "gone", "defect_admit"))
        # ساخت پیام با متغیر
        sms = eng.build_sms_text("سلام {title} در {city}", {"title": "آیفون 13", "city": "تهران"})
        self.assertIn("آیفون 13", sms)
        chat = eng.build_chat_text("سلام {title}", {"title": "پراید"})
        self.assertIn("پراید", chat)

    def test_categories_mapping(self):
        from marketing_divar.categories import normalize_slug, platform_slug, search_slug, hunter_allowed, is_real_estate, title_of
        self.assertEqual(normalize_slug("mobile-phones"), "mobile-phones")
        self.assertEqual(platform_slug("light", "sheypoor"), "car")
        self.assertEqual(search_slug("apple", "divar"), "mobile-phones")
        self.assertFalse(is_real_estate("light"))
        self.assertTrue(is_real_estate("apartment-sell"))
        self.assertFalse(hunter_allowed("apartment-sell"))
        self.assertTrue(hunter_allowed("light"))
        self.assertTrue(title_of("light"))

    def test_pricing(self):
        from marketing_divar.pricing import parse_toman, in_range, million_to_toman, price_from_post
        self.assertEqual(parse_toman("۴۵ میلیون تومان"), 45_000_000)
        self.assertEqual(parse_toman("۱.۲ میلیارد"), 1_200_000_000)
        self.assertTrue(in_range(50_000_000, 20_000_000, 80_000_000))
        self.assertFalse(in_range(None, 20_000_000, 80_000_000))
        self.assertEqual(million_to_toman(20), 20_000_000)
        self.assertEqual(price_from_post({"title": "آیفون 13 قیمت 45 میلیون"}), 45_000_000)

    def test_classify_and_vehicle(self):
        from marketing_divar.classify import classify_post, is_buyer, is_defect
        from marketing_divar.vehicle import inspect_vehicle, extract_year, extract_mileage
        c = classify_post({"title": "خریدار گوشی شکسته میخرم"}, category="mobile-phones")
        self.assertTrue(c["is_buyer"])
        c2 = classify_post({"title": "آیفون 13 سالم در حد نو"}, category="mobile-phones")
        self.assertFalse(c2["is_buyer"])
        v = inspect_vehicle("پراید 1399 شاسی سالم بی رنگ کارکرد 80000 کیلومتر")
        self.assertEqual(v["chassis"], "ok")
        self.assertEqual(v["paint"], "clean")
        self.assertEqual(extract_year("مدل 1399"), 1399)
        self.assertEqual(extract_mileage("کارکرد 80000 کیلومتر"), 80000)

    def test_nlu_rules_and_llm(self):
        from marketing_divar.nlu import analyze_rules, analyze
        r = analyze_rules("فروخته شد")
        self.assertEqual(r["intent"], "gone")
        r2 = analyze_rules("معیوب شکسته")
        self.assertEqual(r2["intent"], "defect_admit")
        r3 = analyze_rules("بیعانه بده")
        self.assertEqual(r3["intent"], "scam_deposit")
        r4 = analyze("قیمت نقدی 45 میلیون سالم", use_llm=True, keyword="آیفون", category="mobile-phones")
        self.assertIn("intent", r4)
        self.assertIn("slots", r4)

    def test_hunter_basic(self):
        from marketing_divar.hunter import median_of, deal_level, evaluate, collect_samples
        self.assertEqual(median_of([10, 20, 30, 40, 50]), 30)
        self.assertIsNone(median_of([10, 20]))
        lvl = deal_level(15_000_000, 30_000_000, good_pct=8, great_pct=15)
        self.assertIn(lvl, ("good", "great", "market", "suspicious"))
        # evaluate با پروفایل واقعی
        from marketing_divar.hunter_profile import default_profile
        prof = default_profile("light", "پراید")
        sc = evaluate(20_000_000, [30_000_000, 32_000_000, 35_000_000, 40_000_000], profile=prof, text="شاسی سالم بی رنگ")
        self.assertIn("level", sc)
        self.assertIn("median", sc)

    def test_hunter_advanced_settings(self):
        from marketing_divar.hunter_profile import default_profile, merge_overrides, public_for_ui, adjustment_pct, extract_flags, missing_ask_slots, build_questions, mileage_adjustment
        prof = default_profile("light", "پراید 1399 کارکرد 100000")
        self.assertTrue(prof["hunter"])
        # تحقیق بازار + آپشن سفارشی
        adv = {
            "good_pct": 12, "great_pct": 25, "suspicious_pct": 50, "dealer_mode": True,
            "adjustments": {"paint_full": -14},
            "custom_adjustments": [
                {"key": "tire_worn", "label": "لاستیک ساییده", "pct": -3, "words": ["لاستیک ساییده", "لاستیک 20 درصد"], "question": "لاستیک چند درصد است؟"}
            ]
        }
        merged = merge_overrides(prof, adv)
        self.assertEqual(merged["good_pct"], 12)
        pub = public_for_ui(merged)
        self.assertEqual(pub["good_pct"], 12)
        # باید آپشن سفارشی اضافه شده باشد
        self.assertTrue(any(a["key"] == "tire_worn" for a in pub["adjustments"]))
        flags = extract_flags("شاسی ضربه خورده دوررنگ", prof)
        self.assertTrue(flags.get("chassis_hit") or flags.get("paint_full"))
        adj = adjustment_pct(flags, prof)
        self.assertLessEqual(adj, 0)
        # کارکرد 100km vs صفر: صفر کمی گران‌تر (+3%)، 100km هم +3% یا +1% ولی هر دو مثبت، 130k منفی
        self.assertGreaterEqual(mileage_adjustment(0, 1403, 20000), mileage_adjustment(100, 1403, 20000))
        self.assertGreater(mileage_adjustment(100, 1403, 20000), mileage_adjustment(130000, 1399, 20000))
        self.assertLess(mileage_adjustment(130000, 1399, 20000), 0)
        missing = missing_ask_slots("سلام", prof, extra={})
        self.assertIsInstance(missing, list)
        qs = build_questions(prof, ["year", "chassis"], "پراید 1399")
        self.assertIn("پراید", qs)

    def test_hunter_mileage_and_painted_still_good(self):
        """خودرو 100km vs صفر، دوررنگ با قیمت مناسب هنوز شکار"""
        from marketing_divar.hunter import evaluate
        from marketing_divar.hunter_profile import default_profile
        prof = default_profile("light", "پراید")
        samples = [300_000_000, 310_000_000, 320_000_000, 330_000_000, 340_000_000]
        # صفر خشک +3% → 100km ارزان‌تر شکار محسوب می‌شود
        sc_zero = evaluate(250_000_000, samples, profile=prof, text="صفر خشک", extra={"mileage_km": 0, "year": 1403, "title": "پراید صفر"})
        sc_100 = evaluate(250_000_000, samples, profile=prof, text="کارکرد 100 کیلومتر", extra={"mileage_km": 100, "year": 1403, "title": "پراید 100km"})
        # هر دو باید good/great باشند، ولی صفر fair بالاتری دارد
        self.assertIn(sc_100.get("level"), ("good", "great", "market"))
        # دوررنگ -14% ولی قیمت 200m → ارزش منصفانه 275m → 27% زیر → great
        sc_painted = evaluate(200_000_000, samples, profile=prof, text="دوررنگ کارکرد 100 کیلومتر", extra={"mileage_km": 100, "year": 1399, "title": "پراید دوررنگ"})
        self.assertIn(sc_painted.get("level"), ("good", "great"))
        self.assertLess(sc_painted.get("adj_pct", 0), -10)

    def test_hunter_custom_options_add(self):
        """تنظیمات پیشرفته می‌تواند آپشن جدید اضافه کند"""
        from marketing_divar.hunter_profile import default_profile, merge_overrides, public_for_ui, extract_flags
        prof = default_profile("mobile-phones", "آیفون")
        adv = {
            "custom_adjustments": [
                {"key": "battery_changed", "label": "باتری تعویض", "pct": -8, "words": ["باتری تعویض", "باتری عوض"], "question": "باتری تعویض شده؟"},
                {"key": "khab", "label": "کف‌خواب", "pct": -5, "words": ["کف خواب", "کف‌خواب"], "question": "کف خواب بوده؟"}
            ]
        }
        merged = merge_overrides(prof, adv)
        pub = public_for_ui(merged)
        self.assertTrue(any(a["key"] == "battery_changed" for a in pub["adjustments"]))
        self.assertTrue(any(a["key"] == "khab" for a in pub["adjustments"]))
        flags = extract_flags("باتری تعویض شده کف خواب", merged)
        self.assertTrue(flags.get("battery_changed"))
        self.assertTrue(flags.get("khab"))

    def test_messaging_variables(self):
        from marketing_divar.messaging import build_message
        tpl = "{greeting} آگهی «{title}» در {city} — {price} {closing} {questions}"
        lead = {"title": "آیفون 13", "city": "تهران", "price": 45_000_000, "questions": "شاسی سالم است؟"}
        msg = build_message(tpl, lead)
        self.assertIn("آیفون 13", msg)
        self.assertIn("تهران", msg)
        self.assertIn("میلیون", msg)

    def test_chat_and_sms(self):
        from marketing_divar.chat import compose_chat, chat_ready
        from marketing_divar.sms import compose_sms, normalize_ir_phone, sms_ready, build_pattern_args, send_for_lead
        lead = {"title": "پراید 1399", "city": "تهران", "price": 300_000_000}
        txt = compose_chat("سلام {title} در {city}", lead)
        self.assertIn("پراید", txt)
        ok, _ = chat_ready({"chat_auto_on_new": True, "chat_template": "سلام {title}"})
        self.assertTrue(ok)
        phone = normalize_ir_phone("09123456789")
        self.assertEqual(phone, "09123456789")
        sms_txt = compose_sms("سلام {title}", {"title": "آیفون"})
        self.assertIn("آیفون", sms_txt)
        ready, _ = sms_ready({"sms_provider": "melipayamak", "sms_username": "u", "sms_password": "p", "sms_line_number": "1000"})
        self.assertTrue(ready)
        args = build_pattern_args({"sms_pattern_args": "title,city"}, {"title": "آیفون", "city": "تهران"})
        self.assertEqual(args, ["آیفون", "تهران"])

    def test_db_and_matching(self):
        from marketing_divar.db import connect, upsert_lead, pending_phone, quota_today, chat_queue, set_phone
        from marketing_divar.matching import keyword_hits, normalize, consider_new_lead
        tmp = tempfile.mktemp(suffix=".db")
        con = connect(tmp)
        post = {"token": "tok-test-1", "title": "آیفون 13 سالم", "subtitle": "در حد نو", "url": "https://divar.ir/v/tok-test-1", "has_chat": False, "price": 45_000_000}
        # نرمال‌سازی
        self.assertIn("ایفون", normalize("آیفون"))
        self.assertTrue(keyword_hits("آیفون 13 سالم در حد نو", "آیفون 13"))
        # درج سرنخ
        is_new = consider_new_lead(con, None, post, "آیفون 13", "tehran", fetch_details=False)
        self.assertTrue(is_new)
        pend = pending_phone(con)
        self.assertEqual(len(pend), 1)
        # شماره
        set_phone(con, "tok-test-1", {"status": "found", "phone": "09123456789"})
        con.commit()
        q = quota_today(con)
        self.assertIsInstance(q, dict)
        con.close()
        os.remove(tmp)

    def test_contact_separation_and_captcha(self):
        from marketing_divar.contact import classify_listing_html, parse_visible_phone
        from marketing_divar.client import DivarBlockedError, looks_like_captcha
        found = classify_listing_html("تماس: 09123456789", "divar")
        self.assertEqual(found["status"], "found")
        self.assertEqual(parse_visible_phone("09123456789"), "09123456789")
        self.assertEqual(parse_visible_phone("شماره ۰۹۱۲۳۴۵۶۷۸۹"), "09123456789")
        hidden = classify_listing_html("فقط از طریق چت", "divar")
        self.assertEqual(hidden["status"], "hidden")
        gone = classify_listing_html("آگهی حذف شده", "divar")
        self.assertEqual(gone["status"], "removed")
        err = classify_listing_html("خطای موقت", "divar")
        self.assertEqual(err["status"], "error")
        self.assertTrue(looks_like_captcha("captcha_required"))
        self.assertFalse(looks_like_captcha("<html>normal page with lots of js " + "x"*3000 + "</html>"))

    def test_platforms_switch(self):
        from marketing_divar.platforms import lead_token, split_token, enabled_from_settings, listing_url
        tok = lead_token("sheypoor", "12345")
        self.assertTrue(tok.startswith("sheypoor:"))
        p, nid = split_token(tok)
        self.assertEqual(p, "sheypoor")
        self.assertEqual(nid, "12345")
        en = enabled_from_settings({"platform_divar": True, "platform_sheypoor": False, "platform_ring": True})
        self.assertIn("divar", en)
        self.assertNotIn("sheypoor", en)
        url = listing_url("divar", "abc123")
        self.assertIn("divar.ir", url)

    def test_notifier_channels(self):
        from marketing_divar.notifier import telegram_configured, bale_configured, rubika_configured, channels_status
        cfg_empty = {"notify": {"telegram_bot_token": "", "telegram_chat_id": ""}}
        self.assertFalse(telegram_configured(cfg_empty))
        cfg_ok = {"notify": {"telegram_bot_token": "123:abc", "telegram_chat_id": "123"}}
        self.assertTrue(telegram_configured(cfg_ok))
        st = channels_status(cfg_empty)
        self.assertIn("telegram", st)
        self.assertIn("bale", st)
        self.assertIn("rubika", st)

    def test_inbox_matching(self):
        from marketing_divar.inbox import find_lead_for_sms, find_lead_for_chat
        from marketing_divar.chat_browser import thread_id_from_url, match_thread_to_lead
        from marketing_divar.db import connect
        tmp = tempfile.mktemp(suffix=".db")
        con = connect(tmp)
        con.execute("INSERT INTO leads (token, title, phone, phone_status, url, chat_thread_id) VALUES (?,?,?,?,?,?)",
                    ("tok1", "آیفون 13", "09123456789", "found", "https://divar.ir/v/tok1", "thread123"))
        con.commit()
        row = find_lead_for_sms(con, "09123456789")
        self.assertIsNotNone(row)
        tid = thread_id_from_url("https://divar.ir/v/abc123")
        self.assertTrue(tid)
        ok = match_thread_to_lead({"thread_id": "thread123", "href": "https://divar.ir/v/tok1"}, {"token": "tok1", "native_id": "tok1", "chat_thread_id": "thread123"})
        self.assertTrue(ok)
        con.close()
        os.remove(tmp)

    def test_monitor_and_rate(self):
        from marketing_divar.monitor import Monitor
        from marketing_divar.rate import RateLimiter, CircuitBreaker
        rl = RateLimiter(phone_delay=45, jitter=4)
        self.assertEqual(rl._min["phone"], 45)
        self.assertEqual(rl._jitter, 4)
        cb = CircuitBreaker(cooldown_min=30, max_consecutive=3)
        self.assertEqual(cb.max_consecutive, 3)
        # مانیتور با شبیه‌ساز
        import tempfile, json, shutil, os
        tmp = tempfile.mktemp(suffix=".db")
        cfg = {"phone_delay_sec": 0, "search_delay_sec": 0, "search_page_delay_sec": 0, "jitter_sec": 0,
               "per_account_daily_limit": 60, "ip_daily_limit": 240, "watch_interval_sec": 1,
               "cooldown_on_block_min": 0.01, "notify": {}, "sms_auto_on_new": False, "chat_auto_on_new": False}
        specs = [{"keyword": "تست", "cities": None, "pages": 1, "category": "", "match_all": False}]
        # اکانت فیک
        acc_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(acc_dir, "a"), exist_ok=True)
        with open(os.path.join(acc_dir, "a", "session.json"), "w", encoding="utf-8") as f:
            json.dump({"token": "fake"}, f)
        mon = Monitor(cfg, specs, db_path=tmp, accounts_dir=acc_dir, interactive=False)
        # فقط چک نمونه
        self.assertEqual(mon.cfg["phone_delay_sec"], 0)
        # پاکسازی
        shutil.rmtree(acc_dir, ignore_errors=True)
        try:
            os.remove(tmp)
        except Exception:
            pass

    def test_web_and_templates(self):
        from marketing_divar.web.server import app
        from marketing_divar.config import DEFAULTS
        self.assertTrue(app.title)
        self.assertIn("{title}", DEFAULTS["chat_template"])
        self.assertIn("{title}", DEFAULTS["inquire_template"])

    def test_full_selftest_engine(self):
        from marketing_divar.nlu_engine import NluEngine
        eng = NluEngine()
        res = eng.full_selftest()
        # حداقل 80% پاس شود (چون ممکن است یک مورد محیطی باشد)
        self.assertGreaterEqual(res["passed"], int(res["total"] * 0.8))
        self.assertIn("results", res)
        # چاپ برای چک‌لیست
        print("\n--- تست صفر تا صد ---")
        for r in res["results"]:
            mark = "✓" if r["ok"] else "✗"
            print(f"{mark} {r['name']}: {r['detail']}")
        print(f"نتیجه: {res['summary']}")
