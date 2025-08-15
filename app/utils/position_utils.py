#!/usr/bin/env python3
# app/utils/position_utils.py
# python 3.9
from decimal import Decimal
import logging
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import StrategyOpenTrade

logger = logging.getLogger("verifier")


async def confirm_open_trade(db: AsyncSession, trade: StrategyOpenTrade, position_data: dict):
    """
    Pozisyon borsada gerçekten açıldıysa, bu bilgiyi trade objesine işler ve veritabanına yazar.
    """
    try:
        entry_price = Decimal(str(position_data.get("entryPrice", 0)))
    except Exception as e:
        logger.warning(f"[entry_price parse error] {e}")
        return

    await db.execute(
        update(StrategyOpenTrade)
        .where(StrategyOpenTrade.id == trade.id)
        .values(entry_price=entry_price)
    )
    await db.flush()
    logger.info(f"[confirm_open_trade] Entry price güncellendi: {trade.symbol} → {entry_price}")


def position_matches(position: dict) -> bool:
    logger.debug("position_matches() real implementation is in use.")

    amt = Decimal(str(position.get("positionAmt", position.get("size", 0)))).copy_abs()
    entry_price = Decimal(str(position.get("entryPrice", 0)))

    has_position = amt > Decimal("0")

    logger.debug(f"🔍 Pozisyon durumu → has_position={has_position}, positionAmt={amt}, entryPrice={entry_price}")
    return has_position
