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
    PuzzleLive, _http_get_local, _wait_cdp, cookies_from_session,
    find_browser, launch_account_browser)


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


class TestCdpLocalHttp(unittest.TestCase):
    def test_wait_cdp_ignores_http_proxy(self):
        """باگ زنده: urlopen با پروکسی سیستم به 127.0.0.1 timeout می‌شد."""
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({
                    "webSocketDebuggerUrl": "ws://127.0.0.1:9/devtools/browser/x",
                }).encode()
                if self.path.startswith("/json/list"):
                    body = json.dumps([{
                        "type": "page",
                        "webSocketDebuggerUrl": "ws://127.0.0.1:9/devtools/page/x",
                    }]).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt, *args):
                return

        srv = HTTPServer(("127.0.0.1", 0), H)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        old = {k: os.environ.get(k) for k in (
            "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")}
        try:
            os.environ["HTTP_PROXY"] = "http://127.0.0.1:1"
            os.environ["http_proxy"] = "http://127.0.0.1:1"
            os.environ["HTTPS_PROXY"] = "http://127.0.0.1:1"
            body = _http_get_local(port, "/json/version")
            self.assertIn("webSocketDebuggerUrl", body)
            ws = _wait_cdp(port, tries=8)
            self.assertIn("/devtools/page/", ws)
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            srv.shutdown()

    def test_start_uses_isolated_profile(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "session.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"token": "T"}, f)
        live = PuzzleLive()
        with mock.patch("marketing_divar.session_view.find_browsers",
                        return_value=["/usr/bin/no-such-browser"]), \
             mock.patch("marketing_divar.session_view.subprocess.Popen",
                        side_effect=OSError("nope")):
            with self.assertRaises(RuntimeError) as ctx:
                live.start(p)
        self.assertIn("پازل", str(ctx.exception))


class TestPuzzleLiveGuard(unittest.TestCase):
    def test_start_needs_session_and_browser(self):
        live = PuzzleLive()
        with self.assertRaises(RuntimeError):
            live.start("/tmp/no-session-here.json")
        d = tempfile.mkdtemp()
        p = os.path.join(d, "session.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"token": "T"}, f)
        with mock.patch("marketing_divar.session_view.find_browser", return_value=None):
            with self.assertRaises(RuntimeError):
                live.start(p)


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
