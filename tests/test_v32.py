# -*- coding: utf-8 -*-
"""۳.۲.۰: پروفایل شکارچی هر دسته، تنظیمات پیشرفته، برند موبایل، استعلام جای‌خالی."""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


class TestMobileBrands(unittest.TestCase):
    def test_tree_and_search_slug(self):
        from marketing_divar.categories import (
            hunter_allowed, is_real_estate, public_list, search_slug, title_of,
        )
        slugs = {c["slug"] for c in public_list()}
        for s in ("apple", "samsung", "xiaomi", "huawei", "macbook", "asus-laptop"):
            self.assertIn(s, slugs)
        self.assertIn("آیفون", title_of("apple"))
        self.assertEqual(search_slug("samsung", "divar"), "mobile-phones")
        self.assertEqual(search_slug("macbook", "divar"), "laptops")
        self.assertEqual(search_slug("samsung", "sheypoor"), "mobile-tablet")
        self.assertTrue(is_real_estate("apartment-sell"))
        self.assertFalse(hunter_allowed("apartment-sell"))
        self.assertTrue(hunter_allowed("light"))
        self.assertTrue(hunter_allowed("apple"))


class TestHunterProfile(unittest.TestCase):
    def test_keyword_picks_family(self):
        from marketing_divar.hunter_profile import (
            default_profile, extract_flags, guess_category, merge_overrides,
        )
        self.assertEqual(guess_category("آیفون ۱۳"), "apple")
        self.assertEqual(guess_category("پراید ۱۱۱"), "light")
        self.assertEqual(guess_category("لپ تاپ ایسوس"), "laptops")
        phone = default_profile("", "آیفون")
        self.assertEqual(phone["family"], "phone")
        self.assertTrue(phone["hunter"])
        car = default_profile("light", "پراید")
        self.assertEqual(car["family"], "vehicle")
        estate = default_profile("apartment-sell", "")
        self.assertFalse(estate["hunter"])
        flags = extract_flags("گلگیر رنگ شاسی سالم بی رنگ", car)
        self.assertTrue(flags.get("paint_panel"))
        merged = merge_overrides(car, {"adjustments": {"paint_panel": -5}, "good_pct": 12})
        panel = next(a for a in merged["adjustments"] if a["key"] == "paint_panel")
        self.assertEqual(panel["pct"], -5)
        self.assertEqual(merged["good_pct"], 12)

    def test_paint_is_haircut_not_block(self):
        from marketing_divar.hunter import evaluate
        from marketing_divar.hunter_profile import default_profile
        from marketing_divar.listing_inspect import inspect_listing
        from marketing_divar.vehicle import inspect_vehicle
        hit = inspect_vehicle("پراید شاسی ضربه خورده دور رنگ")
        self.assertEqual(hit["chassis"], "hit")
        self.assertFalse(hit["hunter_block"])
        ins = inspect_listing(
            {"title": "سمند گلگیر رنگ", "price": 200_000_000, "category": "light"},
            use_llm=False)
        self.assertFalse(ins["hunter_block"])
        samples = [220_000_000] * 6
        prof = default_profile("light", "پراید")
        sc = evaluate(200_000_000, samples, extra={
            "paint": "repainted", "title": "پراید گلگیر رنگ", "category": "light",
        }, profile=prof, text="پراید گلگیر رنگ")
        self.assertFalse(sc["blocked"])
        self.assertLess(sc["fair"], sc["median"])
        self.assertIn(sc["raw_level"], ("good", "great", "market", "none"))

    def test_lenient_thresholds_find_deals(self):
        from marketing_divar.hunter import evaluate, median_of
        from marketing_divar.hunter_profile import default_profile
        self.assertIsNone(median_of([1, 2]))
        self.assertIsNotNone(median_of([10_000_000] * 3))
        samples = [10_000_000] * 3
        prof = default_profile("mobile-phones", "آیفون")
        # آکبند 0% افت → ارزش منصفانه 10M، قیمت 9M → 10% تخفیف → good (آستانه جدید 10%)
        sc = evaluate(9_000_000, samples, extra={"category": "mobile-phones"},
                      profile=prof, text="آیفون آکبند پلمپ")
        self.assertEqual(sc["level"], "good")
        self.assertFalse(sc["pending"])

    def test_estate_never_hunts(self):
        from marketing_divar.hunter import evaluate
        from marketing_divar.hunter_profile import default_profile
        prof = default_profile("real-estate", "آپارتمان")
        sc = evaluate(1_000_000_000, [1_200_000_000] * 6, extra={}, profile=prof)
        self.assertTrue(sc["blocked"])

    def test_dealer_mode_pending_questions(self):
        from marketing_divar.hunter import evaluate
        from marketing_divar.hunter_profile import default_profile, merge_overrides
        prof = merge_overrides(default_profile("light", "پژو"), {"dealer_mode": True})
        sc = evaluate(180_000_000, [200_000_000] * 6,
                      extra={"title": "پژو ۲۰۶", "needs_inquiry": False,
                             "category": "light"},
                      profile=prof, text="پژو ۲۰۶ تمیز")
        self.assertTrue(sc["pending"] or sc["missing"])
        if sc["pending"]:
            self.assertEqual(sc["level"], "pending")
            self.assertTrue(sc["questions"])

    def test_store_hunter_adv_and_real_estate(self):
        from marketing_divar import store
        db = os.path.join(tempfile.mkdtemp(), "h.db")
        self.assertTrue(store.keywords_add(
            db, "آیفون", None, "apple", hunter=True,
            hunter_adv={"good_pct": 9, "adjustments": {"cracked": -12}}))
        rows = store.keywords_list(db)
        one = next(r for r in rows if r["keyword"] == "آیفون")
        self.assertTrue(one["hunter"])
        self.assertEqual(one["hunter_adv"]["good_pct"], 9)
        self.assertTrue(store.keywords_set_hunter_adv(db, one["id"], {"great_pct": 18}))
        self.assertEqual(store.keywords_list(db)[0]["hunter_adv"]["great_pct"], 18)
        self.assertTrue(store.keywords_add(db, "", None, "apartment-sell", hunter=True))
        estate = next(r for r in store.keywords_list(db) if r["category"] == "apartment-sell")
        self.assertFalse(estate["hunter"])
        specs = store.keywords_active_specs(db)
        iphone = next(s for s in specs if s["keyword"] == "آیفون")
        self.assertFalse(iphone["match_all"])
        self.assertEqual(iphone["category"], "apple")

    def test_nlu_rescore_on_inquire_reply(self):
        from marketing_divar.db import connect, upsert_lead
        from marketing_divar.nlu import analyze_rules, apply_to_lead
        db = os.path.join(tempfile.mkdtemp(), "n.db")
        con = connect(db)
        upsert_lead(con, {"token": "t1", "title": "پراید", "url": "u",
                          "price": 180_000_000, "has_chat": 1}, "پراید", "tehran")
        con.execute("UPDATE leads SET hunter_level='pending', inquiry_status='sent', "
                    "price=180000000 WHERE token='t1'")
        con.commit()
        nlu = analyze_rules("شاسی سالمه بیرنگه نقد ۱۸۰ میلیون")
        out = apply_to_lead(con, "t1", nlu, context="inquire")
        self.assertIn(out.get("acted"), ("price", "none"))
        row = con.execute("SELECT inquiry_status, chassis, paint FROM leads "
                          "WHERE token='t1'").fetchone()
        self.assertEqual(row["inquiry_status"], "answered")

    def test_inquire_template_has_questions(self):
        from marketing_divar.chat import compose_chat
        from marketing_divar.config import DEFAULTS
        from marketing_divar.hunter_profile import build_questions, default_profile
        prof = default_profile("light", "پراید")
        q = build_questions(prof, ["year", "mileage_km"], "پراید ۱۳")
        self.assertIn("مدل", q)
        text = compose_chat(DEFAULTS["inquire_template"], {
            "title": "پراید ۱۳", "questions": q,
        })
        self.assertIn("پراید ۱۳", text)
        self.assertIn("مدل", text)


class TestPanelNeedles(unittest.TestCase):
    def test_index_has_adv_dialog(self):
        path = os.path.join(ROOT, "marketing_divar", "web", "static", "index.html")
        html = open(path, encoding="utf-8").read()
        self.assertIn("hunter-adv-dlg", html)
        self.assertIn("hunterAdvOpen", html)
        self.assertIn("/api/hunter-profile", html)
        self.assertIn("تنظیمات پیشرفته شکارچی", html)
        self.assertIn("hunter_pending", html)


if __name__ == "__main__":
    unittest.main()
