#!/usr/bin/env python3
# app/routers/referral.py
# Python 3.9
from __future__ import annotations
import re
import bcrypt
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Body, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/referral", tags=["referral"])
CODE_RE = re.compile(r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")


@router.post("/verify")
async def verify_referral(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: Optional[Dict[str, Any]] = Depends(get_current_user),
    code_form: Optional[str] = Form(None),
    payload: Optional[Dict[str, Any]] = Body(None),
):
    if not user:
        raise HTTPException(status_code=401, detail="Giriş gerekli")

    # 1) Kodu mümkün olan her kaynaktan oku (JSON → Form → raw json → raw form)
    code = (code_form or "").strip()
    if not code and payload and "code" in payload:
        v = payload.get("code")
        code = (v if v is not None else "").strip()
    if not code:
        # Fallback: bazı ortamlarda Body/Form çözümlemesi başarısız olabiliyor
        try:
            j = await request.json()
            v = j.get("code") if isinstance(j, dict) else None
            code = (v or "").strip()
        except Exception:
            pass
    if not code:
        try:
            frm = await request.form()
            code = (frm.get("code") or "").strip()
        except Exception:
            pass

    code = code.upper()
    if not code:
        raise HTTPException(status_code=400, detail="Code required")
    if not CODE_RE.fullmatch(code):
        raise HTTPException(
            status_code=400, detail="Kod formatı geçersiz. Örn: AB12-CDEF-3456"
        )

    # 2) İdempotent: zaten doğrulanmışsa OK
    already = (
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
    if already:
        return {"ok": True, "status": "CLAIMED", "already": True}

    email = (user.get("email") or "").strip().lower()
    raw = code.encode("utf-8")

    # 3) SADECE bu kullanıcıya RESERVED edilmiş ve aktif olan kodlar
    rows = (
        await db.execute(
            text(
                """
        SELECT id, code_hash
          FROM referral_codes
         WHERE status='RESERVED'
           AND LOWER(TRIM(email_reserved))=:email
           AND (expires_at IS NULL OR expires_at > NOW())
    """
            ),
            {"email": email},
        )
    ).all()

    match_id = None
    for rid, chash in rows:
        try:
            if isinstance(chash, str) and bcrypt.checkpw(raw, chash.encode("utf-8")):
                match_id = rid
                break
        except Exception:
            pass

    if match_id is None:
        # Kural gereği AVAILABLE’dan claim YOK
        raise HTTPException(
            status_code=400, detail="Kod size tahsisli değil veya süresi dolmuş"
        )

    # 4) Atomik claim
    upd = await db.execute(
        text(
            """
        UPDATE referral_codes
           SET used_by_user_id=:uid,
               status='CLAIMED',
               used_at=NOW(),
               email_reserved=NULL,
               expires_at=NULL
         WHERE id=:rid
           AND status='RESERVED'
           AND LOWER(TRIM(email_reserved))=:email
           AND (expires_at IS NULL OR expires_at > NOW())
    """
        ),
        {"uid": user["id"], "rid": match_id, "email": email},
    )
    if upd.rowcount != 1:
        raise HTTPException(status_code=409, detail="Kod artık uygun değil")

    await db.execute(
        text(
            """
        UPDATE users
           SET referral_verified_at = COALESCE(referral_verified_at, NOW()),
               updated_at = NOW()
         WHERE id=:uid
    """
        ),
        {"uid": user["id"]},
    )
    await db.commit()
    return {"ok": True, "status": "CLAIMED"}
