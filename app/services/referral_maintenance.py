#!/usr/bin/env python3
# app/services/referral_maintenance.py
# Python 3.9
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def cleanup_expired_reserved(db: AsyncSession) -> int:
    """
    Tahsis süresi geçmiş RESERVED kayıtları tamamen boşa (AVAILABLE) çevirir.
    Kurallar:
      - Sadece RESERVED
      - email_reserved NOT NULL
      - expires_at NOT NULL ve geçmişte
    Dönüş: güncellenen satır sayısı
    """
    result = await db.execute(
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
    return result.rowcount
