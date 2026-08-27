# -*- coding: utf-8 -*-
"""Endpoint های FastAPI برای نشست ریموت پروفایل‌ها + پل WebSocket به noVNC.

همهٔ مسیرها پشت احراز هویت پنل هستند (میان‌افزار در app.py). websockify فقط روی
127.0.0.1 گوش می‌دهد؛ مرورگر اپراتور از طریق این پلِ WebSocket به آن وصل می‌شود،
بنابراین هیچ پورت عمومی روی سرور باز نمی‌شود.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from . import remote_session

router = APIRouter(prefix="/api/remote", tags=["remote"])

_ACCOUNTS_DIR = None
_auth_checker = None


def configure(accounts_dir: str, auth_checker=None) -> None:
    global _ACCOUNTS_DIR, _auth_checker
    _ACCOUNTS_DIR = accounts_dir
    _auth_checker = auth_checker


def _acc_dir() -> str:
    if _ACCOUNTS_DIR:
        return _ACCOUNTS_DIR
    import os
    return os.environ.get("DIVAR_ACCOUNTS_DIR", "data/accounts")


def _is_authenticated(ws: WebSocket) -> bool:
    if _auth_checker is None:
        return True
    token = ws.cookies.get("divar_session")
    return bool(_auth_checker(token))


class RemoteOpen(BaseModel):
    name: str


@router.get("/sessions")
def sessions():
    return remote_session.status()


@router.post("/{name}/open")
def open_session(name: str):
    try:
        remote_session.touch(name)
        return remote_session.open_remote(_acc_dir(), name)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/{name}/close")
def close_session(name: str):
    return remote_session.close_remote(name)


@router.get("/{name}/status")
def session_status(name: str):
    return remote_session.status(name)


@router.post("/{name}/verify")
def verify(name: str):
    try:
        return remote_session.verify_login(_acc_dir(), name)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.websocket("/{name}/ws")
async def ws_relay(ws: WebSocket, name: str):
    """پل مرورگر اپراتور ⇄ websockify همان نشست (noVNC)."""
    if not _is_authenticated(ws):
        await ws.close(code=1008, reason="احراز هویت لازم است")
        return
    st = remote_session.status(name)
    s = st.get("session") or {}
    ws_port = s.get("ws_port")
    if not st.get("open") or not ws_port:
        await ws.close(code=1011, reason="نشست ریموت باز نیست")
        return
    # مذاکرهٔ subprotocol (noVNC معمولاً «binary» می‌خواهد)
    req_proto = (ws.headers.get("sec-websocket-protocol") or "").lower()
    chosen = None
    for p in ("binary", "base64"):
        if p in req_proto:
            chosen = p
            break
    await ws.accept(subprotocol=chosen)
    target = f"ws://127.0.0.1:{ws_port}/websockify"
    try:
        import websockets
    except Exception:
        await ws.close(code=1011, reason="کتابخانهٔ websockets نصب نیست")
        return
    remote_session.touch(name)
    try:
        kw = {"max_size": 64 * 1024 * 1024}
        if chosen:
            kw["subprotocols"] = [chosen]
        async with websockets.connect(target, **kw) as upstream:
            async def to_upstream():
                while True:
                    try:
                        msg = await ws.receive()
                    except WebSocketDisconnect:
                        return
                    except Exception:
                        return
                    if msg.get("type") == "websocket.disconnect":
                        return
                    if msg.get("text") is not None:
                        await upstream.send(msg["text"])
                    elif msg.get("bytes") is not None:
                        await upstream.send(msg["bytes"])
                    remote_session.touch(name)

            async def to_browser():
                while True:
                    try:
                        data = await upstream.recv()
                    except Exception:
                        return
                    if isinstance(data, str):
                        await ws.send_text(data)
                    else:
                        await ws.send_bytes(data)
                    remote_session.touch(name)

            await asyncio.gather(to_upstream(), to_browser())
    except Exception:
        pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
