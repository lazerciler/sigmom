#!/usr/bin/env python3
# app/routers/webhook_router.py
# Python 3.9
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas import WebhookSignal
from app.database import get_db
from app.handlers.signal_handler import handle_signal
from app.security.fm_guard import ensure_authorized_fund_manager

router = APIRouter(prefix="/webhook", tags=["Webhook"])


@router.post("/", status_code=status.HTTP_200_OK)
async def receive_webhook(
    signal: WebhookSignal, db: AsyncSession = Depends(get_db)
) -> dict:
    ensure_authorized_fund_manager(signal.fund_manager_id)
    return await handle_signal(signal, db)
