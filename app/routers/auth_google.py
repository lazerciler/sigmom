#!/usr/bin/env python3
# app/routers/auth_google.py
# Python 3.9

import time
import secrets
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from itsdangerous import URLSafeSerializer, BadSignature  # stateless state

from app.config import settings
from app.database import get_db
from app.user import create_or_update_on_google_login

router = APIRouter(prefix="/auth/google", tags=["auth"])

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
    db: AsyncSession = Depends(get_db),
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
        raise HTTPException(400, "Email required.")

    # DB upsert: mevcut mimarideki fonksiyonu kullan
    user = await create_or_update_on_google_login(
        db, sub=sub, email=email, name=name, picture_url=picture
    )
    await db.commit()
    # Eski yöntem
    # # Session: projede kullanılan anahtarla hizala
    # request.session["user_id"] = int(user.id)

    # Yeni yöntem
    # Session: IdP (Google) claim'lerini oturuma koy
    # (isteğe bağlı sabitleme: önce oturumu temizle)
    request.session.clear()
    request.session.update(
        {
            "user_id": int(user.id),  # DB user id
            "email": email,  # Google UserInfo'dan
            "email_verified": bool(info.get("email_verified", True)),
            "sub": sub,  # Google unique subject
        }
    )
    return RedirectResponse("/", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)
