#!/usr/bin/env python3
# app/routers/webhook_router.py
# Python 3.9

from fastapi import APIRouter, Depends, status
import json
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas import WebhookSignal
from app.database import get_db
from app.handlers.signal_handler import handle_signal
from app.security.fm_guard import ensure_authorized_fund_manager

try:
    import httpx
except ImportError:  # httpx yoksa sorun değil
    httpx = None

router = APIRouter(prefix="/webhook", tags=["Webhook"])


@router.post("/", status_code=status.HTTP_200_OK)
async def receive_webhook(
    signal: WebhookSignal, db: AsyncSession = Depends(get_db)
) -> dict:
    ensure_authorized_fund_manager(signal.fund_manager_id)
    # return await handle_signal(signal, db)
    try:
        result = await handle_signal(signal, db)

        def _safe(obj):
            # 1) SQLAlchemy ORM instance? (I/O tetiklemeden)
            state = getattr(obj, "_sa_instance_state", None)
            if state is not None:
                ikey = getattr(state, "identity_key", None)
                ident = ikey[1] if isinstance(ikey, tuple) and len(ikey) > 1 else None
                return {"orm": obj.__class__.__name__, "identity": ident}
            # 2) Row / RowMapping
            m = getattr(obj, "_mapping", None)  # SQLAlchemy Row -> Mapping
            if m is not None:
                from collections.abc import Mapping

                return (
                    dict(m) if isinstance(m, Mapping) else {"type": type(obj).__name__}
                )
            # 3) httpx.Response
            if httpx and isinstance(obj, httpx.Response):
                try:
                    return obj.json()
                except json.JSONDecodeError:
                    return {"raw": obj.text or None, "status_code": obj.status_code}
            # 4) bytes/str -> JSON parse dene, olmazsa raw
            if isinstance(obj, (bytes, str)):
                s = obj.decode() if isinstance(obj, bytes) else obj
                try:
                    return json.loads(s)
                except json.JSONDecodeError:
                    return {"raw": s or None}
            # 5) dict/list/None/primitive
            if obj is None or isinstance(obj, (dict, list, int, float, bool)):
                return obj
            return {"type": type(obj).__name__}

        data = _safe(result)
        return {"ok": True, "result": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}
