#!/usr/bin/env python3
# app/routers/admin_test.py
# Python 3.9
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.dependencies.auth import get_current_user, require_admin_db
from app.exchanges.binance_futures_testnet.settings import (
    POSITION_MODE as CFG_MODE,
    EXCHANGE_NAME,
)
from app.exchanges.binance_futures_testnet.utils import get_position_mode
from pathlib import Path

router = APIRouter(
    prefix="/admin/test",
    tags=["admin-test"],
    # Tüm endpoint'ler admin korumalı
    dependencies=[Depends(require_admin_db)],
)

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"  # app/templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


@router.get("/status")
async def admin_test_status(current_user=Depends(get_current_user)):
    # require_admin_db(current_user)
    ex = EXCHANGE_NAME
    chk = await get_position_mode()
    return {
        "exchange": ex,
        "config_mode": CFG_MODE,
        "exchange_mode": chk.get("mode") if chk.get("success") else None,
        "success": chk.get("success", False),
        "raw": chk.get("data", chk.get("message")),
    }


@router.get("", response_class=HTMLResponse)
async def admin_test_page(request: Request, current_user=Depends(get_current_user)):
    # Merkezde tanımlı adminlere izin ver (aksi halde 403)
    # require_admin_db(current_user)  # aynı koruma referral panelinde de var
    return templates.TemplateResponse(
        "admin_test.html",
        {"request": request, "current_user": current_user},
        headers={
            "Content-Security-Policy": CSP,
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "same-origin",
        },
    )
