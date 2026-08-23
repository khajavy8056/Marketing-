# -*- coding: utf-8 -*-
"""تست روی پاسخ‌های واقعی دیوار که در ۱۴۰۵/۰۶/۰۱ از سایت زنده گرفته شد.

اتصال خام این محیط به api.divar.ir در لایه TLS قطع است؛ این تست‌ها همان
بدنه‌های واقعی را به پارسِر می‌دهند تا مطمئن شویم اگر شبکه کاربر سالم باشد،
کد فعلی همان داده زنده را می‌فهمد.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from marketing_divar.client import (DivarClient, extract_contact_uuid,  # noqa: E402
                                    is_blocking_view)
from marketing_divar.matching import extract_description, keyword_hits  # noqa: E402

# پاسخ واقعی GET /v8/web-search/iran?q=آپارتمان — ۱۴۰۵/۰۶/۰۱
LIVE_BLOCKING = {
    "widget_list": [{"widget_type": "BLOCKING_VIEW",
                     "data": {"title": "نیاز به بروزرسانی"}}],
    "last_post_date": -1,
}

# تکه‌ای از HTML/مارک‌داون واقعی صفحه /s/tehran و /s/iran?q=تدریس
LIVE_HTML = """
<a href="/v/%D8%A7%DB%8C%D9%81%D9%88%D9%86-13-%D9%BE%D8%B1%D9%88%D9%85%DA%A9%D8%B3/gaLuC0dU">ایفون</a>
](https://divar.ir/v/%D9%81%D8%B1%D9%88%D8%B4-%D8%A2%D9%BE%D8%A7%D8%B1%D8%AA%D9%85%D8%A7%D9%86-%DB%B1%DB%B0%DB%B6-%D9%85%D8%AA%D8%B1%DB%8C-%D9%86%D8%A7%D9%85%D8%AC%D9%88/gaK-LspM)
](https://divar.ir/v/%D8%AA%D8%AF%D8%B1%DB%8C%D8%B3-%D8%AE%D8%B5%D9%88%D8%B5%DB%8C-%D9%85%D9%88%D8%B3%DB%8C%D9%82%DB%8C/ga84Em-u)
<a href="/v/rules/about">not an ad</a>
"""

# ساختار واقعی contact در posts-v2/web/gaLuC0dU
LIVE_POST = {
    "sections": [{"section_name": "DESCRIPTION", "widgets": [
        {"widget_type": "DESCRIPTION_ROW",
         "data": {"text": "بدون خط و خش 512 گیگ سلامت باطری 86"}}]}],
    "seo": {"title": "ایفون 13 پرومکس در تهران",
            "description": "آگهی ایفون 13 پرومکس در دیوار تهران",
            "post_seo_schema": {"description": "بدون خط و خش 512 گیگ سلامت باطری 86",
                                "name": "ایفون 13 پرومکس"}},
    "contact": {
        "chat_enabled": True,
        "secure_call_enabled": True,
        "action_log": {"server_side_info": {"info": {
            "post_token": "gaLuC0dU",
            "contact_uuid": "e8313322-2843-4355-bdd9-36fcbc3ba06e"}}}},
}


class TestLiveCaptured(unittest.TestCase):
    def test_blocking_view_detected(self):
        self.assertTrue(is_blocking_view(LIVE_BLOCKING))
        self.assertEqual(DivarClient._extract_post_list(LIVE_BLOCKING), [])

    def test_html_extracts_live_tokens(self):
        posts = DivarClient._parse_search_html(LIVE_HTML)
        toks = {p["token"] for p in posts}
        self.assertIn("gaLuC0dU", toks)
        self.assertIn("gaK-LspM", toks)
        self.assertIn("ga84Em-u", toks)
        self.assertNotIn("about", toks)
        iphone = next(p for p in posts if p["token"] == "gaLuC0dU")
        self.assertIn("ایفون", iphone["title"])

    def test_contact_uuid_nested_live_shape(self):
        self.assertEqual(extract_contact_uuid(LIVE_POST),
                         "e8313322-2843-4355-bdd9-36fcbc3ba06e")
        self.assertEqual(extract_contact_uuid({"contact": {"contact_uuid": "old-style-uuid"}}),
                         "old-style-uuid")

    def test_description_and_keyword_from_live_post(self):
        desc = extract_description(LIVE_POST)
        self.assertIn("باطری", desc)
        self.assertTrue(keyword_hits(desc + " ایفون 13 پرومکس", "ایفون"))

    def test_live_mobile_html_tokens(self):
        html = """
        ](https://divar.ir/v/%DA%AF%D9%88%D8%B4%DB%8C-poco-x7-pro/gaLSzmq_)
        ](https://divar.ir/v/s-21-22-23-24-25-ultra/QacnRuCM)
        <script>challenge; captcha loader</script>
        """
        toks = {p["token"] for p in DivarClient._parse_search_html(html)}
        self.assertIn("gaLSzmq_", toks)
        self.assertIn("QacnRuCM", toks)
        from marketing_divar.client import looks_like_captcha
        self.assertFalse(looks_like_captcha(html + ("x" * 3000)))


if __name__ == "__main__":
    unittest.main()
