#!/usr/bin/env python3
# app/services/capacity.py
# Python 3.9

# Lokal test için kapasite durumu stub.
# ?full=1 parametresiyle “kapasite dolu” sahnesini test edersin.

from fastapi import Request

async def is_capacity_full(request: Request = None) -> bool:
    try:
        # Request opsiyonel ama panel.py’den geçirebiliriz; geçmezsek False döner.
        if request and request.query_params.get("full") == "1":
            return True
    except Exception:
        pass
    return False
