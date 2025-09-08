#!/usr/bin/env python3
# app/dependencies/auth.py
# Python 3.9

from __future__ import annotations
from typing import Optional, Dict, Any
import os
import re

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlalchemy import select

from app.database import get_db
from app.models import User


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> Optional[Dict[str, Any]]:
    uid = request.session.get("user_id")
    if not uid:
        return None
    res = await db.execute(select(User).where(User.id == uid))
    u = res.scalar_one_or_none()
    if not u:
        return None
    return {
        "id": u.id,
        "email": u.email,
        "role": u.role,
        "name": u.name,
        "avatar_url": u.avatar_url,
    }


# --- IdP (Google) oturum claim'leri için hafif yardımcı ---
def _normalize_email(email: str) -> str:
    s = (email or "").strip().lower()
    if not s or "@" not in s:
        return s
    local, _, domain = s.partition("@")
    if domain in {"gmail.com", "googlemail.com"}:
        local = local.split("+", 1)[0].replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"


def _split_emails(raw: Optional[str]):
    if not raw:
        return []
    return [x for x in re.split(r"[,;\s]+", raw) if x]


def _load_admin_whitelist() -> set:
    wl = set()
    try:
        # 1) config.Settings içinden oku (Pydantic .env dosyana göre dolduruldu)
        from app.config import settings

        src = settings.ADMIN_EMAIL_WHITELIST  # Genellikle CSV string
        if isinstance(src, (list, tuple, set)):
            wl |= {_normalize_email(e) for e in src if e}
        elif isinstance(src, str):
            wl |= {_normalize_email(e) for e in _split_emails(src)}
    except Exception:
        pass
    # 2) (opsiyonel) OS env override
    env = os.getenv("ADMIN_EMAIL_WHITELIST") or os.getenv("ADMIN_EMAILS")
    if env:
        wl |= {_normalize_email(e) for e in _split_emails(env)}
    return wl


_ADMIN_WL = _load_admin_whitelist()


def _is_email_whitelisted(email: str) -> bool:
    # Güvenli varsayılan: whitelist boşsa admin verilmez
    return bool(_ADMIN_WL) and _normalize_email(email) in _ADMIN_WL


async def get_current_session(request: Request) -> Optional[Dict[str, Any]]:
    """Oturumdaki IdP claim'lerini döndürür (DB'den değil)."""
    uid = request.session.get("user_id")
    email = request.session.get("email")
    email_verified = request.session.get("email_verified", True)
    sub = request.session.get("sub")
    if not uid or not email:
        return None
    return {"id": uid, "email": email, "email_verified": email_verified, "sub": sub}


async def require_user(user=Depends(get_current_user)):
    if user:
        return user
    # İstersen 401 de dönebilirsin
    raise HTTPException(status_code=404)


# Aşağıdaki require_member_db asil üyelik gerektiren API’lerde/end-point’lerde kullanılabilir
# Örnekler:
# @router.get("/hesap-ozetim", dependencies=[Depends(require_member_db)])
# async def my_summary(...):
# vaya router'lar: router = APIRouter(dependencies=[Depends(require_member_db)])
async def require_member_db(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        raise HTTPException(401)
    row = (
        await db.execute(
            text(
                """
                SELECT 1 FROM referral_codes
                 WHERE used_by_user_id=:uid AND status='CLAIMED' LIMIT 1
            """
            ),
            {"uid": user["id"]},
        )
    ).first()
    if not row:
        raise HTTPException(403, detail="Asil üyelik gerekli")
    return user


async def require_admin_db(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    SERTLEŞTİRİLMİŞ admin guard:
    1) Admin whitelisti: yalnız oturumdaki (IdP) email ile kontrol
    2) email_verified opsiyonel kontrolü
    3) DB'de role='admin' olmalı (DB tek başına yetki vermez; kısıtlar)
    """
    sess = await get_current_session(request)
    if not sess:
        raise HTTPException(status_code=401)
    email_norm = _normalize_email(sess["email"])
    if not _is_email_whitelisted(email_norm):
        # Kaynağı gizlemek için 404
        raise HTTPException(status_code=404)
    if not sess.get("email_verified", True):
        raise HTTPException(status_code=403, detail="Email not verified")
    role = (await db.execute(select(User.role).where(User.id == sess["id"]))).scalar()
    if role != "admin":
        # Admin rolünü DB de doğrulasın (DB tek başına admin yapamaz)
        raise HTTPException(status_code=404)
    return {"id": sess["id"], "email": sess["email"], "role": "admin"}
