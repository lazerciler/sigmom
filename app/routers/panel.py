#!/usr/bin/env python3
# app/routers/panel.py
# Python 3.9
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.dependencies.auth import get_current_user_opt
from app.database import async_session
from app.services.referrals import get_dynamic_capacity
from sqlalchemy import text

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def panel(request: Request, user=Depends(get_current_user_opt)):
    if user:
        name = (user.get("name") or "").strip()
        email = (user.get("email") or "")
        display_name = name if name else (email.split("@")[0] if email else "")
    else:
        display_name = "Ziyaretçi"
        email = None

    async with async_session() as db:
        capacity_info = await get_dynamic_capacity(db, email)
        capacity_full = capacity_info["free_total_for_user"] <= 0

        # ⇩⇩ YENİ: Kullanıcı referral doğrulanmış mı?
        referral_verified = False
        if user:
            # CLAIMED kodu var mı?
            row = await db.execute(text("""
                SELECT 1
                FROM referral_codes
                WHERE used_by_user_id = :uid AND status = 'CLAIMED'
                LIMIT 1
            """), {"uid": user["id"]})
            referral_verified = row.first() is not None

    ctx = {
        "request": request,
        "user": user,
        "user_name": display_name,
        "referral_verified": referral_verified,
        "capacity_full": capacity_full,
        "feed_url": None,
    }

    return templates.TemplateResponse("panel.html", ctx)
