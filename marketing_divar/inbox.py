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


def find_candidate_leads_for_unknown_sms(con: sqlite3.Connection, incoming_phone: str, incoming_text: str = "", limit: int = 15) -> List[sqlite3.Row]:
    """وقتی شماره ناشناس است (احتمال سیم دوم)، آخرین آگهی‌های پیام رفته که هنوز پاسخ نگرفته را برگردان"""
    try:
        # آخرین 20 آگهی که پیامک رفته و هنوز پاسخ نگرفته یا در انتظار مذاکره است
        rows = con.execute(
            "SELECT * FROM leads WHERE sms_status='sent' AND phone!='' "
            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return rows
    except Exception:
        return []


def detect_second_sim_in_sms(incoming_phone: str, lead_phone: str, incoming_text: str, lead_title: str = "") -> Dict[str, Any]:
    """تشخیص سیم دوم + متن مبهم برای SMS ورودی"""
    try:
        from .tira_agent import detect_second_sim_reply, detect_ambiguous_text_reply
        # اول متن مبهم
        amb = detect_ambiguous_text_reply(incoming_text, ad_title=lead_title)
        if amb.get("need_clarify"):
            return {"need_clarify": True, "is_ambiguous": True, "message": amb["message"], "log": f"متن مبهم SMS: {incoming_text[:40]}"}
        # بعد شماره متفاوت
        if incoming_phone and lead_phone:
            det = detect_second_sim_reply(incoming_phone, lead_phone, ad_token="", ad_title=lead_title, incoming_text=incoming_text)
            if det.get("need_clarify"):
                return det
    except Exception as e:
        pass
    return {"need_clarify": False, "message": ""}


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
            # v4: اطلاع‌رسانی جواب موبایل در روبیکا
            try:
                title = lead["title"] if "title" in lead.keys() else ""
                phone = lead["phone"] if "phone" in lead.keys() else ""
                city = lead["city"] if "city" in lead.keys() else ""
                kw = lead["keyword"] if "keyword" in lead.keys() else ""
                platform = lead["platform"] if "platform" in lead.keys() else "divar"
                # فقط اگر موبایل یا همه، خبر بده
                from .notifier import notify_mobile_reply
                from .store import settings_all
                import os
                db_path = os.environ.get("DIVAR_DB_PATH", "data/divar_leads.db")
                cfg = {"notify": settings_all(db_path)}
                notify_mobile_reply(cfg, title=title, phone=phone, reply_text=body, platform=platform, city=city, keyword=kw)
            except Exception:
                pass
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
    second_sim_info = None
    if not lead:
        # احتمال سیم دوم — شماره ناشناس
        cands = find_candidate_leads_for_unknown_sms(con, phone, body, limit=10)
        # اگر متن مبهم است (شما؟)، اولین کاندید را بگیر و شفاف‌سازی کن
        try:
            from .tira_agent import detect_ambiguous_text_reply
            amb = detect_ambiguous_text_reply(body, ad_title="")
            if amb.get("need_clarify") and cands:
                # اولین کاندید که هنوز نیاز به اقدام دارد
                lead = cands[0]
                second_sim_info = {"is_second_sim": True, "need_clarify": True, "message": amb["message"], "incoming_phone": phone, "candidate_token": lead["token"], "reason": "ambiguous_text_unknown_number"}
        except Exception:
            pass
        if not lead:
            return {"ok": False, "reason": "unmatched", "second_sim_check": "no_candidate"}

    # اگر lead پیدا شد، چک کن آیا سیم دوم است یا متن مبهم
    if lead:
        lead_phone = lead["phone"] if "phone" in lead.keys() else ""
        lead_title = lead["title"] if "title" in lead.keys() else ""
        det = detect_second_sim_in_sms(phone, lead_phone, body, lead_title)
        if det.get("need_clarify"):
            second_sim_info = det
            # پیام شفاف‌سازی را به عنوان پاسخ ذخیره کن تا در لاگ دیده شود
            # و همچنین سعی کن خودکار پیام شفاف‌سازی بفرستی (اگر sms_auto روشن باشد)
            try:
                # ذخیره لاگ دوم
                pass
            except Exception:
                pass

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
    # v4: اطلاع‌رسانی جواب موبایل در روبیکا
    if saved:
        try:
            title = lead["title"] if "title" in lead.keys() else ""
            lead_phone = lead["phone"] if "phone" in lead.keys() else ""
            city = lead["city"] if "city" in lead.keys() else ""
            kw = lead["keyword"] if "keyword" in lead.keys() else ""
            platform = lead["platform"] if "platform" in lead.keys() else "divar"
            from .notifier import notify_mobile_reply
            from .store import settings_all
            import os
            db_path = os.environ.get("DIVAR_DB_PATH", "data/divar_leads.db")
            cfg = {"notify": settings_all(db_path)}
            notify_mobile_reply(cfg, title=title, phone=lead_phone, reply_text=body, platform=platform, city=city, keyword=kw)
        except Exception:
            pass
    out = {"ok": True, "token": lead["token"], "stored": int(saved), "nlu": last}
    if second_sim_info and second_sim_info.get("need_clarify"):
        out["second_sim"] = second_sim_info
        out["need_clarify"] = True
        out["clarify_message"] = second_sim_info.get("message")
    return out


def _context(lead) -> str:
    try:
        st = lead["inquiry_status"] if "inquiry_status" in lead.keys() else ""
    except Exception:
        st = ""
    try:
        hl = lead["hunter_level"] if "hunter_level" in lead.keys() else ""
    except Exception:
        hl = ""
    if st in ("sent", "pending") or hl == "pending":
        return "inquire"
    return "marketing"


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
