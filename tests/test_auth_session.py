# -*- coding: utf-8 -*-
"""ذخیره و تزریق کامل سشن دیوار (SuperTokens + token)."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from marketing_divar.auth_session import (  # noqa: E402
    absorb_response, cdp_cookie_params, cookies_for_browser,
    localstorage_script, merge_into_session_file)
from marketing_divar.client import DivarClient  # noqa: E402
from marketing_divar.session_view import PuzzleLive  # noqa: E402


class _Hdr(dict):
    def get_all(self, name):
        if name.lower() == "set-cookie":
            return list(self.get("Set-Cookie-list") or [])
        return []


class TestAbsorb(unittest.TestCase):
    def test_headers_become_site_cookies(self):
        class R:
            cookies = []
            headers = {
                "st-access-token": "SAT-HDR",
                "front-token": "FRONT",
                "st-refresh-token": "REF",
            }
        bag = absorb_response(R())
        names = {c["name"]: c["value"] for c in bag["cookies_full"]}
        self.assertEqual(names["sAccessToken"], "SAT-HDR")
        self.assertEqual(names["sFrontToken"], "FRONT")
        self.assertEqual(names["sRefreshToken"], "REF")
        self.assertEqual(bag["auth_headers"]["st-access-token"], "SAT-HDR")

    def test_set_cookie_and_httpx_name_iter(self):
        class Jar:
            def __iter__(self):
                return iter(["sFrontToken"])

            def __getitem__(self, k):
                return "SFT"

        class R:
            cookies = Jar()
            headers = _Hdr({"Set-Cookie-list": [
                "sAccessToken=SATCK; Domain=.divar.ir; Path=/; HttpOnly",
            ]})
        bag = absorb_response(R())
        names = {c["name"]: c["value"] for c in bag["cookies_full"]}
        self.assertEqual(names["sFrontToken"], "SFT")
        self.assertEqual(names["sAccessToken"], "SATCK")

    def test_requests_cookie_objects(self):
        class C:
            def __init__(self, n, v):
                self.name, self.value, self.domain, self.path = n, v, ".divar.ir", "/"

        class R:
            cookies = [C("did", "D1")]
            headers = {}
        bag = absorb_response(R())
        self.assertEqual(bag["cookies_full"][0]["name"], "did")
        self.assertEqual(bag["cookies_full"][0]["value"], "D1")


class TestPersistAndInject(unittest.TestCase):
    def test_merge_and_browser_cookies_have_api_domain(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "session.json")
        merge_into_session_file(p, "09120000000", "TOK", {
            "cookies_full": [{"name": "sFrontToken", "value": "F",
                              "domain": ".divar.ir", "path": "/"}],
            "auth_headers": {"st-access-token": "SAT"},
        })
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        self.assertEqual(data["token"], "TOK")
        self.assertIn("sFrontToken", data["cookies"])
        self.assertTrue(data["cookies_full"])
        cks = cookies_for_browser(p)
        self.assertTrue(any(c["name"] == "sAccessToken" and "api.divar.ir" in c["domain"]
                            for c in cks))
        params = cdp_cookie_params(cks[0])
        urls = {x["url"] for x in params}
        self.assertIn("https://divar.ir/", urls)
        self.assertIn("https://api.divar.ir/", urls)
        script = localstorage_script(p)
        self.assertIn("TOK", script)
        self.assertIn("localStorage.setItem", script)

    def test_confirm_otp_writes_supertokens(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "session.json")
        c = DivarClient(session_path=p)

        class Fake:
            name = "fake"

            def request(self, method, url, **kw):
                class R:
                    status_code = 200
                    text = '{"token":"JWT1"}'
                    cookies = []
                    headers = {
                        "st-access-token": "SAT1",
                        "front-token": "FRONT1",
                        "Set-Cookie": "sRefreshToken=REF1; Domain=.divar.ir; Path=/",
                    }

                    def json(self):
                        return {"token": "JWT1"}
                return R()

        c._custom_transports = [Fake()]
        tok = c.confirm_otp("09121111111", "123456")
        self.assertEqual(tok, "JWT1")
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        self.assertEqual(data["token"], "JWT1")
        self.assertEqual(data["cookies"].get("sAccessToken"), "SAT1")
        self.assertEqual(data["cookies"].get("sFrontToken"), "FRONT1")
        self.assertTrue(any(x.get("name") == "sRefreshToken" for x in data["cookies_full"]))

    def test_inject_cookies_and_script_before_navigate(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "session.json")
        Path(p).write_text(json.dumps({"token": "T", "cookies": {"sFrontToken": "F"}}),
                           encoding="utf-8")
        calls = []

        class FakeCdp:
            def call(self, method, params=None, timeout=10):
                calls.append(method)
                return {}

        live = PuzzleLive()
        live.cdp = FakeCdp()
        live.session_path = p
        live._inject_login_then_open(
            [{"name": "sAccessToken", "value": "X", "domain": ".divar.ir",
              "urls": ["https://divar.ir/", "https://api.divar.ir/"]}],
            "https://divar.ir/v/ad1")
        self.assertIn("Network.setCookie", calls)
        self.assertIn("Page.addScriptToEvaluateOnNewDocument", calls)
        self.assertIn("Page.navigate", calls)
        self.assertLess(calls.index("Network.setCookie"), calls.index("Page.navigate"))
        self.assertLess(calls.index("Page.addScriptToEvaluateOnNewDocument"),
                        calls.index("Page.navigate"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
