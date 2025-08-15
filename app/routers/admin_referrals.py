#!/usr/bin/env python3
# app/routers/admin_referrals.py
# Python 3.9
from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from io import StringIO, BytesIO
from datetime import datetime, timedelta

import bcrypt
import secrets
import string
import pyzipper

from app.database import async_session
from app.dependencies.auth import get_current_user, require_admin

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(prefix="/admin/referrals", tags=["admin-referrals"])

ALPH = string.ascii_uppercase + string.digits


def _gen_plain():
    return "-".join("".join(secrets.choice(ALPH) for _ in range(4)) for _ in range(3))


async def _fetch_panel_data():
    async with async_session() as db:
        # Kullanıcı listesi: claimed + reserved görünümü
        users = (
            await db.execute(
                text(
                    """
            SELECT
              u.id,
              u.email,
              (
                SELECT rc.id
                FROM referral_codes rc
                WHERE rc.used_by_user_id = u.id AND rc.status='CLAIMED'
                ORDER BY rc.used_at DESC LIMIT 1
              ) AS referral_code_id,  -- mevcut şablon ismiyle uyumlu tutuyorum
              (
                SELECT rc2.id
                FROM referral_codes rc2
                WHERE rc2.status='RESERVED'
                  AND rc2.email_reserved = u.email
                  AND (rc2.expires_at IS NULL OR rc2.expires_at > NOW())
                ORDER BY rc2.id DESC LIMIT 1
              ) AS reserved_code_id,
              (
                SELECT rc3.expires_at
                FROM referral_codes rc3
                WHERE rc3.status='RESERVED'
                  AND rc3.email_reserved = u.email
                  AND (rc3.expires_at IS NULL OR rc3.expires_at > NOW())
                ORDER BY rc3.id DESC LIMIT 1
              ) AS reserved_expires_at,
              u.created_at
            FROM users u
            ORDER BY u.created_at DESC
            LIMIT 200
        """
                )
            )
        ).all()

        # Kod listesi: kime rezerve edildiğini göstermek için user join
        codes = (
            await db.execute(
                text(
                    """
            SELECT
              rc.id,
              rc.status,
              rc.email_reserved,
              rc.expires_at,
              u.id   AS reserved_user_id,
              u.name AS reserved_user_name
            FROM referral_codes rc
            LEFT JOIN users u
              ON u.email = rc.email_reserved
            ORDER BY rc.id DESC
            LIMIT 300
        """
                )
            )
        ).all()

        # Free pool: SADECE AVAILABLE
        free_codes = (
            await db.execute(
                text(
                    """
            SELECT id
            FROM referral_codes
            WHERE status='AVAILABLE'
            ORDER BY id DESC
            LIMIT 50
        """
                )
            )
        ).all()

    return users, codes, free_codes


@router.get("", response_class=HTMLResponse)
async def panel(request: Request, current_user=Depends(get_current_user)):
    require_admin(current_user)
    users, codes, free_codes = await _fetch_panel_data()
    return templates.TemplateResponse(
        "admin_referrals.html",
        {
            "request": request,
            "users": users,
            "codes": codes,
            "free_codes": free_codes,
            "current_user": current_user,
        },
    )


# Expiry temizliği için manuel buton/endpoint'i (hemen çalıştır-gör)
@router.post("/expire_cleanup", response_class=HTMLResponse)
async def expire_cleanup(
    request: Request,
    current_user=Depends(get_current_user),
):
    require_admin(current_user)
    async with async_session() as db:
        async with db.begin():
            # result = await db.execute(
            await db.execute(
                text(
                    """
                UPDATE referral_codes
                SET status='AVAILABLE',
                    email_reserved=NULL,
                    expires_at=NULL
                WHERE status='RESERVED'
                  AND email_reserved IS NOT NULL
                  AND expires_at IS NOT NULL
                  AND expires_at < NOW()
            """
                )
            )
        # result.rowcount ile kaç satırın temizlendiğini görmek istersen loglayabilirsin
    return await panel(request, current_user)


@router.post("/assign", response_class=HTMLResponse)
async def assign(
    request: Request,
    email: str = Form(...),
    referral_id: int = Form(...),  # ikisi de ZORUNLU
    plain_code: str = Form(...),  # ikisi de ZORUNLU
    current_user=Depends(get_current_user),
):
    require_admin(current_user)

    email = (email or "").strip().lower()
    if not email:
        raise HTTPException(400, "email gerekli")

    now = datetime.utcnow()
    # Rezerv süresi (istersen ayarlanabilir yapabilirsin)
    DEFAULT_RESERVE_DAYS = 14
    exp_new = now + timedelta(days=DEFAULT_RESERVE_DAYS)

    async with async_session() as db:
        async with db.begin():
            # Kullanıcıyı al/oluştur (kilitle)
            row = (
                await db.execute(
                    text("SELECT id FROM users WHERE email=:e FOR UPDATE"),
                    {"e": email},
                )
            ).first()
            if row:
                uid = row[0]
                await db.execute(
                    text("UPDATE users SET updated_at=:t WHERE id=:id"),
                    {"t": now, "id": uid},
                )
            else:
                await db.execute(
                    text(
                        """
                        INSERT INTO users (email, is_active, created_at, updated_at)
                        VALUES (:e, 1, :t, :t)
                    """
                    ),
                    {"e": email, "t": now},
                )
                uid = (await db.execute(text("SELECT LAST_INSERT_ID()"))).first()[0]

            # Seçilen ID'yi kilitle ve hash'i getir
            row = (
                await db.execute(
                    text(
                        """
                SELECT id, code_hash, status, email_reserved, expires_at
                FROM referral_codes
                WHERE id=:rid
                FOR UPDATE
            """
                    ),
                    {"rid": referral_id},
                )
            ).first()
            if not row:
                raise HTTPException(400, "Kod bulunamadı.")

            _id, chash, status, email_res, exp = row

            # CLAIMED'e asla atama yapma
            if status == "CLAIMED":
                raise HTTPException(409, "Kod zaten CLAIMED.")

            # Düz kod → hash doğrulaması (ID ile EŞLEŞME zorunlu)
            raw = (plain_code or "").strip().upper().encode("utf-8")
            try:
                if not bcrypt.checkpw(raw, chash.encode("utf-8")):
                    raise HTTPException(400, "Düz kod bu ID ile eşleşmiyor.")
            except Exception:
                raise HTTPException(400, "Düz kod doğrulanamadı.")

            # Başka e-postaya tahsisli RESERVED ise engelle
            if (
                status == "RESERVED"
                and email_res
                and email_res.strip().lower() != email
            ):
                raise HTTPException(400, "Kod farklı bir e-posta için tahsisli.")

            # Süresi geçmiş RESERVED ise, admin rezerve edebiliriz → yeni süre yaz
            # AVAILABLE ise de yeni rezerv süresi yazacağız.

            # === RESERVE === (CLAIM YOK)
            await db.execute(
                text(
                    """
                UPDATE referral_codes
                SET status='RESERVED',
                    email_reserved=:email,
                    expires_at=:exp,
                    used_by_user_id=NULL,
                    used_at=NULL
                WHERE id=:rid AND status!='CLAIMED'
            """
                ),
                {"email": email, "exp": exp_new, "rid": referral_id},
            )

    # Paneli tazele
    return await panel(request, current_user)


@router.post("/unassign", response_class=HTMLResponse)
async def unassign(
    request: Request,
    user_id: int = Form(...),
    current_user=Depends(get_current_user),
):
    require_admin(current_user)
    now = datetime.utcnow()

    async with async_session() as db:
        async with db.begin():
            # 1) Kullanıcının son CLAIMED kodunu kilitleyerek al
            row = (
                await db.execute(
                    text(
                        """
                SELECT id FROM referral_codes
                WHERE used_by_user_id=:uid AND status='CLAIMED'
                ORDER BY used_at DESC
                LIMIT 1
                FOR UPDATE
            """
                    ),
                    {"uid": user_id},
                )
            ).first()
            if not row:
                raise HTTPException(400, "Kullanıcıda bağlı CLAIMED kod bulunamadı.")
            rid = row[0]

            # 2) Kodu tamamen boşa çıkar: AVAILABLE + tüm tahsis/claim alanlarını temizle
            result = await db.execute(
                text(
                    """
                UPDATE referral_codes
                SET status='AVAILABLE',
                    email_reserved=NULL,
                    expires_at=NULL,
                    used_by_user_id=NULL,
                    used_at=NULL
                WHERE id=:rid AND status='CLAIMED'
            """
                ),
                {"rid": rid},
            )

            if result.rowcount == 0:
                # Yarış durumu: kayıt CLAIMED değilse vs.
                raise HTTPException(
                    409, "Kod bu sırada değişti; lütfen tekrar deneyin."
                )

            # 3) Kullanıcıda başka CLAIMED yoksa, üyelik damgasını da temizle
            await db.execute(
                text(
                    """
                UPDATE users
                SET referral_verified_at=NULL, updated_at=:t
                WHERE id=:uid
                  AND NOT EXISTS (
                      SELECT 1 FROM referral_codes
                      WHERE used_by_user_id=:uid AND status='CLAIMED'
                  )
            """
                ),
                {"t": now, "uid": user_id},
            )

    return await panel(request, current_user)


@router.post("/generate", response_class=HTMLResponse)
async def generate(
    request: Request,
    count: int = Form(...),
    days: int = Form(14),  # NOT: AVAILABLE üretimde kullanılmıyor (rezerve yok)
    email_reserved: str = Form(None),  # NOT: AVAILABLE üretimde kullanılmıyor
    mode: str = Form("download"),  # "download" | "zip"
    zip_password: str = Form(None),  # ZIP için opsiyonel parola
    current_user=Depends(get_current_user),
):
    """
    Yeni referans kodları üretir ve plaintext CSV/ZIP olarak indirir.
    - Üretim mantığı: AVAILABLE (boş havuz)
      email_reserved = NULL, expires_at = NULL
    - Rezerve/expiry işleri /assign ile yönetilir.
    """
    admin = require_admin(current_user)
    count = max(1, min(100, int(count or 1)))
    days = max(
        1, min(180, int(days or 14))
    )  # AVAILABLE modda kullanılmıyor; parametre uyumluluğu için tutuldu
    email_reserved = (email_reserved or "").strip().lower() or None

    created = []

    async with async_session() as db:
        async with db.begin():
            for _ in range(count):
                plain = _gen_plain()
                code_hash = bcrypt.hashpw(
                    plain.strip().upper().encode("utf-8"), bcrypt.gensalt()
                ).decode("utf-8")

                # status sütununu yazmıyoruz → DEFAULT 'AVAILABLE'
                await db.execute(
                    text(
                        """
                        INSERT INTO referral_codes
                          (code_hash, email_reserved, tier, invited_by_admin_id, expires_at)
                        VALUES
                          (:h, NULL, 'default', :admin_id, NULL)
                    """
                    ),
                    {"h": code_hash, "admin_id": admin["id"]},
                )

                rid = (await db.execute(text("SELECT LAST_INSERT_ID()"))).first()[0]
                created.append({"id": rid, "plain": plain})

    # CSV içeriği (AVAILABLE üretimde email_reserved/expiry boş kalır)
    csv_buf = StringIO()
    csv_buf.write("sep=,\n")
    csv_buf.write("id,code,email_reserved,expires_at\n")
    for row in created:
        # email_reserved="", expires_at="" → boş alan
        csv_buf.write(f'{row["id"]},{row["plain"]},,\n')

    csv_bytes = csv_buf.getvalue().encode("utf-8")
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    if mode == "zip":
        # Şifreli ZIP (AES)
        zip_stream = BytesIO()
        with pyzipper.AESZipFile(
            zip_stream,
            "w",
            compression=pyzipper.ZIP_DEFLATED,
            encryption=pyzipper.WZ_AES,
        ) as zf:
            if zip_password:
                zf.setpassword(zip_password.encode("utf-8"))
            zf.writestr(f"referrals_plain_{ts}.csv", csv_bytes)
        zip_stream.seek(0)
        headers = {
            "Content-Disposition": f'attachment; filename="referrals_plain_{ts}.zip"',
            "X-Content-Type-Options": "nosniff",
        }
        return StreamingResponse(
            zip_stream, media_type="application/zip", headers=headers
        )

    # Varsayılan: düz CSV indir
    headers = {
        "Content-Disposition": f'attachment; filename="referrals_plain_{ts}.csv"',
        "X-Content-Type-Options": "nosniff",
    }
    return StreamingResponse(
        iter([csv_bytes]), media_type="application/octet-stream", headers=headers
    )


@router.get("/export")
async def export(current_user=Depends(get_current_user)):
    """
    Kullanıcı bazında CLAIMED özetini CSV olarak dışa aktarır.
    Kolonlar: user_id,email,referral_id,is_claimed,used_at
    """
    require_admin(current_user)

    buf = StringIO()
    buf.write("sep=,\n")
    buf.write("user_id,email,referral_id,is_claimed,used_at\n")

    async with async_session() as db:
        rows = (
            await db.execute(
                text(
                    """
            SELECT
                u.id,
                u.email,
                (
                  SELECT rc.id
                  FROM referral_codes rc
                  WHERE rc.used_by_user_id = u.id AND rc.status='CLAIMED'
                  ORDER BY rc.used_at DESC
                  LIMIT 1
                ) AS ref_id,
                EXISTS(
                  SELECT 1
                  FROM referral_codes rc2
                  WHERE rc2.used_by_user_id = u.id AND rc2.status='CLAIMED'
                ) AS is_claimed,
                (
                  SELECT rc3.used_at
                  FROM referral_codes rc3
                  WHERE rc3.used_by_user_id = u.id AND rc3.status='CLAIMED'
                  ORDER BY rc3.used_at DESC
                  LIMIT 1
                ) AS used_at
            FROM users u
            ORDER BY u.id ASC
        """
                )
            )
        ).all()

    for uid, email, ref_id, is_claimed, used_at in rows:
        used_at_str = used_at.isoformat() + "Z" if used_at else ""
        buf.write(
            f"{uid},{email},{ref_id or ''},{1 if is_claimed else 0},{used_at_str}\n"
        )

    headers = {
        # ISO dosya adında ':' sorun çıkarabilir → güvenli timestamp
        "Content-Disposition": f'attachment; filename="referrals_{datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")}.csv"'
    }
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv", headers=headers
    )
