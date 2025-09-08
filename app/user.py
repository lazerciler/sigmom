#!/usr/bin/env python3
# app/crud/user.py
# Python 3.9

from __future__ import annotations
from typing import Optional, List
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import User
import os
import re
from typing import Set

GMAIL_DOMAINS = {"gmail.com", "googlemail.com"}


def normalize_email(email: str) -> str:
    s = (email or "").strip().lower()
    if "@" not in s:
        return s
    local, _, domain = s.partition("@")
    if domain in GMAIL_DOMAINS:
        local = local.split("+", 1)[0].replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"


# --- Whitelist yükleme: app.config.settings + ENV fallback ---
def _split_emails(raw: Optional[str]):
    if not raw:
        return []
    return [x for x in re.split(r"[,;\s]+", raw) if x]


def _load_admin_whitelist() -> Set[str]:
    wl: Set[str] = set()
    try:
        # Pydantic Settings: .env'den gelir
        from app.config import settings

        src = getattr(settings, "ADMIN_EMAIL_WHITELIST", None)
        if isinstance(src, (list, tuple, set)):
            wl |= {normalize_email(e) for e in src if e}
        elif isinstance(src, str):
            wl |= {normalize_email(e) for e in _split_emails(src)}
    except Exception:
        pass
    # OS env override (opsiyonel)
    env = os.getenv("ADMIN_EMAIL_WHITELIST") or os.getenv("ADMIN_EMAILS")
    if env:
        wl |= {normalize_email(e) for e in _split_emails(env)}
    return wl


_ADMIN_WL: Set[str] = _load_admin_whitelist()


def is_email_whitelisted(email: str) -> bool:
    # Güvenli varsayılan: whitelist boşsa terfi/demode izni verme
    return bool(_ADMIN_WL) and normalize_email(email) in _ADMIN_WL


async def get_by_sub(db: AsyncSession, sub: str) -> Optional[User]:
    if not sub:
        return None
    res = await db.execute(select(User).where(User.google_sub == sub))
    return res.scalar_one_or_none()


async def get_by_email(db: AsyncSession, email: str) -> Optional[User]:
    if not email:
        return None
    res = await db.execute(select(User).where(User.email == email))
    return res.scalar_one_or_none()


async def create_or_update_on_google_login(
    db: AsyncSession,
    *,
    sub: Optional[str],
    email: str,
    name: Optional[str],
    picture_url: Optional[str],
) -> User:
    """
    Google OAuth dönüşünde kullanıcıyı oluştur/güncelle.
    NOT: 'role' alanını ASLA ezmeyiz (admin'i koru).
    """
    user = await get_by_sub(db, sub) if sub else None
    if not user:
        user = await get_by_email(db, email)

    if user:
        # Sadece kimlik bilgisi niteliğindeki alanlar güncellenir
        if email:
            user.email = email
        if sub:
            user.google_sub = sub
        if name:
            user.name = name
        if picture_url:
            user.avatar_url = picture_url
        user.updated_at = datetime.utcnow()
        await db.flush()
        return user

    user = User(
        email=email,
        google_sub=sub,
        name=name,
        avatar_url=picture_url,
        # role='user' -> server_default ile 'user'
        created_at=datetime.utcnow(),
    )
    db.add(user)
    await db.flush()
    return user


async def set_role(db: AsyncSession, user_id: int, role: str) -> Optional[User]:
    role = (role or "").lower()
    if role not in {"user", "admin"}:
        return None
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        return None
    user.role = role
    user.updated_at = datetime.utcnow()
    await db.flush()
    return user


async def list_users(db: AsyncSession, limit: int = 200, offset: int = 0) -> List[User]:
    res = await db.execute(select(User).order_by(User.id).offset(offset).limit(limit))
    return list(res.scalars().all())
