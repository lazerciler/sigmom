#!/usr/bin/env python3
# app/database.py
# Python 3.9

# Lokal test için “opsiyonel kullanıcı” döndüren minimal dependency.
# ?mock_user=1 ile kullanıcıyı simüle eder; ?verified=1 ile referans doğrulanmış gibi davranır.

from types import SimpleNamespace
from fastapi import Request

async def get_current_user_opt(request: Request):
    if request.query_params.get("mock_user") == "1":
        return SimpleNamespace(
            id=1,
            email="demo@sigma.local",
            name="Demo Kullanıcı",
            referral_verified_at=("2025-01-01" if request.query_params.get("verified") == "1" else None),
        )
    return None
