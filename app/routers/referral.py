#!/usr/bin/env python3
# app/routers/referral.py
# Python 3.9
import bcrypt
import re
from pydantic import BaseModel, validator
from typing import ClassVar, Pattern
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text

from app.database import async_session
from app.dependencies.auth import get_current_user_opt

router = APIRouter()


class VerifyIn(BaseModel):
    code: str

    # Field değil, sınıf sabiti:
    code_re: ClassVar[Pattern[str]] = re.compile(r'^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$')

    @validator("code", pre=True)
    def normalize_and_validate(cls, v: str) -> str:
        v = (v or "").strip().upper()
        if not cls.code_re.fullmatch(v):
            raise ValueError("Kod formatı geçersiz. Örn: AB12-CDEF-3456")
        return v


@router.post("/verify")
async def verify_referral(
    body: VerifyIn,
    _request: Request,
    user=Depends(get_current_user_opt),
):
    if not user:
        raise HTTPException(401, "Giriş gerekli.")

    # Pydantic validator normalize etti (UPPER + 4-4-4 kontrolü)
    code = body.code
    email_norm = (user["email"] or "").strip().lower()
    now = datetime.utcnow()

    async with async_session() as db:
        async with db.begin():
            # 0) idempotent
            already = await db.execute(text("""
                SELECT 1
                FROM referral_codes
                WHERE used_by_user_id = :uid AND status = 'CLAIMED'
                LIMIT 1
            """), {"uid": user["id"]})
            if already.first():
                return {"ok": True}

            # 1) Adaylar: SADECE bu e-postaya tahsisli + süresi geçmemiş
            res = await db.execute(text("""
                SELECT id, code_hash
                FROM referral_codes
                WHERE status = 'RESERVED'
                  AND LOWER(TRIM(email_reserved)) = :email
                  AND (expires_at IS NULL OR expires_at > :now)
            """), {"email": email_norm, "now": now})
            rows = res.all()

            # # --- GEÇİCİ TEŞHİS ---
            # print("verify email_norm:", email_norm)
            # print("verify candidates:", [r[0] for r in rows])

            # 2) Bcrypt ile plaintext eşleşmesi
            bcrypt_re = re.compile(r'^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$')
            match_id = None
            raw = code.encode("utf-8")
            for rid, chash in rows:
                if not isinstance(chash, str) or not bcrypt_re.match(chash):
                    continue
                if bcrypt.checkpw(raw, chash.encode("utf-8")):
                    match_id = rid
                    print("verify matched id:", match_id)  # --- GEÇİCİ TEŞHİS ---
                    break

            if not match_id:
                raise HTTPException(400, "Kod bulunamadı veya size tahsisli/aktif değil.")

            # 3) Koşullu CLAIM (Unlimited: expires_at=NULL)
            result = await db.execute(text("""
                UPDATE referral_codes
                SET status='CLAIMED',
                    used_by_user_id=:uid,
                    used_at=:now,
                    expires_at=NULL
                WHERE id=:rid
                  AND status='RESERVED'
                  AND LOWER(TRIM(email_reserved)) = :email
                  AND (expires_at IS NULL OR expires_at > :now)
            """), {"uid": user["id"], "email": email_norm, "now": now, "rid": match_id})

            print("verify update rowcount:", result.rowcount)  # --- GEÇİCİ TEŞHİS ---

            if result.rowcount == 0:
                raise HTTPException(409, "Kod artık uygun değil. Lütfen tekrar deneyin.")

            # 4) Kullanıcıyı işaretle
            await db.execute(
                text("UPDATE users SET referral_verified_at=:now, updated_at=:now WHERE id=:uid"),
                {"now": now, "uid": user["id"]},
            )

    return {"ok": True}
