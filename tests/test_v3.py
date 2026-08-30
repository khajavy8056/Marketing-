# -*- coding: utf-8 -*-
"""پذیرش نسخه ۳: چت متغیر، تطبیق دقیق thread، حذف بدون کرش، NLU، شکارچی، سه پلتفرم."""

import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


class TestChatVariables(unittest.TestCase):
    def test_compose_includes_title_and_differs(self):
        from marketing_divar.chat import compose_chat, chat_ready
        tpl = "{greeting}\nآگهی «{title}» را دیدم.\n{closing}"
        with mock.patch("marketing_divar.messaging.random.choice",
                        side_effect=lambda seq: seq[0]):
            a = compose_chat(tpl, {"title": "پراید سفید ۸۴"})
            b = compose_chat(tpl, {"title": "تیبا دوگانه سوز"})
        self.assertIn("پراید سفید ۸۴", a)
        self.assertIn("تیبا دوگانه سوز", b)
        self.assertNotEqual(a, b)
        ok, why = chat_ready({"chat_auto_on_new": True, "chat_template": "سلام بدون متغیر"})
        self.assertFalse(ok)
        self.assertIn("{title}", why)

    def test_unknown_template_key_swallowed(self):
        from marketing_divar.messaging import build_message
        with mock.patch("marketing_divar.messaging.random.choice",
                        side_effect=lambda seq: seq[0]):
            t = build_message("سلام {title} {unknown_key}", {"title": "آیفون"})
        self.assertIn("آیفون", t)
        self.assertNotIn("{unknown_key}", t)

    def test_send_removed_does_not_raise(self):
        from marketing_divar.chat import send_divar_chat

        def gone(client, token, text):
            return {"ok": False, "status": "removed", "message": "آگهی حذف شده"}

        r = send_divar_chat(None, "tok", "سلام", send_fn=gone)
        self.assertFalse(r["ok"])
        self.assertEqual(r["status"], "removed")

        def boom(client, token, text):
            raise RuntimeError("target closed")

        r = send_divar_chat(None, "tok", "سلام", send_fn=boom)
        self.assertEqual(r["status"], "requires_operator")


class TestThreadBinding(unittest.TestCase):
    def test_match_exact_ad_not_other(self):
        from marketing_divar.chat_browser import match_thread_to_lead, listing_gone
        lead_a = {"token": "AAAA1111", "native_id": "AAAA1111", "title": "ویلای شمال رامسر",
                  "chat_thread_id": "th-a"}
        lead_b = {"token": "BBBB2222", "native_id": "BBBB2222", "title": "آپارتمان تهران",
                  "chat_thread_id": "th-b"}
        th_a = {"thread_id": "th-a", "href": "https://divar.ir/v/villa/AAAA1111",
                "title": "ویلای شمال رامسر"}
        self.assertTrue(match_thread_to_lead(th_a, lead_a))
        self.assertFalse(match_thread_to_lead(th_a, lead_b))
        self.assertTrue(listing_gone("این آگهی حذف شده است"))
        self.assertFalse(listing_gone("آگهی سالم برای فروش"))

    def test_inbox_binds_one_lead(self):
        from marketing_divar.db import connect, upsert_lead
        from marketing_divar.inbox import ingest_chat, find_lead_for_chat
        con = connect(os.path.join(tempfile.mkdtemp(), "in.db"))
        upsert_lead(con, {"token": "tokA", "title": "ویلای شمال رامسر", "url":
                          "https://divar.ir/v/villa/tokA", "has_chat": 1}, "ویلا", "iran")
        upsert_lead(con, {"token": "tokB", "title": "آپارتمان تهرانپارس", "url":
                          "https://divar.ir/v/apt/tokB", "has_chat": 1}, "آپارتمان", "iran")
        con.execute("UPDATE leads SET chat_status='sent', chat_thread_id='th-a' WHERE token='tokA'")
        con.execute("UPDATE leads SET chat_status='sent', chat_thread_id='th-b' WHERE token='tokB'")
        con.commit()
        th = {"thread_id": "th-a", "href": "https://divar.ir/v/villa/tokA",
              "title": "ویلای شمال رامسر", "messages": ["فروختم"]}
        lead = find_lead_for_chat(con, th)
        self.assertEqual(lead["token"], "tokA")
        r = ingest_chat(con, th, use_llm=False)
        self.assertTrue(r["ok"])
        self.assertEqual(r["token"], "tokA")
        n = con.execute("SELECT COUNT(*) c FROM replies WHERE token='tokA'").fetchone()["c"]
        self.assertEqual(n, 1)
        n_b = con.execute("SELECT COUNT(*) c FROM replies WHERE token='tokB'").fetchone()["c"]
        self.assertEqual(n_b, 0)
        gone = ingest_chat(con, {"thread_id": "th-a", "status": "removed",
                                 "href": "https://divar.ir/v/villa/tokA",
                                 "messages": []}, use_llm=False)
        self.assertTrue(gone.get("removed"))
        st = con.execute("SELECT phone_status FROM leads WHERE token='tokA'").fetchone()
        self.assertEqual(st["phone_status"], "removed")


class TestClassifyHunterNlu(unittest.TestCase):
    def test_buyer_defect_placeholder(self):
        from marketing_divar.classify import classify_post
        from marketing_divar.db import connect, lead_exists
        from marketing_divar.matching import consider_new_lead
        buyer = classify_post({"title": "خریدار گوشی آیفون نقد"})
        self.assertTrue(buyer["is_buyer"])
        self.assertTrue(buyer["reject"])
        defect = classify_post({"title": "آیفون ۱۳ معیوب صفحه شکسته", "price": 8_000_000})
        self.assertTrue(defect["is_defect"])
        ph = classify_post({"title": "آیفون ۱۳", "price": 1000}, category="mobile-phones")
        self.assertTrue(ph["is_placeholder"])
        self.assertTrue(ph["needs_inquiry"])
        con = connect(os.path.join(tempfile.mkdtemp(), "c.db"))
        self.assertFalse(consider_new_lead(
            con, None, {"token": "buy1", "title": "خریدار آیفون نقد", "url": "u"},
            "آیفون", "iran", fetch_details=False))
        self.assertFalse(lead_exists(con, "buy1"))

    def test_hunter_levels(self):
        from marketing_divar.hunter import deal_level, median_of, score_lead
        samples = [10_000_000] * 6
        self.assertEqual(median_of(samples), 10_000_000)
        self.assertEqual(deal_level(7_500_000, 10_000_000), "great")
        self.assertEqual(deal_level(8_800_000, 10_000_000), "good")
        self.assertEqual(deal_level(4_000_000, 10_000_000), "suspicious")
        sc = score_lead(7_500_000, samples, {})
        self.assertTrue(sc["warm"])
        self.assertEqual(sc["level"], "great")

    def test_nlu_rules(self):
        from marketing_divar.nlu import analyze_rules
        self.assertEqual(analyze_rules("فروختم دیگه موجود نیست")["intent"], "gone")
        self.assertEqual(analyze_rules("صفحه شکسته معیوبه")["intent"], "defect_admit")
        q = analyze_rules("25 میلیون نقد")
        self.assertEqual(q["intent"], "price_quote")
        self.assertEqual(q["slots"]["price_toman"], 25_000_000)
        self.assertEqual(analyze_rules("اول بیعانه بده کارت به کارت")["intent"], "scam_deposit")


class TestPlatformsSmsNluModel(unittest.TestCase):
    def test_tokens_and_html(self):
        from marketing_divar.platforms import lead_token, split_token, enabled_from_settings
        from marketing_divar.sheypoor import parse_listings
        from marketing_divar.ring import parse_listings as ring_parse
        self.assertEqual(lead_token("sheypoor", "99"), "sheypoor:99")
        self.assertEqual(split_token("sheypoor:99"), ("sheypoor", "99"))
        self.assertEqual(split_token("abc"), ("divar", "abc"))
        self.assertEqual(enabled_from_settings({"platform_sheypoor": False,
                                                "platform_ring": False}), ["divar"])
        html = '<a href="https://www.sheypoor.com/v/iphone-13-1234567.html">x</a>'
        posts = parse_listings(html)
        self.assertTrue(any(p["token"] == "sheypoor:1234567" for p in posts))
        rhtml = '<a href="https://ring.ir/a/xyz99">r</a>'
        rp = ring_parse(rhtml)
        self.assertTrue(any(p["token"] == "ring:xyz99" for p in rp))

    def test_sms_inbox_parse(self):
        from marketing_divar.sms import parse_inbox_body, receive_melipayamak
        body = {"Data": [{"From": "09121112233", "Body": "موجوده", "Date": "2026-08-29"}]}
        msgs = parse_inbox_body(body)
        self.assertEqual(msgs[0]["from"], "09121112233")
        self.assertEqual(msgs[0]["body"], "موجوده")

        class R:
            def json(self):
                return body

        rec = receive_melipayamak("u", "p", http_post=lambda url, data, timeout=20: R())
        self.assertTrue(rec["ok"])
        self.assertEqual(len(rec["messages"]), 1)

    def test_nlu_model_not_bundled(self):
        from marketing_divar.nlu_model import MODEL_NAME, is_ready, model_dir, status
        self.assertTrue(MODEL_NAME.endswith(".gguf"))
        st = status()
        self.assertIn("ready", st)
        self.assertIn("model", st)
        # فایل داخل مخزن نیست
        repo_gguf = os.path.join(ROOT, MODEL_NAME)
        self.assertFalse(os.path.isfile(repo_gguf))
        d = str(model_dir())
        self.assertTrue("nlu-model" in d.replace("\\", "/"))
        if not os.path.isfile(os.path.join(d, MODEL_NAME)):
            self.assertFalse(is_ready())


class TestQuotaChats(unittest.TestCase):
    def test_chats_quota(self):
        from marketing_divar.db import bump_quota, connect, quota_today
        con = connect(os.path.join(tempfile.mkdtemp(), "q.db"))
        self.assertEqual(quota_today(con)["chats"], 0)
        bump_quota(con, "chats")
        self.assertEqual(quota_today(con)["chats"], 1)


if __name__ == "__main__":
    unittest.main()
