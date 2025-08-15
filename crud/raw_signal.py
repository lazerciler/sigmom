#!/usr/bin/env python3
# crud/raw_signal.py
# Python 3.9
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.encoders import jsonable_encoder
import logging

from app.models import RawSignal
from app.schemas import WebhookSignal
from app.utils.exchange_loader import load_utils_module

logger = logging.getLogger(__name__)


async def insert_raw_signal(db: AsyncSession, signal: WebhookSignal) -> RawSignal:
    # 1. Leverage ayarını dinamik utils modülüne devret
    utils = load_utils_module(signal.exchange)
    try:
        await utils.set_leverage(signal.symbol, signal.leverage)
    except Exception as e:
        logger.warning(f"Kaldıraç ayarlanamadı fallback: {e}")

    # 2. Gelen db oturumuyla raw sinyali ekle
    json_payload = jsonable_encoder(signal)
    db_signal = RawSignal(payload=json_payload, fund_manager_id=signal.fund_manager_id)
    db.add(db_signal)
    # Eğer dışarıda begin() yoksa burada flush/commit gerekebilir:
    await db.flush()  # db_signal.id atanır
    # await db.commit()  # commit işini üst kata bırakmak daha esnek olabilir
    return db_signal
