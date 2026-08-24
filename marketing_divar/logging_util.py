# -*- coding: utf-8 -*-
"""سیستم لاگ قدرتمند — فایل چرخشی + بافر حافظه برای نمایش زنده در رابط وب.

همه رخدادهای مهم (لاگین، شروع/توقف، کپچا، بلاک، شماره گرفته‌شده، خطا)
اینجا ثبت می‌شوند تا عیب‌یابی بعدی دقیق و ممکن باشد.
"""

from __future__ import annotations

import logging
import os
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

def _log_dir() -> Path:
    return Path(os.environ.get("DIVAR_LOG_DIR") or "logs")

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "divar_app.log"

# بافر حافظه برای صفحه «لاگ‌ها» در رابط وب (آخرین ۱۰۰۰ رخداد)
_recent: deque = deque(maxlen=1000)

_formatter = logging.Formatter(
    "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")


class _MemoryHandler(logging.Handler):
    """هر رکورد را در بافر حافظه هم می‌گذارد (برای API لاگ‌ها)."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            _recent.append({
                "time": self.format_time(record),
                "level": record.levelname,
                "name": record.name,
                "msg": record.getMessage(),
            })
        except Exception:  # لاگ هرگز نباید برنامه را بگیرد
            pass

    @staticmethod
    def format_time(record: logging.LogRecord) -> str:
        import time
        return time.strftime("%Y-%m-%d %H:%M:%S",
                             __import__("datetime").datetime.fromtimestamp(
                                 record.created).timetuple())


def setup() -> logging.Logger:
    """راه‌اندازی لاگر اصلی برنامه (یک بار در اجرای سرور صدا زده شود)."""
    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "divar_app.log"
    logger = logging.getLogger("divar")
    if logger.handlers:      # از تکرار هندلر جلوگیری می‌شود
        return logger
    logger.setLevel(logging.INFO)

    fh = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5,
                             encoding="utf-8")
    fh.setFormatter(_formatter)
    logger.addHandler(fh)

    mh = _MemoryHandler()
    mh.setFormatter(_formatter)
    logger.addHandler(mh)

    # Console stays English (main.py banner). Persian events go to the panel.
    if os.environ.get("DIVAR_CONSOLE_LOG") == "1":
        sh = logging.StreamHandler()
        sh.setFormatter(_formatter)
        logger.addHandler(sh)
    return logger


def log(level: str, msg: str) -> None:
    """ثبت رخداد با سطح دلخواه (info/warning/error/success)."""
    logger = logging.getLogger("divar")
    getattr(logger, {"success": "info"}.get(level, level))(msg)


def recent(limit: int = 200, level: str = "") -> list:
    """آخرین لاگ‌ها برای نمایش در وب."""
    items = list(_recent)
    if level:
        items = [i for i in items if i["level"] == level.upper()]
    return items[-limit:]


# سطح سفارشی «موفقیت» برای خوانایی لاگ‌ها
logging.addLevelName(25, "SUCCESS")
logging.Logger.success = (  # type: ignore[attr-defined]
    lambda self, msg, *a, **k: self._log(25, msg, a))  # type: ignore[attr-defined]
