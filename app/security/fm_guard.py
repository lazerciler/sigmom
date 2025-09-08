#!/usr/bin/env python3
# app/security/fm_guard.py
# Python 3.9

from fastapi import HTTPException
from app.config import settings


def ensure_authorized_fund_manager(fund_manager_id: str) -> None:
    """
    Basit allowlist kontrolü:
      - fund_manager_id boşsa 400
      - .env'de ALLOWED_FUND_MANAGER_IDS tanımlıysa ve id listede yoksa 403
    """
    if not fund_manager_id or not str(fund_manager_id).strip():
        raise HTTPException(status_code=400, detail="Missing fund manager.")
    allow = settings.allowed_fund_manager_ids
    if allow and fund_manager_id not in allow:
        raise HTTPException(status_code=403, detail="Unauthorized fund manager.")
