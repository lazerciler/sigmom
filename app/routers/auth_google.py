#!/usr/bin/env python3
# app/routers/auth_google.py
# Python 3.9

import time
import secrets
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from itsdangerous import URLSafeSerializer, BadSignature  # stateless state

from app.config import settings
from app.database import async_session

router = APIRouter()

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
OAUTH_SCOPE = "openid email profile"

# STATE artık session'a yazılmıyor; gizli anahtarla imzalanıyor → reload/sekme sorunları biter
serializer = URLSafeSerializer(settings.SESSION_SECRET, salt="oauth-state")


@router.get("/login")
async def login(request: Request):
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(500, "Google OAuth env eksik.")

    payload = {"nonce": secrets.token_urlsafe(8), "ts": int(time.time())}
    state = serializer.dumps(payload)

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": OAUTH_SCOPE,
        "access_type": "online",
        "include_granted_scopes": "true",
        "state": state,
        "prompt": "consent",
    }
    return RedirectResponse(f"{AUTH_URL}?{urlencode(params)}", status_code=302)


@router.get("/callback")
async def callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    if error:
        raise HTTPException(400, f"Google error: {error}")
    if not code or not state:
        raise HTTPException(400, "State/code eksik.")

    # İmzayı doğrula ve süreyi kontrol et (5 dk)
    try:
        data = serializer.loads(state)
        ts = int(data.get("ts", 0))
        if time.time() - ts > 300:
            raise HTTPException(400, "State süresi doldu.")
    except BadSignature:
        raise HTTPException(400, "State imzası geçersiz.")

    # Token + userinfo
    async with httpx.AsyncClient(timeout=15.0) as client:
        token_res = await client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token_res.raise_for_status()
        tokens = token_res.json()
        access_token = tokens.get("access_token")

        ui = await client.get(
            USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        ui.raise_for_status()
        info = ui.json()

    email = info.get("email")
    sub = info.get("sub")
    name = info.get("name") or ""
    picture = info.get("picture") or ""
    if not email:
        raise HTTPException(400, "Email alınamadı.")

    # DB: async upsert (id,email,name,avatar_url)
    async with async_session() as db:
        row = (
            await db.execute(text("SELECT id FROM users WHERE email=:e"), {"e": email})
        ).first()
        if row:
            uid = row[0]
            await db.execute(
                text(
                    """UPDATE users
                        SET google_sub=:s, name=:n, avatar_url=:p, updated_at=NOW()
                        WHERE id=:id"""
                ),
                {"s": sub, "n": name, "p": picture, "id": uid},
            )
        else:
            ins = await db.execute(
                text(
                    """INSERT INTO users (email, name, google_sub, avatar_url, created_at)
                        VALUES (:e, :n, :s, :p, NOW())"""
                ),
                {"e": email, "n": name, "s": sub, "p": picture},
            )
            uid = ins.lastrowid
        await db.commit()

    request.session["uid"] = int(uid)  # sadece uid'yi session'a yazıyoruz
    return RedirectResponse("/", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)
