# -*- coding: utf-8 -*-
"""ساخت اپلیکیشن FastAPI سرور: احراز هویت + هستهٔ مارکتینگ + نشست ریموت.

تفاوت با نسخهٔ ویندوزی: قبل از پنل یک صفحهٔ لاگین می‌آید؛ پروفایل‌ها به‌جای
پنجرهٔ بومی، از طریق نشست ریموت (noVNC) مدیریت می‌شوند.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# مسیرهای پیش از لاگین (بدون نیاز به احراز)
_PUBLIC_PREFIXES = (
    "/login", "/api/auth", "/logo.png", "/favicon.ico", "/novnc/",
)

_LOGIN_HTML = Path(__file__).parent / "static" / "login.html"


class LoginReq(BaseModel):
    username: str = ""
    password: str = ""


class ChangePwReq(BaseModel):
    current: str = ""
    new: str = ""


def _auth_checker():
    from .auth import auth
    return auth


def build_app(core_app: Optional[FastAPI] = None) -> FastAPI:
    """می‌سازد app را (احراز + ریموت روی هسته)."""
    if core_app is None:
        from marketing_divar.web.server import app as core_app
    from .auth import auth
    from . import remote_router

    def checker(token: Optional[str]) -> bool:
        return auth.get_session(token) is not None

    remote_router.configure(
        os.environ.get("DIVAR_ACCOUNTS_DIR", "data/accounts"), checker)

    # -------------------------------------------------------- احراز هویت --
    @core_app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        token = request.cookies.get("divar_session")
        authed = auth.get_session(token) is not None
        path = request.url.path
        if not authed and not _is_public(path):
            if path.startswith("/api/") or path.startswith("/remote/"):
                return JSONResponse({"detail": "احراز هویت لازم است"}, status_code=401)
            return RedirectResponse("/login", status_code=302)
        return await call_next(request)

    # ------------------------------------------------------ مسیرهای ورود --
    @core_app.post("/api/auth/login")
    def api_login(req: LoginReq):
        r = auth.authenticate(req.username, req.password)
        if not r.get("ok"):
            return JSONResponse(r, status_code=401)
        resp = JSONResponse(r)
        resp.set_cookie(
            "divar_session", r["token"], max_age=12 * 3600,
            httponly=True, samesite="lax",
            secure=os.environ.get("DIVAR_SERVER_SECURE", "") == "1")
        return resp

    @core_app.post("/api/auth/logout")
    def api_logout(request: Request):
        auth.logout(request.cookies.get("divar_session"))
        resp = JSONResponse({"ok": True})
        resp.delete_cookie("divar_session")
        return resp

    @core_app.post("/api/auth/change-password")
    def api_change_password(req: ChangePwReq, request: Request):
        r = auth.change_password(request.cookies.get("divar_session"),
                                 req.current, req.new)
        if not r.get("ok"):
            return JSONResponse(r, status_code=400)
        return r

    @core_app.get("/api/auth/status")
    def api_status(request: Request):
        sess = auth.get_session(request.cookies.get("divar_session"))
        if not sess:
            return JSONResponse({"authenticated": False}, status_code=401)
        return {"authenticated": True, "username": sess["user"],
                "must_change_password": auth.must_change_password(
                    request.cookies.get("divar_session"))}

    @core_app.get("/login", response_class=HTMLResponse)
    def login_page():
        return _LOGIN_HTML.read_text(encoding="utf-8")

    # --------------------------------------- پنل سرور (index اختصاصی) --
    _SERVER_INDEX = Path(__file__).parent / "static" / "index.html"

    def _serve_server_index():
        if _SERVER_INDEX.exists():
            return HTMLResponse(_SERVER_INDEX.read_text(encoding="utf-8"))
        from marketing_divar.web.server import _STATIC
        return HTMLResponse((_STATIC / "index.html").read_text(encoding="utf-8"))

    # جایگزینی مسیر "/" هسته با نسخهٔ سرور (بدون تغییر فایل ویندوز)
    core_app.routes[:] = [r for r in core_app.routes
                          if not (getattr(r, "path", "") == "/")]

    @core_app.get("/", response_class=HTMLResponse)
    def index():
        return _serve_server_index()

    # ---------------------------------------------------- noVNC استاتیک --
    _mount_novnc(core_app)

    # ---------------------------------------------------- نشست ریموت ----
    core_app.include_router(remote_router.router)

    return core_app


def _mount_novnc(app: FastAPI) -> None:
    novnc = os.environ.get("DIVAR_NOVNC_DIR", "")
    for cand in (novnc, "/opt/divar-server/novnc", "/opt/divar-server/noVNC"):
        if cand and Path(cand).is_dir():
            try:
                app.mount("/novnc", StaticFiles(directory=cand, html=True),
                          name="novnc")
                return
            except Exception:
                continue


def _is_public(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in _PUBLIC_PREFIXES)
