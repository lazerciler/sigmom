#!/usr/bin/env python3
# app/routers/admin_settings.py
# Python 3.9

from __future__ import annotations
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.user import list_users, set_role, normalize_email, is_email_whitelisted
from app.dependencies.auth import require_admin_db
from pathlib import Path

router = APIRouter(
    prefix="/admin/settings",
    tags=["admin-settings"],
    # Tüm endpoint'ler admin korumalı
    dependencies=[Depends(require_admin_db)],
)

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"  # app/templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("", response_class=HTMLResponse)
async def admin_settings_page(
    request: Request,
    me=Depends(require_admin_db),
    db: AsyncSession = Depends(get_db),
):
    users = await list_users(db, limit=500)
    me_id = int(me["id"])
    # whitelist'i template'e gönder
    from app.user import normalize_email

    try:
        from app.config import settings

        wl_src = settings.ADMIN_EMAIL_WHITELIST
        if isinstance(wl_src, str):
            import re

            wl_list = [normalize_email(x) for x in re.split(r"[,;\s]+", wl_src) if x]
        else:
            wl_list = [normalize_email(x) for x in (wl_src or [])]
    except Exception:
        wl_list = []
    return templates.TemplateResponse(
        "admin_settings.html",
        {
            "request": request,
            "me": me,
            "users": users,
            "me_id": me_id,
            "admin_wl": wl_list,
        },
    )


@router.post("/role")
async def admin_set_role(
    user_id: int = Form(...),
    role: str = Form(...),
    me=Depends(require_admin_db),
    db: AsyncSession = Depends(get_db),
):
    # 1) Kendini düşürme blok
    if role == "user" and int(user_id) == int(me["id"]):
        raise HTTPException(status_code=400, detail="Kendinizi düşüremezsiniz")

    # 2) Whitelisted admin düşürülemez
    if role == "user":
        target_email = (
            await db.execute(
                text("SELECT email FROM users WHERE id=:id"), {"id": user_id}
            )
        ).scalar()
        if target_email and is_email_whitelisted(normalize_email(target_email)):
            raise HTTPException(status_code=400, detail="Whitelisted admin düşürülemez")

    u = await set_role(db, user_id, role)
    if not u:
        raise HTTPException(status_code=400, detail="Invalid user or role")
    await db.commit()
    return {"ok": True, "user_id": u.id, "role": u.role}
