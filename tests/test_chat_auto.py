# -*- coding: utf-8 -*-
"""ارسال خودکار چت دیوار — ماژول chat.py + کلاینت (بدون نیاز به IP ایران)."""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from marketing_divar.chat import (  # noqa: E402
    chat_ready, compose_chat, maybe_send_chat_for_lead, send_divar_chat)
from marketing_divar.client import DivarClient  # noqa: E402


class FakeClient:
    """کلاینت جعلی برای تزریق send_fn — بدون شبکه."""
    def __init__(self, result=None, exc=None):
        self.result = result if result is not None else {"ok": True, "status": "sent"}
        self.exc = exc

    def send_chat(self, token, text):
        if self.exc:
            raise self.exc
        return self.result


class TestChatAuto(unittest.TestCase):
    def test_ready_off_by_default(self):
        ok, why = chat_ready({})
        self.assertFalse(ok)
        self.assertIn("خاموش", why)
        ok2, _ = chat_ready({"chat_auto_on_new": True})
        self.assertTrue(ok2)

    def test_compose_fills_template(self):
        text = compose_chat("سلام {title}", {"title": "ویلا", "url": "u"})
        self.assertIn("ویلا", text)

    def test_send_success(self):
        seen = {}

        def fn(client, token, text):
            seen["token"] = token
            seen["text"] = text
            return {"ok": True, "status": "sent", "message": "sent"}

        r = send_divar_chat(FakeClient(), "tok1", "سلام", send_fn=fn)
        self.assertTrue(r["ok"])
        self.assertEqual(r["status"], "sent")
        self.assertEqual(seen["token"], "tok1")

    def test_send_requires_operator_on_http_fail(self):
        r = send_divar_chat(FakeClient(result={"ok": False, "status": "requires_operator",
                                               "message": "HTTP 404"}),
                            "tok1", "سلام")
        self.assertFalse(r["ok"])
        self.assertEqual(r["status"], "requires_operator")

    def test_send_exception_falls_back_to_operator(self):
        r = send_divar_chat(FakeClient(exc=RuntimeError("boom")), "tok1", "سلام")
        self.assertFalse(r["ok"])
        self.assertEqual(r["status"], "requires_operator")

    def test_maybe_send_off_returns_none(self):
        self.assertIsNone(maybe_send_chat_for_lead(
            {}, {"token": "t", "title": "x"}, "سلام {title}", FakeClient()))

    def test_maybe_send_on_sends(self):
        r = maybe_send_chat_for_lead(
            {"chat_auto_on_new": True},
            {"token": "t", "title": "ویلا"}, "سلام {title}", FakeClient())
        self.assertTrue(r and r["ok"])

    def test_maybe_send_missing_token(self):
        r = maybe_send_chat_for_lead(
            {"chat_auto_on_new": True}, {"title": "x"}, "سلام", FakeClient())
        self.assertFalse(r["ok"])
        self.assertEqual(r["status"], "error")


class TestClientSendChat(unittest.TestCase):
    """ارسال واقعی کلاینت مقابل شبیه‌ساز (mock_divar)."""

    def test_send_chat_against_mock(self):
        from mock_divar import MockDivar, start_mock
        MockDivar.reset()
        srv = start_mock()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "session.json"), "w", encoding="utf-8") as f:
            f.write('{"phone": "0912chat", "token": "tok-chat"}')
        cl = DivarClient(session_path=os.path.join(d, "session.json"),
                         base_url=base)
        r = cl.send_chat("c1", "سلام، آگهی شما را دیدم")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["status"], "sent")
        with MockDivar.lock:
            sends = list(MockDivar.chat_sends)
        self.assertEqual(len(sends), 1)
        self.assertEqual(sends[0][0], "c1")
        self.assertEqual(sends[0][1], "chat")
        self.assertIn("سلام", sends[0][2])
        srv.shutdown()

    def test_send_chat_unauth_requires_operator(self):
        from mock_divar import MockDivar, start_mock
        MockDivar.reset()
        srv = start_mock()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        cl = DivarClient(session_path=os.path.join(tempfile.mkdtemp(), "s.json"),
                         base_url=base)
        cl.token = None
        from marketing_divar.client import DivarAuthError
        with self.assertRaises(DivarAuthError):
            cl.send_chat("c1", "سلام")
        srv.shutdown()


if __name__ == "__main__":
    unittest.main(verbosity=2)
