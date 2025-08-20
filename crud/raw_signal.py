#!/usr/bin/env python3
# crud/raw_signal.py
# Python 3.9
import logging
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RawSignal
from app.schemas import WebhookSignal

logger = logging.getLogger(__name__)


async def insert_raw_signal(db: AsyncSession, signal: WebhookSignal) -> RawSignal:
    """Persist the incoming raw webhook payload as-is and return the DB row."""
    payload = jsonable_encoder(signal)
    db_signal = RawSignal(payload=payload, fund_manager_id=signal.fund_manager_id)
    db.add(db_signal)
    await db.flush()  # ensure db_signal.id is assigned
    logger.info(
        "Raw signal inserted (id=%s, fund_manager=%s)",
        db_signal.id,
        signal.fund_manager_id,
    )
    return db_signal
