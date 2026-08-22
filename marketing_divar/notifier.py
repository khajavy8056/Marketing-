# -*- coding: utf-8 -*-
"""اعلان‌ها — کنسول + اختیاری تلگرام (مثلاً برای کپچا/بلاک وقتی دور از سیستمید)."""

from __future__ import annotations

from typing import Any, Dict

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore


def notify(cfg: Dict[str, Any], message: str, important: bool = True) -> None:
    """پیام مهم (کپچا، بلاک، پایان سهمیه) را به همه کانال‌های فعال می‌فرستد."""
    prefix = "🚨" if important else "ℹ️"
    print(f"{prefix} {message}")
    t = (cfg or {}).get("notify") or {}
    token, chat_id = t.get("telegram_bot_token"), t.get("telegram_chat_id")
    if token and chat_id and requests is not None:
        try:  # اعلان هرگز نباید برنامه را متوقف کند
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": f"{prefix} {message}"},
                timeout=10)
        except Exception as e:
            print(f"[!] اعلان تلگرام ارسال نشد: {e}")
