# -*- coding: utf-8 -*-
"""مدیریت چند اکانت دیوار + چرخش (Round-Robin) بین آن‌ها.

نکات کلیدی طراحی:
- هر اکانت سشن و فایل وضعیت خودش را دارد → اگر یکی کپچا/کوچ شود، بقیه ادامه می‌دهند.
- سهمیه روزانه جدا برای هر اکانت + سقف کلی IP (همه از یک IP می‌روند و دیوار
  اکانت‌های یک دستگاه را می‌تواند مرتبط ببیند → سقف کلی محافظه‌کارانه).
- وضعیت‌ها در data/accounts/state.json ذخیره می‌شوند تا از یک ترمینال دیگر هم
  بشود اکانت را آزاد کرد (فرمان: accounts release NAME).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .db import account_quota_today, bump_account_quota, connect

ACCOUNTS_DIR = "data/accounts"


class AccountManager:
    def __init__(self, cfg: Dict[str, Any], accounts_dir: str = ACCOUNTS_DIR):
        self.cfg = cfg
        self.dir = Path(accounts_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.dir / "state.json"

    # ---------------------------------------------------------- حساب‌ها --
    def list_accounts(self) -> List[str]:
        names = []
        for p in sorted(self.dir.glob("*/session.json")):
            names.append(p.parent.name)
        return names

    def session_path(self, name: str) -> Path:
        return self.dir / name / "session.json"

    def has_token(self, name: str) -> bool:
        p = self.session_path(name)
        if not p.exists():
            return False
        try:
            return bool(json.loads(p.read_text(encoding="utf-8")).get("token"))
        except Exception:
            return False

    def login_account(self, name: str) -> None:
        """لاگین تعاملی یک اکانت مشخص (شماره + کد پیامکی)."""
        from .client import DivarClient  # import داخلی برای جلوگیری از حلقه
        name = name.strip().lower().replace(" ", "-")
        if not name:
            raise ValueError("نام اکانت خالی است")
        cl = DivarClient(session_path=str(self.session_path(name)))
        cl.login_interactive()
        self.set_status(name, "active")

    # ---------------------------------------------------------- وضعیت‌ها --
    def _load_states(self) -> Dict[str, Any]:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_states(self, st: Dict[str, Any]) -> None:
        self.state_path.write_text(
            json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")

    def set_status(self, name: str, status: str,
                   cooldown_sec: float = 0.0, note: str = "") -> None:
        st = self._load_states()
        rec = st.get(name) or {}
        rec.update({"status": status,
                    "cooldown_until": (time.time() + cooldown_sec
                                       if status == "cooldown" else rec.get("cooldown_until", 0)),
                    "note": note or rec.get("note", ""),
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")})
        st[name] = rec
        self._save_states(st)

    def release(self, name: str) -> None:
        """اپراتور کپچا را حل کرد → اکانت آزاد می‌شود (حتی از ترمینال دیگر)."""
        self.set_status(name, "active", note="released by operator")

    # ------------------------------------------------------------- چرخش --
    def pick(self, db_path: str) -> Optional[str]:
        """بهترین اکانت فعال برای درخواست بعدی:
        سشن سالم + بدون کپچا/کوچ + زیر سهمیه روزانه + کم‌ترین مصرف امروز."""
        now = time.time()
        con = connect(db_path)
        try:
            per_limit = int(self.cfg.get("per_account_daily_limit", 129) or 129)
            adaptive = bool(self.cfg.get("adaptive_until_captcha", True))
            best, best_used = None, None
            for name in self.list_accounts():
                rec = self._load_states().get(name) or {}
                status = rec.get("status", "active")
                if status in ("captcha", "relogin", "disabled"):
                    continue
                if status == "cooldown" and now < rec.get("cooldown_until", 0):
                    continue
                if not self.has_token(name):
                    continue
                used = account_quota_today(con, name)
                # سقف نرم: اگر حالت هوشمند روشن باشد تا کپچای واقعی دیوار ادامه می‌دهد
                if used >= per_limit and not adaptive:
                    continue
                if best_used is None or used < best_used:
                    best, best_used = name, used
            return best
        finally:
            con.close()

    def record_use(self, db_path: str, name: str) -> None:
        con = connect(db_path)
        try:
            bump_account_quota(con, name)
        finally:
            con.close()

    def snapshot(self, db_path: str) -> List[Dict[str, Any]]:
        """گزارش کامل برای فرمان status داخل مانیتور."""
        con = connect(db_path)
        try:
            out = []
            states = self._load_states()
            for name in self.list_accounts():
                rec = states.get(name) or {}
                status = rec.get("status", "active")
                if status == "cooldown" and time.time() >= rec.get("cooldown_until", 0):
                    status = "active"
                out.append({"name": name, "status": status,
                            "note": rec.get("note", ""),
                            "has_token": self.has_token(name),
                            "phones_today": account_quota_today(con, name)})
            return out
        finally:
            con.close()
