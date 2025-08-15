#!/usr/bin/env python3
# app/dependencies/auth.py
# Python 3.9
from fastapi import Request, HTTPException
from sqlalchemy import text

from app.database import async_session
from app.config import settings

# .env → ADMIN_EMAILS=admin1@mail.com,admin2@mail.com
ADMIN_EMAILS = set((getattr(settings, "ADMIN_EMAILS", "") or "").split(","))


async def get_current_user(request: Request):
    """Giriş ZORUNLU: session.uid yoksa 401 atar; DB’den id,email,name çeker."""
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Giriş yapmalısınız.")
    async with async_session() as db:
        row = (
            await db.execute(
                text("SELECT id, email, name FROM users WHERE id=:id"),
                {"id": uid},
            )
        ).first()
        if not row:
            raise HTTPException(status_code=401, detail="Kullanıcı bulunamadı.")
        first_name = (row[2] or "").strip().split(" ")[0].capitalize()
        return {"id": row[0], "email": row[1], "name": first_name}


async def get_current_user_opt(request: Request):
    """Giriş OPSİYONEL: yoksa None döner, 401 atmaz."""
    uid = request.session.get("uid")
    if not uid:
        return None
    async with async_session() as db:
        row = (
            await db.execute(
                text("SELECT id, email, name FROM users WHERE id=:id"),
                {"id": uid},
            )
        ).first()
        if not row:
            return None
        first_name = (row[2] or "").strip().split(" ")[0].capitalize()
        return {"id": row[0], "email": row[1], "name": first_name}


def require_admin(user):
    """Admin kontrolü: yalnızca ADMIN_EMAILS whitelist."""
    if user and user.get("email") in ADMIN_EMAILS:
        return user
    raise HTTPException(status_code=404)
