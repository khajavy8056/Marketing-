# -*- coding: utf-8 -*-
"""۳.۱.۰: پلتفرم، دسته/شهر، خودرو، مدل کنار برنامه، تحلیل سه‌سایت."""

import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


class TestPlatformToggle(unittest.TestCase):
    def test_enabled_from_settings(self):
        from marketing_divar.platforms import enabled_from_settings
        self.assertEqual(enabled_from_settings({"platform_divar": False,
                                                "platform_sheypoor": True,
                                                "platform_ring": False}),
                         ["sheypoor"])
        self.assertEqual(enabled_from_settings({"platform_divar": False,
                                                "platform_sheypoor": False,
                                                "platform_ring": False}),
                         ["divar"])

    def test_monitor_skips_divar_when_off(self):
        from marketing_divar.monitor import Monitor
        tmp = tempfile.mkdtemp()
        db = os.path.join(tmp, "p.db")
        acc = os.path.join(tmp, "acc")
        os.makedirs(acc)
        from marketing_divar import store
        store.settings_set(db, "platform_divar", False)
        store.settings_set(db, "platform_sheypoor", False)
        store.settings_set(db, "platform_ring", False)

        class Fake:
            def search(self, *a, **k):
                raise AssertionError("divar search must not run")

        mon = Monitor({"watch_interval_sec": 1}, [
            {"keyword": "x", "cities": None, "pages": 1, "category": "light",
             "match_all": True}], db_path=db, accounts_dir=acc, interactive=False)
        mon._anon = Fake()
        # fallback enabled_from_settings all-off → divar; override by setting one on
        store.settings_set(db, "platform_sheypoor", True)
        with mock.patch("marketing_divar.sheypoor.search", return_value=[]):
            n = mon.watch_once()
        self.assertEqual(n, 0)


class TestCategoryMap(unittest.TestCase):
    def test_complete_tree_and_map(self):
        from marketing_divar.categories import (platform_slug, public_list,
                                                is_vehicle)
        slugs = {c["slug"] for c in public_list()}
        for s in ("light", "mobile-phones", "shop-sell", "washers", "bicycle"):
            self.assertIn(s, slugs)
        self.assertEqual(platform_slug("light", "sheypoor"), "car")
        self.assertEqual(platform_slug("light", "ring"), "vehicles")
        self.assertEqual(platform_slug("light", "divar"), "light")
        self.assertEqual(platform_slug("apartment-sell", "sheypoor"),
                         "houses-apartments-for-sale")
        self.assertTrue(is_vehicle("light"))
        self.assertFalse(is_vehicle("jobs"))

    def test_sheypoor_uses_map(self):
        from marketing_divar.sheypoor import category_slug, search_url
        self.assertEqual(category_slug("light"), "car")
        url = search_url("tehran", "car", "پراید")
        self.assertIn("/s/tehran/car", url)


class TestCitiesMulti(unittest.TestCase):
    def test_complete_and_multi(self):
        from marketing_divar.cities import (CITIES, parse_city_ids, public_list,
                                            slug_for_platform, slug_of)
        self.assertGreaterEqual(len(public_list()), 80)
        self.assertEqual(slug_of(1), "tehran")
        self.assertEqual(parse_city_ids([1, 3, 0]), [1, 3])
        self.assertIsNone(parse_city_ids([0]))
        self.assertEqual(parse_city_ids("1,3"), [1, 3])
        self.assertTrue(any(c["slug"] == "rasht" for c in CITIES))
        self.assertTrue(any(c["title"] == "چابهار" for c in CITIES))
        self.assertEqual(slug_for_platform(1, "sheypoor"), "tehran")

    def test_store_multi_city(self):
        from marketing_divar import store
        db = os.path.join(tempfile.mkdtemp(), "c.db")
        self.assertTrue(store.keywords_add(db, "پراید", [1, 11], "light"))
        rows = store.keywords_list(db)
        self.assertEqual(rows[0]["cities"], [1, 11])
        self.assertIn("تهران", rows[0]["city_title"])
        self.assertIn("رشت", rows[0]["city_title"])


class TestVehicleHunter(unittest.TestCase):
    def test_chassis_paint_block_hunter(self):
        from marketing_divar.listing_inspect import inspect_listing
        from marketing_divar.vehicle import inspect_vehicle
        hit = inspect_vehicle("پراید مدل ۱۳۹۰ شاسی ضربه خورده دور رنگ کارکرد 200000 کیلومتر")
        self.assertEqual(hit["chassis"], "hit")
        self.assertEqual(hit["paint"], "repainted")
        self.assertTrue(hit["hunter_block"])
        self.assertEqual(hit["year"], 1390)
        self.assertEqual(hit["mileage_km"], 200000)
        ok = inspect_vehicle("پژو ۲۰۶ شاسی سالم بی رنگ مدل ۱۳۹۸")
        self.assertEqual(ok["chassis"], "ok")
        self.assertEqual(ok["paint"], "clean")
        self.assertFalse(ok["hunter_block"])
        post = {"title": "سمند تصادفی شاسی رنگ", "price": 80_000_000,
                "category": "light", "platform": "sheypoor"}
        ins = inspect_listing(post, use_llm=False)
        self.assertTrue(ins["hunter_block"])
        self.assertEqual(ins["platform"], "sheypoor")

    def test_images_counted_without_vision(self):
        from marketing_divar.listing_inspect import inspect_images, inspect_listing
        r = inspect_images(["https://cdn.example.com/a.jpg", "https://x.com/b.png"])
        self.assertEqual(r["count"], 2)
        self.assertFalse(r["reviewed"])
        post = {"title": "تیبا", "description": "عکس https://cdn.divar.ir/x.jpg",
                "category": "light"}
        ins = inspect_listing(post, use_llm=False)
        self.assertGreaterEqual(ins["images"]["count"], 1)


class TestNluThreePlatforms(unittest.TestCase):
    def test_same_analyzer_all_platforms(self):
        from marketing_divar.nlu import analyze_for_platform, analyze_rules
        from marketing_divar.nlu_role import ROLE_FA
        self.assertIn("شاسی", ROLE_FA)
        self.assertIn("معامله", ROLE_FA)
        for plat in ("divar", "sheypoor", "ring"):
            r = analyze_for_platform("فروختم دیگه موجود نیست", plat, use_llm=False)
            self.assertEqual(r["intent"], "gone")
            self.assertEqual(r["platform"], plat)
        self.assertEqual(analyze_rules("صفحه شکسته معیوبه")["intent"], "defect_admit")

    def test_model_install_paths(self):
        from marketing_divar.nlu_model import (download_cache_dir, model_dir,
                                               program_dir, status)
        old = {k: os.environ.get(k) for k in
               ("DIVAR_APP_DIR", "DIVAR_NLU_DIR", "DIVAR_NLU_DOWNLOAD")}
        tmp = tempfile.mkdtemp()
        os.environ["DIVAR_APP_DIR"] = tmp
        os.environ.pop("DIVAR_NLU_DIR", None)
        os.environ["DIVAR_NLU_DOWNLOAD"] = os.path.join(tmp, "setup", "nlu-download")
        try:
            self.assertEqual(str(program_dir()), tmp)
            self.assertTrue(str(model_dir()).endswith("nlu-model") or
                            str(model_dir()).replace("\\", "/").endswith("nlu-model"))
            self.assertEqual(str(model_dir()), os.path.join(tmp, "nlu-model"))
            self.assertIn("nlu-download", str(download_cache_dir()).replace("\\", "/"))
            st = status()
            self.assertIn("install_dir", st)
            self.assertIn("download_dir", st)
            self.assertEqual(st["role"], "analyze_replies_listings_vehicles_images")
            self.assertFalse(os.path.isfile(os.path.join(ROOT, "qwen2.5-1.5b-instruct-q4_k_m.gguf")))
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_inbox_platform_column(self):
        from marketing_divar.db import connect, upsert_lead
        from marketing_divar.inbox import ingest_sms
        from marketing_divar.nlu import analyze_for_platform
        con = connect(os.path.join(tempfile.mkdtemp(), "i.db"))
        upsert_lead(con, {"token": "sheypoor:99", "title": "پراید", "url": "u",
                          "phone": "09121112233", "platform": "sheypoor",
                          "has_chat": 1}, "پراید", "tehran")
        con.execute("UPDATE leads SET phone='09121112233', sms_status='sent' "
                    "WHERE token='sheypoor:99'")
        con.commit()
        r = ingest_sms(con, "09121112233", "موجوده هنوز", use_llm=False)
        self.assertTrue(r.get("ok"))
        row = con.execute("SELECT platform FROM replies").fetchone()
        self.assertEqual(row["platform"], "sheypoor")
        a = analyze_for_platform("۲۵ میلیون نقد", "ring", use_llm=False)
        self.assertEqual(a["intent"], "price_quote")


class TestInstallerNluNeedles(unittest.TestCase):
    def test_setup_has_nlu_install(self):
        path = os.path.join(ROOT, "installer", "setup_app.py")
        body = open(path, encoding="utf-8").read()
        self.assertIn("install_nlu_model", body)
        self.assertIn("nlu-model", body)
        self.assertIn("nlu_bar", body)
        self.assertIn("DIVAR_NLU_DOWNLOAD", body)
        self.assertFalse(any("\u0600" <= ch <= "\u06ff" for ch in body))


if __name__ == "__main__":
    unittest.main()
