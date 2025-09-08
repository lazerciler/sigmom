#!/usr/bin/env python3
# app/routers/panel.py
# Python 3.9
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.dependencies.auth import get_current_user
from app.database import get_db
from pathlib import Path

router = APIRouter()

# Proje köküne göre bağımsız: .../app/routers/panel.py → parents[1] = app/
TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/", response_class=HTMLResponse)
async def panel(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    if user:
        name = (user.get("name") or "").strip()
        email = user.get("email") or ""
        display_name = name if name else (email.split("@")[0] if email else "")
    else:
        display_name = "Ziyaretçi"
        email = None

    # Kullanıcı referral doğrulanmış mı?
    referral_verified = False
    if user:
        # CLAIMED kodu var mı?
        res = await db.execute(
            text(
                """
                SELECT 1
                FROM referral_codes
                WHERE used_by_user_id = :uid AND status = 'CLAIMED'
                LIMIT 1
                """
            ),
            {"uid": user["id"]},
        )
        referral_verified = res.first() is not None

    ctx = {
        "request": request,
        "user": user,
        "user_name": display_name,
        "referral_verified": referral_verified,
        "feed_url": None,
    }

    # Yerel scriptlerle sade CSP (yalnızca 'self')
    resp = templates.TemplateResponse("panel.html", ctx)
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "connect-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )
    return resp
