# -*- coding: utf-8 -*-
"""v2.0: شهرهای دیوار، زیردسته، بازه قیمت، هشدار ویژه."""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from marketing_divar.categories import public_list, title_of
from marketing_divar.cities import public_list as cities_list, slug_of, title_of_city
from marketing_divar.client import city_slug
from marketing_divar.db import connect
from marketing_divar.matching import consider_new_lead
from marketing_divar.pricing import in_range, million_to_toman, parse_toman
from marketing_divar.telegram_bot import vip_alert_text
from marketing_divar import store


class TestCities(unittest.TestCase):
    def test_divar_slugs(self):
        slugs = {c["slug"] for c in cities_list()}
        for s in ("tehran", "mashhad", "shiraz", "kish", "sari"):
            self.assertIn(s, slugs)
        self.assertEqual(slug_of(1), "tehran")
        self.assertEqual(slug_of(15), "yazd")
        self.assertEqual(slug_of(0), "iran")
        self.assertEqual(title_of_city(1), "تهران")
        self.assertEqual(city_slug([15]), "yazd")
        self.assertEqual(city_slug([99]), "iran")


class TestCategoryTree(unittest.TestCase):
    def test_parents_and_subs(self):
        cats = public_list()
        by = {c["slug"]: c for c in cats}
        self.assertEqual(by["mobile-phones"]["parent"], "mobile-tablet")
        self.assertEqual(by["light"]["parent"], "vehicles")
        self.assertIn("└", by["mobile-phones"]["label"])
        self.assertIn("موبایل", title_of("mobile-phones"))


class TestPricing(unittest.TestCase):
    def test_parse_toman(self):
        self.assertEqual(parse_toman("۴۵ میلیون تومان"), 45_000_000)
        self.assertEqual(parse_toman("12,000,000 تومان"), 12_000_000)
        self.assertEqual(million_to_toman(20), 20_000_000)
        self.assertTrue(in_range(30_000_000, 20_000_000, 80_000_000))
        self.assertFalse(in_range(10_000_000, 20_000_000, 80_000_000))
        self.assertFalse(in_range(None, 20_000_000, 0))
        self.assertTrue(in_range(None, 0, 0))

    def test_price_filter_on_lead(self):
        con = connect(os.path.join(tempfile.mkdtemp(), "p.db"))
        cheap = {"token": "c1", "title": "آیفون ۱۱", "subtitle": "۸ میلیون تومان",
                 "url": "u", "has_chat": 1, "price": 8_000_000}
        mid = {"token": "c2", "title": "آیفون ۱۳", "subtitle": "۴۵ میلیون تومان",
               "url": "u", "has_chat": 1, "price": 45_000_000}
        self.assertFalse(consider_new_lead(
            con, None, cheap, "آیفون", "iran", fetch_details=False,
            price_min=20_000_000, price_max=80_000_000))
        self.assertTrue(consider_new_lead(
            con, None, mid, "آیفون", "iran", fetch_details=False,
            price_min=20_000_000, price_max=80_000_000, vip=True))
        row = con.execute("SELECT vip, price FROM leads WHERE token='c2'").fetchone()
        self.assertTrue(row["vip"])
        self.assertEqual(row["price"], 45_000_000)


class TestStorePriceVip(unittest.TestCase):
    def test_keyword_price_and_vip(self):
        db = os.path.join(tempfile.mkdtemp(), "k.db")
        self.assertTrue(store.keywords_add(
            db, "آیفون", [1], "mobile-phones",
            price_min=20_000_000, price_max=80_000_000, vip=True))
        row = store.keywords_list(db)[0]
        self.assertEqual(row["price_min"], 20_000_000)
        self.assertTrue(row["vip"])
        self.assertEqual(row["city_title"], "تهران")
        spec = store.keywords_active_specs(db)[0]
        self.assertEqual(spec["price_max"], 80_000_000)
        self.assertTrue(spec["vip"])


class TestVipText(unittest.TestCase):
    def test_vip_alert_mentions_star(self):
        t = vip_alert_text("آیفون ۱۳", city="تهران", category="موبایل",
                           price=45_000_000, url="https://divar.ir/v/x",
                           phone="09120000000")
        self.assertIn("ویژه", t)
        self.assertIn("تهران", t)
        self.assertIn("09120000000", t)
        self.assertIn("میلیون", t)


class TestHtmlPriceEnrich(unittest.TestCase):
    def test_json_price_near_token(self):
        from marketing_divar.client import DivarClient
        html = (
            '<a href="/v/iphone-13/AbCde1">x</a>'
            '{"token":"AbCde1","offers":{"price":"450000000"}}'
        )
        posts = DivarClient._parse_search_html(html)
        self.assertTrue(posts)
        self.assertEqual(posts[0]["token"], "AbCde1")
        self.assertEqual(posts[0].get("price"), 45_000_000)


if __name__ == "__main__":
    unittest.main()
