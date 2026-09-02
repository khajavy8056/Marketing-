# -*- coding: utf-8 -*-
"""تیرا v4.0 — کالاهای غیرمعمول، دستور اجرایی، پیامک، ربات، پایش دسته."""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


class TestTiraCommands(unittest.TestCase):
    def test_guess_vacuum(self):
        from marketing_divar.tira_commands import guess_product
        g = guess_product("جاروبرقی بوش می‌خوام")
        self.assertEqual(g["slug"], "vacuum-cleaner")
        self.assertEqual(g["family"], "appliance")

    def test_classify_sms_guide_long(self):
        from marketing_divar.tira_commands import classify_intent
        t = ("چطور پنل پیامکی ملی‌پیامک را تنظیم کنم تا بتونم متصلش کنم "
             "و بعد از استخراج شماره پیامک خودکار بره؟ توضیح کامل بده.")
        self.assertGreaterEqual(len(t), 100)
        self.assertEqual(classify_intent(t)["kind"], "guide_sms")

    def test_classify_set_sms_template(self):
        from marketing_divar.tira_commands import classify_intent
        t = "متن پیامک را بگذار سلام، آگهی «{title}» را در {city} دیدم."
        intent = classify_intent(t)
        self.assertEqual(intent["kind"], "set_sms_template")
        self.assertIn("{title}", intent.get("text") or "")

    def test_classify_browse_mobiles(self):
        from marketing_divar.tira_commands import classify_intent
        t = "هرچی موبایل تو دیوار و شیپور هست بگیر، شماره‌هاشون را بکش بیرون و پیام بره"
        intent = classify_intent(t)
        self.assertEqual(intent["kind"], "browse_category")
        self.assertEqual(intent["category"], "mobile-phones")
        self.assertTrue(intent.get("send_sms"))
        self.assertFalse(intent.get("hunter"))

    def test_classify_vacuum_hunt(self):
        from marketing_divar.tira_commands import classify_intent
        intent = classify_intent("جاروبرقی شکار کن")
        self.assertEqual(intent["kind"], "hunt")
        self.assertEqual(intent["product"]["slug"], "vacuum-cleaner")

    def test_classify_enable_sms(self):
        from marketing_divar.tira_commands import classify_intent
        self.assertTrue(classify_intent("پیامک خودکار را روشن کن")["on"])
        self.assertFalse(classify_intent("پیامک خودکار را خاموش کن")["on"])


class TestTiraAgentV4(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "t.db")
        self._prev_db = os.environ.get("DIVAR_DB_PATH")
        os.environ["DIVAR_DB_PATH"] = self.db
        from marketing_divar.tira_agent import reset_tira_sessions
        reset_tira_sessions()

    def tearDown(self):
        if self._prev_db is None:
            os.environ.pop("DIVAR_DB_PATH", None)
        else:
            os.environ["DIVAR_DB_PATH"] = self._prev_db
        from marketing_divar.tira_agent import reset_tira_sessions
        reset_tira_sessions()

    def test_long_sms_guide_executable(self):
        from marketing_divar.tira_agent import TiraAgent
        ag = TiraAgent("t-sms")
        t = ("چطور پنل پیامکی را تنظیم کنم تا بتونم متصلش کنم و پیامک بره؟ "
             "مرحله‌به‌مرحله بگو از ثبت‌نام ملی‌پیامک تا تیک خودکار.")
        self.assertGreaterEqual(len(t), 100)
        r = ag.handle_user(t)
        self.assertIn("ملی", r["reply"])
        self.assertEqual(r.get("guide") or r.get("kind"), "sms" if r.get("guide") else r.get("kind"))
        self.assertIn(r.get("step"), ("guide_sms", "sms_status"))

    def test_set_sms_template_saves(self):
        from marketing_divar.tira_agent import TiraAgent
        from marketing_divar.store import template_get
        ag = TiraAgent("t-tpl")
        body = "سلام آگهی {title} در {city}"
        r = ag.handle_user("متن پیامک را بگذار " + body)
        self.assertIn("قالب پیامک", r["reply"])
        rec = template_get(self.db, "sms") or {}
        self.assertIn("{title}", rec.get("text") or "")

    def test_browse_mobiles_adds_keyword_without_hunter(self):
        from marketing_divar.tira_agent import TiraAgent
        from marketing_divar.store import keywords_list
        ag = TiraAgent("t-br")
        r = ag.handle_user(
            "هرچی موبایل تو دیوار و شیپور هست بگیر، شماره‌هاشون را بکش بیرون و پیام بره")
        self.assertIn("پایش", r["reply"])
        kws = keywords_list(self.db)
        self.assertTrue(kws)
        self.assertEqual(kws[0].get("category"), "mobile-phones")
        self.assertFalse(kws[0].get("hunter"))
        self.assertTrue(kws[0].get("browse"))

    def test_vacuum_research_not_iphone(self):
        from marketing_divar.tira_agent import TiraAgent, research_any_product
        from marketing_divar.market_research import research_product
        res = research_product("جاروبرقی بوش")
        self.assertEqual(res["type"], "appliance")
        keys = [f["key"] for f in res["factors"]]
        self.assertNotIn("battery_low", keys)
        self.assertTrue(any(k in keys for k in ("motor_weak", "used", "no_warranty")))
        anyp = research_any_product("جاروبرقی")
        self.assertEqual(anyp["type"], "appliance")
        ag = TiraAgent("t-vac")
        r = ag.handle_user("جاروبرقی شکار کن")
        self.assertIn("جاروبرقی", r["reply"])
        self.assertNotIn("آیفون 13", r["reply"])


class TestSmsAndNotify(unittest.TestCase):
    def test_custom_text_overrides_template(self):
        from marketing_divar.sms import send_for_lead

        seen = {}

        class R:
            def json(self):
                return {"Value": "9000000999"}

        def poster(url, data, timeout=20):
            seen["text"] = data["text"]
            return R()

        r = send_for_lead({
            "sms_provider": "melipayamak",
            "sms_username": "u", "sms_password": "p",
            "sms_line_number": "3000",
        }, {"phone": "09121112233", "title": "ویلا",
            "custom_text": "متن سفارشی {title}"},
            "قالب پیش‌فرض {title}", http_post=poster)
        self.assertTrue(r["ok"])
        self.assertIn("متن سفارشی", seen["text"])
        self.assertIn("ویلا", seen["text"])
        self.assertNotIn("قالب پیش‌فرض", seen["text"])

    def test_sms_connection_report_incomplete(self):
        from marketing_divar.tira_commands import sms_connection_report
        rep = sms_connection_report({"sms_provider": "none"})
        self.assertFalse(rep["ok"])
        self.assertTrue(rep["missing"])

    def test_sms_connection_report_ready(self):
        from marketing_divar.tira_commands import sms_connection_report
        cfg = {
            "sms_provider": "melipayamak",
            "sms_username": "u", "sms_password": "p",
            "sms_line_number": "5000",
            "sms_auto_on_new": True,
            "sms_inbox_on": True,
        }
        rep = sms_connection_report(cfg)
        self.assertTrue(rep["ready"])
        self.assertTrue(rep["ok"])

    def test_notify_mobile_prefers_rubika(self):
        from marketing_divar import tira_commands as tc
        sent = []

        def fake_rubika(cfg, text, extra=None):
            sent.append(("rubika", text))
            return True

        def fake_notify(cfg, text, important=False):
            sent.append(("notify", text))
            return True

        import marketing_divar.notifier as n
        old_sr, old_n = n.send_rubika, n.notify
        n.send_rubika = fake_rubika
        n.notify = fake_notify
        try:
            lead = {"title": "آیفون 13", "phone": "09120000000",
                    "category": "mobile-phones", "keyword": "آیفون"}
            out = tc.notify_seller_reply(
                lead, "سلام موجوده",
                nlu={"intent": "available_yes", "summary_fa": "موجود"},
                channel="sms",
                cfg={"notify": {"rubika_bot_token": "RT", "rubika_chat_id": "8",
                                "rubika_enabled": True}})
            self.assertTrue(out["mobile"])
            self.assertIn("rubika", out["sent"])
            self.assertTrue(any(x[0] == "rubika" and "موبایل" in x[1] for x in sent))
        finally:
            n.send_rubika = old_sr
            n.notify = old_n


class TestBotTira(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "t.db")
        self._prev_db = os.environ.get("DIVAR_DB_PATH")
        os.environ["DIVAR_DB_PATH"] = self.db
        from marketing_divar.tira_agent import reset_tira_sessions
        reset_tira_sessions()

    def tearDown(self):
        if self._prev_db is None:
            os.environ.pop("DIVAR_DB_PATH", None)
        else:
            os.environ["DIVAR_DB_PATH"] = self._prev_db

    def test_unknown_slash_still_unknown(self):
        from marketing_divar.telegram_bot import handle_command
        self.assertIn("ناشناخته", handle_command("/nope", self.db, {}))

    def test_bot_sms_guide(self):
        from marketing_divar.telegram_bot import handle_command
        t = handle_command("چطور پنل پیامکی را تنظیم کنم؟", self.db, {})
        self.assertIn("ملی", t)

    def test_bot_browse(self):
        from marketing_divar.telegram_bot import handle_command
        from marketing_divar.store import keywords_list
        t = handle_command(
            "همه موبایل‌ها را بگیر و پیامک بده", self.db, {})
        self.assertIn("پایش", t)
        self.assertTrue(keywords_list(self.db))


class TestNluKwargsDummyMemory(unittest.TestCase):
    def test_analyze_accepts_keyword(self):
        from marketing_divar.nlu import analyze, analyze_for_platform
        r = analyze("قیمت نقدی 45 میلیون سالم", use_llm=False,
                    keyword="آیفون", category="mobile-phones")
        self.assertIn("intent", r)
        r2 = analyze_for_platform("فروخته شد", platform="divar",
                                  keyword="آیفون", category="mobile-phones")
        self.assertEqual(r2["intent"], "gone")

    def test_dummy_model(self):
        from marketing_divar.nlu_model import (
            backend_name, ensure_dummy_model_for_test, infer_json, is_ready, status)
        ensure_dummy_model_for_test()
        self.assertTrue(is_ready())
        self.assertEqual(backend_name(), "fallback-smart")
        st = status()
        self.assertTrue(st["ready"])
        self.assertEqual(st["backend"], "fallback-smart")
        out = infer_json("تو فقط طبقه‌بند هستی. متن:\nفروخته شد")
        self.assertIn("intent", out)
        self.assertIn("gone", out)

    def test_remember_listing_title_kw(self):
        from marketing_divar.nlu_memory import remember_listing
        remember_listing("tok1", "آیفون ۱۳ تمیز", category="mobile-phones",
                         keyword="آیفون", platform="divar")

    def test_categories_vacuum(self):
        from marketing_divar.categories import normalize_slug, search_slug, title_of
        from marketing_divar.hunter_profile import family_of, guess_category
        self.assertEqual(normalize_slug("vacuum-cleaner"), "vacuum-cleaner")
        self.assertEqual(title_of("vacuum-cleaner"), "جاروبرقی")
        self.assertEqual(search_slug("vacuum-cleaner", "divar"), "home-kitchen")
        self.assertEqual(family_of("vacuum-cleaner"), "appliance")
        self.assertEqual(guess_category("جاروبرقی"), "vacuum-cleaner")

    def test_editable_bot_flags(self):
        from marketing_divar.store import EDITABLE_SETTINGS
        self.assertIn("telegram_enabled", EDITABLE_SETTINGS)
        self.assertIn("bale_enabled", EDITABLE_SETTINGS)
        self.assertIn("rubika_enabled", EDITABLE_SETTINGS)

    def test_platform_toggle_req_defined(self):
        from marketing_divar.web.server import PlatformToggleReq
        r = PlatformToggleReq(name="acc1", platform="divar", enabled=True)
        self.assertEqual(r.name, "acc1")

    def test_battery_regex(self):
        import re
        from marketing_divar.tira_agent import TiraAgent
        m = re.search(r"باتری.*?(\d{2,3})", "باتری بالای 85")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "85")
        ag = TiraAgent("rx")
        ag.state["step"] = "ask_details"
        ag.state["variants_selected"] = ["آیفون 13"]
        ag.state["answers"] = {"آیفون 13": {"sell_price": 25_000_000, "profit_pct": 10,
                                             "profit_toman": 2_500_000}}
        r = ag.handle_user("خش نداشته باشه، باتری بالای 85، رجیستر شده")
        self.assertTrue(any("85" in c for c in ag.state.get("conditions") or []))


class TestVersion(unittest.TestCase):
    def test_version_40(self):
        from marketing_divar import __version__
        self.assertTrue(__version__.startswith("4.0"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
