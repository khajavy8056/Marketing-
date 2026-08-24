# -*- coding: utf-8 -*-
"""دسته‌بندی دیوار + ساخت exe روی ویندوز کاربر."""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from marketing_divar.categories import normalize_slug, public_list, title_of
from marketing_divar.matching import consider_new_lead
from marketing_divar.db import connect, lead_exists
from marketing_divar import store


class TestDivarCategories(unittest.TestCase):
    def test_known_slugs(self):
        slugs = {c["slug"] for c in public_list()}
        for s in ("mobile-tablet", "light", "computers", "real-estate", "jobs"):
            self.assertIn(s, slugs)
        self.assertEqual(normalize_slug("mobile-tablet"), "mobile-tablet")
        self.assertEqual(normalize_slug("no-such"), "")
        self.assertIn("موبایل", title_of("mobile-tablet"))

    def test_store_category_and_match_all(self):
        db = os.path.join(tempfile.mkdtemp(), "c.db")
        self.assertTrue(store.keywords_add(db, "", None, "mobile-tablet"))
        rows = store.keywords_list(db)
        self.assertTrue(any(r.get("category") == "mobile-tablet" for r in rows))
        specs = store.keywords_active_specs(db)
        self.assertTrue(any(s.get("match_all") and s.get("category") == "mobile-tablet"
                            for s in specs))
        self.assertTrue(store.keywords_add(db, "آیفون", [1], "mobile-tablet"))
        specs2 = store.keywords_active_specs(db)
        iphone = next(s for s in specs2 if s["keyword"] == "آیفون")
        self.assertEqual(iphone["category"], "mobile-tablet")
        self.assertFalse(iphone["match_all"])

    def test_match_all_stores_unrelated_title(self):
        con = connect(os.path.join(tempfile.mkdtemp(), "m.db"))
        post = {"token": "cat1", "title": "فروش یخچال", "subtitle": "",
                "url": "u", "has_chat": 1}
        self.assertTrue(consider_new_lead(
            con, None, post, "موبایل و تبلت", "iran",
            fetch_details=False, match_all=True))
        self.assertTrue(lead_exists(con, "cat1"))

    def test_html_search_uses_category_path(self):
        from marketing_divar.client import DivarClient
        seen = []

        class T:
            name = "t"

            def request(self, method, url, **kw):
                seen.append(url)
                class R:
                    status_code = 200
                    text = '<a href="/v/foo/AbCde">x</a>'
                    def json(self):
                        return {}
                    def raise_for_status(self):
                        pass
                return R()

        cl = DivarClient(session_path=os.path.join(tempfile.mkdtemp(), "s.json"))
        cl._custom_transports = [T()]
        cl.limiter.wait = lambda *_a, **_k: None
        cl.search("", cities=[1], category="light")
        joined = " ".join(seen)
        self.assertTrue(any("/s/tehran/light" in u or "/light" in u for u in seen), joined)

    def test_build_exe_bat_exists(self):
        for name in ("ساخت-نصب-استاندارد.bat", os.path.join("scripts", "build_exe.bat")):
            path = os.path.join(ROOT, name)
            self.assertTrue(os.path.exists(path), name)
            body = open(path, encoding="utf-8-sig", errors="replace").read()
            self.assertTrue("pyinstaller" in body.lower(), name)
            self.assertIn("DivarLead", body)


if __name__ == "__main__":
    unittest.main()
