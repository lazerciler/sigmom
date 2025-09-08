#!/usr/bin/env python3
# app/routers/admin_referrals.py
# Python 3.9
from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from io import StringIO, BytesIO
from datetime import datetime, timedelta
from pathlib import Path
import bcrypt
import secrets
import string
import pyzipper

from app.database import get_db
from app.dependencies.auth import require_admin_db

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"  # app/templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(
    prefix="/admin/referrals",
    tags=["admin"],
    # Tüm endpoint'ler admin korumalı
    dependencies=[Depends(require_admin_db)],
)

CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)

ALPH = string.ascii_uppercase + string.digits


def _gen_plain():
    return "-".join("".join(secrets.choice(ALPH) for _ in range(4)) for _ in range(3))


async def _fetch_panel_data(db: AsyncSession):
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
async def panel(
    request: Request,
    db: AsyncSession = Depends(get_db),
    me=Depends(require_admin_db),
):
    users, codes, free_codes = await _fetch_panel_data(db)
    return templates.TemplateResponse(
        "admin_referrals.html",
        {
            "request": request,
            "users": users,
            "codes": codes,
            "free_codes": free_codes,
            "me": me,
        },
        headers={
            "Content-Security-Policy": CSP,
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "same-origin",
        },
    )


# Expiry temizliği için manuel buton/endpoint'i (hemen çalıştır-gör)
@router.post("/expire_cleanup", response_class=HTMLResponse)
async def expire_cleanup(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
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
    await db.commit()
    # result.rowcount ile kaç satırın temizlendiğini görmek istersen loglayabilirsin
    return await panel(request, db=db, me=None)  # router guard zaten admin


@router.post("/assign", response_class=HTMLResponse)
async def assign(
    request: Request,
    email: str = Form(...),
    referral_id: int = Form(...),  # ikisi de ZORUNLU
    plain_code: str = Form(...),  # ikisi de ZORUNLU
    db: AsyncSession = Depends(get_db),
    me=Depends(require_admin_db),
):

    email = (email or "").strip().lower()
    if not email:
        raise HTTPException(400, "email gerekli")

    now = datetime.utcnow()
    # Rezerv süresi (istersen ayarlanabilir yapabilirsin)
    DEFAULT_RESERVE_DAYS = 14
    exp_new = now + timedelta(days=DEFAULT_RESERVE_DAYS)

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
    if status == "RESERVED" and email_res and email_res.strip().lower() != email:
        raise HTTPException(400, "Kod farklı bir e-posta için tahsisli.")

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

    await db.commit()
    return await panel(request, db=db, me=me)


@router.post("/unassign", response_class=HTMLResponse)
async def unassign(
    request: Request,
    user_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.utcnow()

    # Transaction zaten açık olabilir; doğrudan çalıştır, en sonda commit et
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
        raise HTTPException(409, "Kod bu sırada değişti; lütfen tekrar deneyin.")

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

    await db.commit()
    return await panel(request, db=db, me=None)


@router.post("/generate", response_class=HTMLResponse)
async def generate(
    request: Request,
    count: int = Form(...),
    days: int = Form(14),  # NOT: AVAILABLE üretimde kullanılmıyor (rezerve yok)
    email_reserved: str = Form(None),  # NOT: AVAILABLE üretimde kullanılmıyor
    mode: str = Form("download"),  # "download" | "zip"
    zip_password: str = Form(None),  # ZIP için opsiyonel parola
    db: AsyncSession = Depends(get_db),
    me=Depends(require_admin_db),
):
    """
    Yeni referans kodları üretir ve plaintext CSV/ZIP olarak indirir.
    - Üretim mantığı: AVAILABLE (boş havuz)
      email_reserved = NULL, expires_at = NULL
    - Rezerve/expiry işleri /assign ile yönetilir.
    """
    count = max(1, min(100, int(count or 1)))
    days = max(
        1, min(180, int(days or 14))
    )  # AVAILABLE modda kullanılmıyor; parametre uyumluluğu için tutuldu
    email_reserved = (email_reserved or "").strip().lower() or None

    created = []
    email_reserved = (email_reserved or "").strip().lower() or None
    from datetime import datetime, timedelta

    expires_at_val = (
        (datetime.utcnow() + timedelta(days=int(days))) if email_reserved else None
    )

    for _ in range(count):
        plain = _gen_plain()
        code_hash = bcrypt.hashpw(
            plain.strip().upper().encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

        if email_reserved:
            # Rezerve kod üret (admin tarafından ayrılmış)
            await db.execute(
                text(
                    """
                    INSERT INTO referral_codes
                      (code_hash, email_reserved, status, tier, invited_by_admin_id, expires_at)
                    VALUES
                      (:h, :email, 'RESERVED', 'default', :admin_id, :exp)
                    """
                ),
                {
                    "h": code_hash,
                    "email": email_reserved,
                    "admin_id": me["id"],
                    "exp": expires_at_val,
                },
            )
        else:
            # Boş havuza at (AVAILABLE)
            await db.execute(
                text(
                    """
                    INSERT INTO referral_codes
                      (code_hash, status, tier, invited_by_admin_id)
                    VALUES
                      (:h, 'AVAILABLE', 'default', :admin_id)
                    """
                ),
                {"h": code_hash, "admin_id": me["id"]},
            )

        rid = (await db.execute(text("SELECT LAST_INSERT_ID()"))).first()[0]
        created.append(
            {
                "id": rid,
                "plain": plain,
                "email_reserved": email_reserved or "",
                "expires_at": (
                    expires_at_val.isoformat(sep=" ") if expires_at_val else ""
                ),
            }
        )
    await db.commit()

    # CSV içeriği (AVAILABLE üretimde email_reserved/expiry boş kalır)
    csv_buf = StringIO()
    csv_buf.write("sep=,\n")

    csv_buf.write("id,code,email_reserved,expires_at\n")
    for row in created:
        csv_buf.write(
            f'{row["id"]},{row["plain"]},{row["email_reserved"]},{row["expires_at"]}\n'
        )

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
async def export(db: AsyncSession = Depends(get_db)):
    """
    Kullanıcı bazında CLAIMED özetini CSV olarak dışa aktarır.
    Kolonlar: user_id,email,referral_id,is_claimed,used_at
    """

    buf = StringIO()
    buf.write("sep=,\n")
    buf.write("user_id,email,referral_id,is_claimed,used_at\n")

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
