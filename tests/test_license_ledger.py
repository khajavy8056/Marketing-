# -*- coding: utf-8 -*-
"""بخش ۱ لایسنس: دفترچه سطری + ساعت از هدر اینترنت."""

import os
import sys
import unittest
from datetime import datetime, timezone
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

CSV = (
    "first_name,last_name,username,password,phone,plan,started,expires,status,note\n"
    "علی,دمو,demo,demo123,09120000000,demo,2026-08-01,2026-09-15,active,نمونه\n"
    "رضا,قطع,off,x,09121111111,full,2026-01-01,2026-12-31,disabled,\n"
    "مریم,تمام,old,y,09122222222,full,2026-01-01,2026-01-10,active,\n"
)


def _resp(body=CSV, status=200, date="Sat, 29 Aug 2026 12:00:00 GMT"):
    r = mock.Mock()
    r.status_code = status
    r.headers = {"Date": date} if date is not None else {}
    r.content = body.encode("utf-8")
    return r


class TestLicenseLedger(unittest.TestCase):
    def test_repo_file_has_header_and_demo_row(self):
        path = os.path.join(ROOT, "license", "ok.csv")
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
        self.assertIn("first_name", text)
        self.assertIn("last_name", text)
        self.assertIn("username", text)
        self.assertIn("expires", text)
        self.assertIn("demo", text)

    def test_parse_and_http_date(self):
        from marketing_divar.license_ledger import parse_csv, parse_http_date
        rows = parse_csv(CSV)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["first_name"], "علی")
        self.assertEqual(rows[0]["username"], "demo")
        dt = parse_http_date("Sat, 29 Aug 2026 12:00:00 GMT")
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 8)
        self.assertEqual(dt.day, 29)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def _http(self, resp=None, error=None):
        fake = mock.Mock()
        fake.RequestException = Exception
        if error is not None:
            fake.get.side_effect = fake.RequestException(error)
        else:
            fake.get.return_value = resp if resp is not None else _resp()
        return mock.patch.dict(sys.modules, {"requests": fake})

    def test_login_uses_internet_date_not_pc_clock(self):
        from marketing_divar.license_ledger import check_login
        with self._http(_resp()):
            ok = check_login("demo", "demo123", url="https://example.test/ok.csv")
            self.assertTrue(ok["ok"])
            self.assertEqual(ok["plan"], "demo")
            self.assertEqual(ok["days_left"], (datetime(2026, 9, 15) -
                                               datetime(2026, 8, 29)).days)
            self.assertEqual(ok["full_name"], "علی دمو")
            self.assertEqual(ok["span_days"], 45)
            self.assertEqual(ok["started"], "2026-08-01")
            self.assertEqual(check_login("demo", "wrong",
                                         url="https://example.test/ok.csv")["reason"],
                             "bad_pass")
            self.assertEqual(check_login("nobody", "x",
                                         url="https://example.test/ok.csv")["reason"],
                             "bad_user")
            self.assertEqual(check_login("off", "x",
                                         url="https://example.test/ok.csv")["reason"],
                             "disabled")
            self.assertEqual(check_login("old", "y",
                                         url="https://example.test/ok.csv")["reason"],
                             "expired")

    def test_no_internet(self):
        from marketing_divar.license_ledger import check_login
        with self._http(error="down"):
            r = check_login("demo", "demo123", url="https://example.test/ok.csv")
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "no_internet")
        self.assertIn("اینترنت", r["message_fa"])

    def test_missing_date_header_is_no_internet_time(self):
        from marketing_divar.license_ledger import check_login
        with self._http(_resp(date="")):
            r = check_login("demo", "demo123", url="https://example.test/ok.csv")
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "no_internet")


if __name__ == "__main__":
    unittest.main()
