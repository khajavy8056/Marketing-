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
    absorb_login_json, absorb_response, cdp_cookie_params, cookies_for_browser,
    localstorage_script, merge_into_session_file)
from marketing_divar.client import DivarClient  # noqa: E402
from marketing_divar.session_view import PuzzleLive  # noqa: E402


class _Hdr(dict):
    def get_all(self, name):
        if name.lower() == "set-cookie":
            return list(self.get("Set-Cookie-list") or [])
        return []


class TestAbsorb(unittest.TestCase):
    def test_login_json_session_tokens(self):
        bag = absorb_login_json({
            "status": "OK",
            "frontToken": "FT",
            "session": {"accessToken": {"token": "AT"},
                        "refreshToken": {"token": "RT"}},
        })
        names = {c["name"]: c["value"] for c in bag["cookies_full"]}
        self.assertEqual(names["sAccessToken"], "AT")
        self.assertEqual(names["sRefreshToken"], "RT")
        self.assertEqual(names["sFrontToken"], "FT")

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

    def test_request_otp_persists_device_and_consume_uses_it(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "session.json")
        c = DivarClient(session_path=p)
        seen = []

        class Fake:
            name = "fake"

            def request(self, method, url, **kw):
                seen.append({"url": url, "json": kw.get("json") or {},
                             "headers": kw.get("headers") or {}})
                class R:
                    status_code = 200
                    text = "{}"
                    cookies = []
                    headers = {}

                    def json(self):
                        if url.endswith("/code") and not url.endswith("/consume"):
                            return {"status": "OK", "deviceId": "DEV9",
                                    "preAuthSessionId": "PRE9"}
                        return {"token": "JWT-ST"}
                return R()

        c._custom_transports = [Fake()]
        self.assertTrue(c.request_otp("09123334444"))
        pending = json.loads((Path(d) / "otp_pending.json").read_text(encoding="utf-8"))
        self.assertEqual(pending["deviceId"], "DEV9")
        self.assertEqual(pending["preAuthSessionId"], "PRE9")
        tok = c.confirm_otp("09123334444", "654321")
        self.assertEqual(tok, "JWT-ST")
        consume = next(x for x in seen if str(x["url"]).endswith("/consume"))
        self.assertEqual(consume["json"].get("userInputCode"), "654321")
        self.assertEqual(consume["json"].get("deviceId"), "DEV9")
        self.assertEqual(consume["json"].get("preAuthSessionId"), "PRE9")
        self.assertEqual(consume["headers"].get("rid"), "passwordless")
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        self.assertTrue(data["cookies"].get("sFrontToken"))

    def test_consume_json_session_becomes_site_cookies(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "session.json")
        c = DivarClient(session_path=p)

        class Fake:
            name = "fake"

            def request(self, method, url, **kw):
                class R:
                    status_code = 200
                    text = "{}"
                    cookies = []
                    headers = {}

                    def json(self):
                        if url.endswith("/consume"):
                            return {"status": "OK", "session": {
                                "accessToken": {"token": "ST-ACCESS"},
                                "refreshToken": {"token": "ST-REFRESH"},
                            }, "frontToken": "ST-FRONT"}
                        return {"token": "V5-API"}
                return R()

        c._custom_transports = [Fake()]
        tok = c.confirm_otp("09120002222", "222222")
        self.assertEqual(tok, "V5-API")
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        self.assertEqual(data["token"], "V5-API")
        self.assertEqual(data["cookies"].get("sAccessToken"), "ST-ACCESS")
        self.assertEqual(data["cookies"].get("sRefreshToken"), "ST-REFRESH")
        self.assertEqual(data["cookies"].get("sFrontToken"), "ST-FRONT")
        script = localstorage_script(p)
        self.assertIn("V5-API", script)
        self.assertIn("ST-FRONT", script)

    def test_consume_incorrect_status_falls_to_v5(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "session.json")
        c = DivarClient(session_path=p)

        class Fake:
            name = "fake"

            def request(self, method, url, **kw):
                class R:
                    cookies = []
                    headers = {}

                    def __init__(self):
                        self.status_code = 200
                        if url.endswith("/consume"):
                            self.text = '{"status":"INCORRECT_USER_INPUT_CODE_ERROR"}'
                        else:
                            self.text = '{"token":"V5-OK"}'

                    def json(self):
                        if url.endswith("/consume"):
                            return {"status": "INCORRECT_USER_INPUT_CODE_ERROR"}
                        return {"token": "V5-OK"}
                return R()

        c._custom_transports = [Fake()]
        self.assertEqual(c.confirm_otp("09120003333", "333333"), "V5-OK")

    def test_v5_token_promoted_to_site_session(self):
        from marketing_divar.auth_session import session_is_complete
        d = tempfile.mkdtemp()
        p = os.path.join(d, "session.json")
        c = DivarClient(session_path=p)

        class Fake:
            name = "fake"

            def request(self, method, url, **kw):
                class R:
                    cookies = []
                    headers = {}

                    def __init__(self):
                        if url.endswith("/consume"):
                            self.status_code = 400
                            self.text = '{"error":"bad body"}'
                        else:
                            self.status_code = 200
                            self.text = '{"token":"eyJhbGciOiJub25lIn0.eyJzdWIiOiJ1MSIsImV4cCI6OTk5OTk5OTk5OX0.x"}'

                    def json(self):
                        if self.status_code != 200:
                            return {"error": "bad"}
                        return {"token": "eyJhbGciOiJub25lIn0.eyJzdWIiOiJ1MSIsImV4cCI6OTk5OTk5OTk5OX0.x"}
                return R()

        c._custom_transports = [Fake()]
        tok = c.confirm_otp("09120001111", "111111")
        self.assertTrue(tok.startswith("eyJ"))
        self.assertTrue(session_is_complete(p))
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        self.assertTrue(data["cookies"].get("sFrontToken"))
        self.assertEqual(data["cookies"].get("sAccessToken"), tok)

    def test_incomplete_token_only_hidden(self):
        from marketing_divar.accounts import AccountManager
        from marketing_divar.auth_session import session_is_complete
        from marketing_divar.config import DEFAULTS
        d = tempfile.mkdtemp()
        old = Path(d) / "old" / "session.json"
        old.parent.mkdir(parents=True)
        old.write_text(json.dumps({"token": "JWT-ONLY"}), encoding="utf-8")
        good = Path(d) / "good" / "session.json"
        good.parent.mkdir(parents=True)
        good.write_text(json.dumps({
            "token": "JWT2", "cookies": {"sFrontToken": "FRONT"}}), encoding="utf-8")
        self.assertFalse(session_is_complete(str(old)))
        self.assertTrue(session_is_complete(str(good)))
        m = AccountManager(DEFAULTS, d)
        db = os.path.join(d, "x.db")
        from marketing_divar.db import connect
        connect(db).close()
        names = [a["name"] for a in m.snapshot(db, complete_only=True)]
        self.assertEqual(names, ["good"])
        self.assertNotIn("old", names)

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

    def test_urlencoded_set_cookie_decoded(self):
        class R:
            cookies = []
            headers = _Hdr({"Set-Cookie-list": [
                "sAccessToken=eyJ.abc%2Bdef%3D; Domain=.divar.ir; Path=/; HttpOnly",
            ]})
        bag = absorb_response(R())
        names = {c["name"]: c["value"] for c in bag["cookies_full"]}
        self.assertEqual(names["sAccessToken"], "eyJ.abc+def=")

    def test_browser_cookies_include_header_mode_aliases(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "session.json")
        merge_into_session_file(p, "09120000000", "TOK", {
            "cookies_full": [
                {"name": "sFrontToken", "value": "F",
                 "domain": ".divar.ir", "path": "/"},
                {"name": "sAccessToken", "value": "SAT",
                 "domain": ".divar.ir", "path": "/"},
                {"name": "sRefreshToken", "value": "REF",
                 "domain": ".divar.ir", "path": "/"},
            ],
            "auth_headers": {},
        })
        names = {c["name"] for c in cookies_for_browser(p)}
        self.assertIn("st-access-token", names)
        self.assertIn("st-refresh-token", names)
        self.assertIn("front-token", names)
        script = localstorage_script(p)
        self.assertIn("st-access-token", script)
        self.assertIn("st-refresh-token", script)

    def test_consume_fallback_after_deviceid_400(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "session.json")
        c = DivarClient(session_path=p)
        seen = []

        class Fake:
            name = "fake"

            def request(self, method, url, **kw):
                body = kw.get("json") or {}
                seen.append(body)
                class R:
                    cookies = []
                    headers = {}

                    def __init__(self):
                        if url.endswith("/consume") and body.get("deviceId"):
                            self.status_code = 400
                            self.text = '{"error":"bad"}'
                        elif url.endswith("/consume"):
                            self.status_code = 200
                            self.text = '{"status":"OK"}'
                            self.headers = {
                                "st-access-token": "SAT-FB",
                                "front-token": "FRONT-FB",
                                "st-refresh-token": "REF-FB",
                            }
                        else:
                            self.status_code = 200
                            self.text = '{"token":"V5-FB"}'

                    def json(self):
                        if self.status_code != 200:
                            return {"error": "bad"}
                        if url.endswith("/consume"):
                            return {"status": "OK"}
                        return {"token": "V5-FB"}
                return R()

        c._custom_transports = [Fake()]
        c._save_otp_pending("09124445555", {
            "deviceId": "DEV-BAD", "preAuthSessionId": "PRE-BAD"})
        tok = c.confirm_otp("09124445555", "444444")
        self.assertEqual(tok, "V5-FB")
        self.assertTrue(any(x.get("deviceId") == "DEV-BAD" for x in seen))
        self.assertTrue(any(x.get("phoneNumber") == "09124445555" for x in seen))
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        self.assertEqual(data["cookies"].get("sAccessToken"), "SAT-FB")
        self.assertEqual(data["cookies"].get("sFrontToken"), "FRONT-FB")


if __name__ == "__main__":
    unittest.main(verbosity=2)
