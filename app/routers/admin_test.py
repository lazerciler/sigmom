#!/usr/bin/env python3
# app/routers/admin_test.py
# Python 3.9

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.dependencies.auth import get_current_user, require_admin_db
from app.config import settings as app_settings
import importlib
from typing import Optional
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


def _resolve_exchange(name: Optional[str]) -> str:
    """Parametre yoksa DEFAULT_EXCHANGE'e düş."""
    ex = (
        name or getattr(app_settings, "DEFAULT_EXCHANGE", "binance_futures_testnet")
    ).strip()
    return ex


def _load_exchange_utils(ex: str):
    return importlib.import_module(f"app.exchanges.{ex}.utils")


def _load_exchange_settings_or_none(ex: str):
    try:
        return importlib.import_module(f"app.exchanges.{ex}.settings")
    except ModuleNotFoundError:
        return None


@router.get("/status")
async def admin_test_status(exchange: str = Query(app_settings.DEFAULT_EXCHANGE)):
    ex = exchange.strip()
    utils = importlib.import_module(f"app.exchanges.{ex}.utils")
    ex_settings = importlib.import_module(f"app.exchanges.{ex}.settings")
    get_mode = getattr(utils, "get_position_mode")
    chk = await get_mode()
    return {
        "exchange": ex,
        "config_mode": getattr(ex_settings, "POSITION_MODE", "one_way"),
        "exchange_mode": chk.get("mode") if chk.get("success") else None,
        "success": chk.get("success", False),
        "raw": chk.get("data", chk.get("message")),
    }


@router.get("", response_class=HTMLResponse)
async def admin_test_page(
    request: Request,
    exchange: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
):
    # Merkezde tanımlı adminlere izin ver (aksi halde 403)
    # require_admin_db(current_user)  # aynı koruma referral panelinde de var

    # return templates.TemplateResponse(
    ex = _resolve_exchange(exchange)
    return templates.TemplateResponse(
        "admin_test.html",
        # {"request": request, "current_user": current_user},
        {"request": request, "current_user": current_user, "exchange": ex},
        headers={
            "Content-Security-Policy": CSP,
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "same-origin",
        },
    )
