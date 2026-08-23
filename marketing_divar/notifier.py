# -*- coding: utf-8 -*-
"""اعلان‌ها — کنسول + اختیاری تلگرام (مثلاً برای کپچا/بلاک وقتی دور از سیستمید)."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore


def format_alert(message: str, account: str = "", problem: str = "",
                 operation: str = "", action: str = "") -> str:
    """متن اعلان ساخت‌یافته برای اپراتور."""
    lines = [message]
    if account:
        lines.append(f"اکانت: {account}")
    if problem:
        lines.append(f"مشکل: {problem}")
    if operation:
        lines.append(f"عملیات: {operation}")
    lines.append(f"زمان: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    if action:
        lines.append(f"اقدام لازم: {action}")
    return "\n".join(lines)


def notify(cfg: Dict[str, Any], message: str, important: bool = True,
           account: str = "", problem: str = "", operation: str = "",
           action: str = "") -> None:
    """پیام مهم (کپچا، بلاک، پایان سهمیه) را به همه کانال‌های فعال می‌فرستد."""
    prefix = "🚨" if important else "ℹ️"
    text = format_alert(message, account=account, problem=problem,
                        operation=operation, action=action)
    print(f"{prefix} {text}")
    t = (cfg or {}).get("notify") or {}
    token, chat_id = t.get("telegram_bot_token"), t.get("telegram_chat_id")
    if token and chat_id and requests is not None:
        try:  # اعلان هرگز نباید برنامه را متوقف کند
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": f"{prefix} {text}"},
                timeout=10)
        except Exception as e:
            print(f"[!] اعلان تلگرام ارسال نشد: {e}")
