#!/usr/bin/env python3
# app/services/referrals.py
# Python 3.9
from typing import Optional, Dict
from sqlalchemy import text

async def get_dynamic_capacity(db, user_email: Optional[str]) -> Dict[str, int]:
    # Genel (herkese açık) boş slotlar
    row = (await db.execute(text("""
        SELECT COUNT(*) FROM referral_codes
        WHERE status='RESERVED' AND email_reserved IS NULL
    """))).first()
    free_general = int(row[0])

    free_for_user = 0
    if user_email:
        row2 = (await db.execute(text("""
            SELECT COUNT(*) FROM referral_codes
            WHERE status='RESERVED' AND email_reserved = :email
        """), {"email": user_email.strip().lower()})).first()
        free_for_user = int(row2[0])

    return {
        "free_general": free_general,
        "free_for_user": free_for_user,
        "free_total_for_user": free_general + free_for_user,
    }
