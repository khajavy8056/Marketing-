# -*- coding: utf-8 -*-
"""ارسال و خواندن چت از Chromium همان پروفایل — تطبیق دقیق با آگهی.

- هر آگهی با token / thread_id خودش جفت می‌شود؛ چت‌ها قاطی نمی‌شوند.
- آگهی حذف‌شده یا چت بسته‌شده کرش نمی‌کند؛ status=removed برمی‌گردد.
- قفل پروفایل تا دو تب همزمان روی یک اکانت نفرستند.
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from .platforms import listing_url, split_token

_LOCKS: Dict[str, threading.Lock] = {}
_LOCKS_MU = threading.Lock()

_GONE_MARKERS = (
    "آگهی حذف شده", "این آگهی حذف شده", "آگهی مورد نظر یافت نشد",
    "پیدا نشد", "دیگر در دسترس نیست", "این آگهی وجود ندارد",
    "آگهی منقضی", "صفحه مورد نظر پیدا نشد", "not found",
    "this listing is no longer", "ad not found", "deleted",
)


def _profile_lock(key: str) -> threading.Lock:
    with _LOCKS_MU:
        if key not in _LOCKS:
            _LOCKS[key] = threading.Lock()
        return _LOCKS[key]


def listing_gone(html: str, title: str = "") -> bool:
    t = (html or "")
    low = t.lower()
    if any(m in t for m in _GONE_MARKERS):
        return True
    if "404" in t[:800] and ("یافت نشد" in t or "not found" in low):
        return True
    return False


def _js_gone_check() -> str:
    markers = json.dumps(list(_GONE_MARKERS), ensure_ascii=False)
    return (
        """(() => {
          const marks = %s;
          const t = (document.body && document.body.innerText || '') + ' ' + document.title;
          if (marks.some(m => t.includes(m))) return {gone:true, reason:'marker'};
          if ((document.title||'').includes('۴۰۴') || document.title.toLowerCase().includes('404'))
            return {gone:true, reason:'404'};
          return {gone:false, href: location.href, title: document.title||''};
        })()""" % markers
    )


def _chat_click_labels(platform: str) -> list:
    if platform == "sheypoor":
        return ["چت", "گفتگو", "ارسال پیام", "پیام", "شروع گفتگو",
                "پیام به فروشنده", "Chat", "Message"]
    if platform == "disabled_platform":
        return ["چت", "گفتگو", "پیام", "ارسال پیام", "Message", "Chat"]
    return ["چت", "گفتگو", "ارسال پیام", "پیام", "شروع گفتگو",
            "چت با", "Chat", "Message"]


def _js_send(text: str, platform: str = "divar") -> str:
    payload = json.dumps(text, ensure_ascii=False)
    labels = json.dumps(_chat_click_labels(platform), ensure_ascii=False)
    return (
        """(async () => {
          const text = %s;
          const gone = %s;
          const g = eval(gone);
          if (g && g.gone) return {ok:false, status:'removed', message:'آگهی حذف شده'};
          const clickTxt = %s;
          const nodes = Array.from(document.querySelectorAll('button,a,[role=button]'));
          let btn = nodes.find(el => clickTxt.some(t => (el.innerText||'').trim().startsWith(t)));
          if (!btn) btn = nodes.find(el => /چت|گفتگو|پیام/.test(el.innerText||''));
          if (btn) { btn.click(); await new Promise(r => setTimeout(r, 900)); }
          const t2 = (document.body && document.body.innerText) || '';
          if (%s.some(m => t2.includes(m)))
            return {ok:false, status:'removed', message:'چت این آگهی دیگر در دسترس نیست'};
          let box = document.querySelector('textarea')
            || document.querySelector('[contenteditable="true"]')
            || document.querySelector('input[type=text]');
          if (!box) return {ok:false, status:'requires_operator', message:'فیلد پیام پیدا نشد'};
          box.focus();
          if (box.tagName === 'TEXTAREA' || box.tagName === 'INPUT') {
            box.value = text;
            box.dispatchEvent(new Event('input', {bubbles:true}));
          } else {
            box.innerText = text;
            box.dispatchEvent(new Event('input', {bubbles:true}));
          }
          const senders = Array.from(document.querySelectorAll('button,[role=button]'));
          const send = senders.find(el => /ارسال|بفرست|Send/.test((el.innerText||el.getAttribute('aria-label')||'')));
          if (send) send.click();
          else box.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true}));
          await new Promise(r => setTimeout(r, 600));
          return {ok:true, status:'sent', href: location.href, title: document.title||''};
        })()""" % (payload, json.dumps(_js_gone_check()), labels,
                   json.dumps(list(_GONE_MARKERS), ensure_ascii=False))
    )


def _js_read_thread() -> str:
    return """(() => {
      const goneMarks = %s;
      const t = (document.body && document.body.innerText) || '';
      if (goneMarks.some(m => t.includes(m)))
        return {ok:false, status:'removed', messages:[]};
      const nodes = Array.from(document.querySelectorAll('[class*="message"],[class*="bubble"],li,p'));
      const msgs = [];
      for (const el of nodes) {
        const txt = (el.innerText || '').trim();
        if (txt.length < 2 || txt.length > 800) continue;
        if (/ارسال|چت|گفتگو/.test(txt) && txt.length < 20) continue;
        msgs.push(txt);
      }
      const uniq = [];
      for (const m of msgs) { if (!uniq.includes(m)) uniq.push(m); }
      return {ok:true, status:'ok', href: location.href, title: document.title||'',
              messages: uniq.slice(-20)};
    })()""" % json.dumps(list(_GONE_MARKERS), ensure_ascii=False)


def thread_id_from_url(url: str, token: str = "") -> str:
    u = str(url or "")
    for pat in (
        r"/chat/([^/?#]+)",
        r"conversation[=/]([A-Za-z0-9_-]+)",
        r"thread[=/]([A-Za-z0-9_-]+)",
        r"/v/[^/]+/([A-Za-z0-9_-]{5,16})",
        r"/a/([A-Za-z0-9_-]+)",
        r"-([0-9]{6,})\.html",
    ):
        m = re.search(pat, u)
        if m:
            return m.group(1)
    return token or u


def match_thread_to_lead(thread: Dict[str, Any], lead: Dict[str, Any]) -> bool:
    """چت این آگهی است؟ سخت‌گیر — قاطی نشود."""
    tid = str(thread.get("thread_id") or "")
    href = str(thread.get("href") or thread.get("url") or "")
    token = str(lead.get("token") or "")
    native = str(lead.get("native_id") or "")
    plat, nid = split_token(token)
    if not nid:
        nid = native
    stored = str(lead.get("chat_thread_id") or "")
    if stored and tid and stored == tid:
        return True
    if nid and nid in href:
        return True
    if token and token in href:
        return True
    if nid and tid and nid == tid:
        return True
    title = (lead.get("title") or "").strip()
    page_title = (thread.get("title") or "")
    if title and len(title) >= 8 and title in page_title:
        return True
    return False


def _cdp_eval(cdp, expression: str, timeout: float = 20.0) -> Any:
    r = cdp.call("Runtime.evaluate", {
        "expression": expression,
        "awaitPromise": True,
        "returnByValue": True,
    }, timeout=timeout)
    return (r.get("result") or {}).get("value")


def _connect_profile(accounts_dir: str, name: str):
    from .chromium_profile import chromium_dir, is_open, open_profile
    from .session_view import CdpClient, _devtools_port_file, _page_ws_from_list
    from pathlib import Path
    if not is_open(name):
        open_profile(accounts_dir, name)
        time.sleep(1.2)
    prof = chromium_dir(accounts_dir, name)
    port = _devtools_port_file(Path(prof))
    if port <= 0:
        raise RuntimeError("پروفایل Chromium برای چت آماده نیست")
    ws = _page_ws_from_list(port)
    if not ws:
        raise RuntimeError("CDP چت در دسترس نیست")
    return CdpClient(ws), port


def send_on_url(url: str, text: str, accounts_dir: str, account: str,
                token: str = "") -> Dict[str, Any]:
    lock = _profile_lock(account)
    if not lock.acquire(timeout=90):
        return {"ok": False, "status": "requires_operator",
                "message": "پروفایل مشغول است — بعداً"}
    cdp = None
    try:
        cdp, _port = _connect_profile(accounts_dir, account)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Page.navigate", {"url": url}, timeout=25)
        time.sleep(2.2)
        gone = _cdp_eval(cdp, _js_gone_check(), timeout=8)
        if isinstance(gone, dict) and gone.get("gone"):
            return {"ok": False, "status": "removed",
                    "message": "آگهی حذف شده یا چت در دسترس نیست"}
        plat, _nid = split_token(token)
        res = _cdp_eval(cdp, _js_send(text, plat), timeout=25)
        if not isinstance(res, dict):
            return {"ok": False, "status": "requires_operator",
                    "message": "پاسخ صفحه نامعتبر"}
        href = str(res.get("href") or url)
        res["thread_id"] = thread_id_from_url(href, token)
        return res
    except Exception as e:
        msg = str(e)
        if any(x in msg.lower() for x in ("closed", "target", "timeout", "socket")):
            return {"ok": False, "status": "requires_operator",
                    "message": "پنجره چت قطع شد — آگهی ممکن است حذف شده باشد"}
        return {"ok": False, "status": "requires_operator", "message": msg[:200]}
    finally:
        try:
            if cdp:
                cdp.close()
        except Exception:
            pass
        lock.release()


def send_for_token(token: str, text: str, client: Any = None,
                   accounts_dir: str = "", account: str = "",
                   url: str = "") -> Dict[str, Any]:
    plat, nid = split_token(token)
    dest = url or listing_url(plat, nid)
    if not accounts_dir or not account:
        return {"ok": False, "status": "requires_operator",
                "message": "پروفایل Chromium برای ارسال چت مشخص نیست"}
    return send_on_url(dest, text, accounts_dir, account, token=token)


def read_thread(url: str, accounts_dir: str, account: str,
                token: str = "") -> Dict[str, Any]:
    lock = _profile_lock(account)
    if not lock.acquire(timeout=60):
        return {"ok": False, "status": "busy", "messages": []}
    cdp = None
    try:
        cdp, _p = _connect_profile(accounts_dir, account)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Page.navigate", {"url": url}, timeout=25)
        time.sleep(2.0)
        res = _cdp_eval(cdp, _js_read_thread(), timeout=12)
        if not isinstance(res, dict):
            return {"ok": False, "status": "error", "messages": []}
        if res.get("status") == "removed":
            return {"ok": False, "status": "removed", "messages": []}
        href = str(res.get("href") or url)
        res["thread_id"] = thread_id_from_url(href, token)
        res["url"] = href
        return res
    except Exception as e:
        return {"ok": False, "status": "error", "messages": [],
                "message": str(e)[:160]}
    finally:
        try:
            if cdp:
                cdp.close()
        except Exception:
            pass
        lock.release()


def open_json_new_tabs(port: int, urls: List[str]) -> int:
    """سربرگ اضافه روی همان Chromium — GET /json/new?url="""
    from .session_view import _http_get_local
    n = 0
    for u in urls or []:
        try:
            path = "/json/new?" + quote(u, safe=":/?&=#%")
            _http_get_local(int(port), path, timeout=2.5)
            n += 1
            time.sleep(0.25)
        except Exception:
            pass
    return n
