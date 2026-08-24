# -*- coding: utf-8 -*-
"""کوکی سشن → پنجرهٔ دیوار همان اکانت (بدون iframe)."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from marketing_divar.client import parse_block_body  # noqa: E402
from marketing_divar.session_view import (  # noqa: E402
    cookies_from_session, find_browser, launch_account_browser)


class TestCookiesFromSession(unittest.TestCase):
    def test_token_and_named_cookies(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "session.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"token": "TOK123",
                       "cookies": {"sAccessToken": "SAT", "sFrontToken": "SFT"}}, f)
        cks = cookies_from_session(p)
        by = {c["name"]: c["value"] for c in cks}
        self.assertEqual(by["sAccessToken"], "SAT")
        self.assertEqual(by["sFrontToken"], "SFT")
        self.assertEqual(by["token"], "TOK123")
        self.assertTrue(all(c["domain"] == ".divar.ir" for c in cks))

    def test_token_only_sets_access_cookie(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "session.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"token": "ONLY"}, f)
        by = {c["name"]: c["value"] for c in cookies_from_session(p)}
        self.assertEqual(by["token"], "ONLY")
        self.assertEqual(by["sAccessToken"], "ONLY")

    def test_missing_file(self):
        self.assertEqual(cookies_from_session("/no/such/session.json"), [])


class TestParseBlockBody(unittest.TestCase):
    def test_image_url(self):
        r = parse_block_body('oops https://cdn.divar.ir/x/puz.png done')
        self.assertEqual(r["image_url"], "https://cdn.divar.ir/x/puz.png")
        self.assertTrue(r["has_widget"])

    def test_empty(self):
        r = parse_block_body("just a 403")
        self.assertFalse(r["image_url"])
        self.assertFalse(r["has_widget"])


class TestLaunchGuard(unittest.TestCase):
    def test_missing_session(self):
        ok, msg = launch_account_browser("/tmp/no-session-here.json", "x")
        self.assertFalse(ok)
        self.assertIn("سشن", msg)

    def test_popen_when_browser_present(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "session.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"token": "T"}, f)
        with mock.patch("marketing_divar.session_view.find_browser",
                        return_value="/usr/bin/chromium"), \
             mock.patch("marketing_divar.session_view.subprocess.Popen") as pop:
            ok, msg = launch_account_browser(p, "ac1")
        self.assertTrue(ok)
        self.assertIn("ac1", msg)
        self.assertTrue(pop.called)


class TestFindBrowserEnv(unittest.TestCase):
    def test_divar_browser_file(self):
        d = tempfile.mkdtemp()
        fake = os.path.join(d, "msedge")
        open(fake, "w").close()
        old = os.environ.get("DIVAR_BROWSER")
        os.environ["DIVAR_BROWSER"] = fake
        try:
            self.assertEqual(find_browser(), fake)
        finally:
            if old is None:
                os.environ.pop("DIVAR_BROWSER", None)
            else:
                os.environ["DIVAR_BROWSER"] = old


if __name__ == "__main__":
    unittest.main(verbosity=2)
