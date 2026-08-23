# -*- coding: utf-8 -*-
"""تست‌های v1.5.0 — چند-مسیری اتصال، جستجوی HTML، بررسی اتصال کامل.

خواستهٔ کاربر: «چندین روش/کتابخانهٔ مختلف — به‌ترتیب تا یکی کار کند» +
«بررسی اتصال در تنظیمات: آگهی بکش، متنش را بخوان، با اکانت شماره بگیر، چت».
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

import requests  # noqa: E402

from marketing_divar.client import DivarClient  # noqa: E402


class _Resp:
    def __init__(self, code, payload=None, text=None):
        self.status_code = code
        self._p = payload or {}
        self.text = text if text is not None else str(self._p)

    def json(self):
        return self._p


class _T:
    """مسیر ساختگی برای تست زنجیرهٔ ترابری."""

    def __init__(self, name, fail=None, resp=None):
        self.name, self.fail, self.resp = name, fail, resp

    def request(self, method, url, **kw):
        if self.fail:
            raise self.fail
        return self.resp


class TestTransportChain(unittest.TestCase):
    def _client(self):
        c = DivarClient.__new__(DivarClient)
        c.http = requests.Session()
        c.base = "http://mock"
        c.token = None
        c._winner = None
        c._custom_transports = None
        c.limiter = __import__("marketing_divar.rate", fromlist=["R"]).RateLimiter(
            search_delay=0, phone_delay=0, page_delay=0, jitter=0)
        return c

    def test_falls_through_to_working_transport(self):
        c = self._client()
        c._custom_transports = [
            _T("bad1", fail=requests.exceptions.ProxyError("vpn down")),
            _T("bad2", fail=ConnectionError("refused")),
            _T("good", resp=_Resp(200, {"ok": 1})),
        ]
        r = c._fetch("GET", "http://mock/x")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(c._winner, "good", "مسیر برنده باید sticky شود")

    def test_winner_moves_first_on_next_call(self):
        c = self._client()
        t_bad = _T("bad", fail=requests.exceptions.ProxyError("x"))
        order = []
        good = _T("good", resp=_Resp(200))

        class _OrderedGood(_T):
            def request(self, method, url, **kw):
                order.append(self.name)
                return super().request(method, url, **kw)

        class _OrderedBad(_T):
            def request(self, method, url, **kw):
                order.append(self.name)
                return super().request(method, url, **kw)

        chain = [_OrderedBad("bad", fail=t_bad.fail), _OrderedGood("good", resp=good.resp)]
        c._custom_transports = chain
        c._fetch("GET", "http://mock/x")
        c._fetch("GET", "http://mock/x")
        self.assertEqual(order, ["bad", "good", "good"],
                         "بعد از برد، مسیر برنده باید اول بیاید")

    def test_all_fail_raises_last(self):
        c = self._client()
        c._custom_transports = [
            _T("a", fail=requests.exceptions.ProxyError("p")),
            _T("b", fail=ConnectionError("c"))]
        with self.assertRaises(ConnectionError):
            c._fetch("GET", "http://mock/x")

    def test_html_parser(self):
        html = ('<a href="/v/%D8%A2%D9%BE%D8%A7%D8%B1%D8%AA%D9%85%D8%A7%D9%86-80/QY8b9X">x</a>'
                '<a href="/v/moblian/Gk21zZ">y</a>'
                '<a href="/v/rules/about">z</a>'
                '<a href="/v/%D8%A2%D9%BE%D8%A7%D8%B1%D8%AA%D9%85%D8%A7%D9%86-80/QY8b9X">dup</a>')
        posts = DivarClient._parse_search_html(html)
        self.assertEqual(len(posts), 2, "توکن تکراری و مسیر غیرآگهی حذف شود")
        self.assertEqual(posts[0]["token"], "QY8b9X")
        self.assertIn("آپارتمان", posts[0]["title"])

    def test_httpx_merges_authorization_header(self):
        """اگر مسیر httpx برنده شود، هدر Authorization نباید حذف شود."""
        import marketing_divar.client as clmod
        seen = {}

        class _FakeHttpxClient:
            def __init__(self, **kw): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def post(self, url, headers=None, json=None, timeout=None):
                seen["headers"] = dict(headers or {})
                return _Resp(200, {"ok": 1})
            def get(self, url, headers=None, params=None, timeout=None):
                seen["headers"] = dict(headers or {})
                return _Resp(200, {"ok": 1})

        c = self._client()
        tr = clmod._HttpxDirectTransport(c)
        real_httpx = __import__("httpx")
        orig = real_httpx.Client
        real_httpx.Client = _FakeHttpxClient
        try:
            r = tr.request("POST", "http://mock/x",
                           headers={"Authorization": "Bearer tok-test"},
                           json={"a": 1})
        finally:
            real_httpx.Client = orig
        self.assertEqual(r.status_code, 200)
        self.assertEqual(seen["headers"].get("Authorization"), "Bearer tok-test")

    def test_search_falls_back_to_html(self):
        c = self._client()
        good_html = _Resp(200, text='<a href="/v/apartman-80/QY8b9X">x</a>')

        class _AlwaysApiDown:
            name = "requests"

            def request(self, method, url, **kw):
                if "web-search" in url:
                    raise requests.exceptions.ConnectionError("api dead")
                return good_html

        c._custom_transports = [_AlwaysApiDown()]
        posts = c.search("آپارتمان")
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["token"], "QY8b9X")


if __name__ == "__main__":
    unittest.main()
