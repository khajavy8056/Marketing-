# -*- coding: utf-8 -*-
"""صندوق پاسخ چت و پیامک — تطبیق دقیق با همان آگهی."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from .chat_browser import match_thread_to_lead, thread_id_from_url
from .db import now
from .nlu import analyze, apply_to_lead
from .sms import normalize_ir_phone


def save_reply(con: sqlite3.Connection, rec: Dict[str, Any]) -> bool:
    """True اگر ردیف جدید درج شد (تکراری نباشد)."""
    token = rec.get("token") or ""
    body = (rec.get("body") or "").strip()
    if not body:
        return False
    thread = rec.get("thread_id") or ""
    channel = rec.get("channel") or "chat"
    received = rec.get("received_at") or now()
    prev = con.execute(
        "SELECT id FROM replies WHERE channel=? AND body=? AND "
        "COALESCE(thread_id,'')=? AND COALESCE(token,'')=? "
        "AND COALESCE(received_at,'')=?",
        (channel, body, thread, token, received)).fetchone()
    if prev:
        return False
    nlu = rec.get("nlu") or {}
    con.execute(
        "INSERT INTO replies (token, platform, channel, thread_id, phone, body, "
        "direction, received_at, nlu_intent, nlu_confidence, nlu_summary, nlu_slots) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (token, rec.get("platform") or "divar", channel, thread,
         rec.get("phone") or "", body, rec.get("direction") or "in", received,
         nlu.get("intent") or "", float(nlu.get("confidence") or 0),
         nlu.get("summary_fa") or "",
         json.dumps(nlu.get("slots") or {}, ensure_ascii=False)))
    con.commit()
    return True


def find_lead_for_chat(con: sqlite3.Connection, thread: Dict[str, Any]
                       ) -> Optional[sqlite3.Row]:
    """سخت‌گیر: اول thread_id ذخیره‌شده، بعد token در URL."""
    tid = str(thread.get("thread_id") or thread_id_from_url(
        thread.get("href") or thread.get("url") or ""))
    if tid:
        row = con.execute(
            "SELECT * FROM leads WHERE chat_thread_id=? ORDER BY id DESC LIMIT 1",
            (tid,)).fetchone()
        if row:
            return row
    rows = con.execute(
        "SELECT * FROM leads WHERE chat_status IN ('sent','available') "
        "OR phone_status='hidden' ORDER BY id DESC LIMIT 80").fetchall()
    for row in rows:
        lead = dict(row)
        if match_thread_to_lead(thread, lead):
            return row
    return None


def find_lead_for_sms(con: sqlite3.Connection, phone: str) -> Optional[sqlite3.Row]:
    p = normalize_ir_phone(phone)
    if not p:
        return None
    row = con.execute(
        "SELECT * FROM leads WHERE phone=? AND "
        "(sms_status='sent' OR inquiry_status='sent') "
        "ORDER BY id DESC LIMIT 1", (p,)).fetchone()
    if row:
        return row
    return con.execute(
        "SELECT * FROM leads WHERE phone=? ORDER BY id DESC LIMIT 1", (p,)
    ).fetchone()


def ingest_chat(con, thread: Dict[str, Any], use_llm: bool = True) -> Dict[str, Any]:
    lead = find_lead_for_chat(con, thread)
    if not lead:
        return {"ok": False, "reason": "unmatched"}
    token = lead["token"]
    msgs = list(thread.get("messages") or [])
    stored = 0
    last = None
    for body in msgs[-8:]:
        nlu = analyze(body, use_llm=use_llm)
        rec = {
            "token": token,
            "platform": lead["platform"] if "platform" in lead.keys() else "divar",
            "channel": "chat",
            "thread_id": (thread.get("thread_id")
                          or (lead["chat_thread_id"]
                              if "chat_thread_id" in lead.keys() else "")),
            "body": body,
            "nlu": nlu,
        }
        if save_reply(con, rec):
            stored += 1
            last = apply_to_lead(con, token, nlu, context=_context(lead))
    if thread.get("status") == "removed":
        try:
            con.execute(
                "UPDATE leads SET phone_status='removed', removed_reason='chat_gone' "
                "WHERE token=?", (token,))
            con.commit()
        except Exception:
            pass
        return {"ok": True, "token": token, "removed": True, "stored": stored}
    return {"ok": True, "token": token, "stored": stored, "nlu": last}


def ingest_sms(con, phone: str, body: str, received_at: str = "",
               use_llm: bool = True) -> Dict[str, Any]:
    lead = find_lead_for_sms(con, phone)
    if not lead:
        return {"ok": False, "reason": "unmatched"}
    nlu = analyze(body, use_llm=use_llm)
    rec = {
        "token": lead["token"],
        "platform": lead["platform"] if "platform" in lead.keys() else "divar",
        "channel": "sms",
        "phone": normalize_ir_phone(phone), "body": body,
        "received_at": received_at, "nlu": nlu,
    }
    saved = save_reply(con, rec)
    last = apply_to_lead(con, lead["token"], nlu, context=_context(lead)) if saved else None
    return {"ok": True, "token": lead["token"], "stored": int(saved), "nlu": last}


def _context(lead) -> str:
    try:
        st = lead["inquiry_status"] if "inquiry_status" in lead.keys() else ""
    except Exception:
        st = ""
    return "inquire" if st in ("sent", "pending") else "marketing"


def list_replies(con, token: str = "", limit: int = 80) -> List[Dict[str, Any]]:
    if token:
        rows = con.execute(
            "SELECT * FROM replies WHERE token=? ORDER BY id DESC LIMIT ?",
            (token, limit)).fetchall()
    else:
        rows = con.execute(
            "SELECT * FROM replies ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["intent"] = d.get("nlu_intent") or ""
        out.append(d)
    return out
