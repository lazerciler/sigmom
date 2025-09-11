#!/usr/bin/env python3
# app/utils/position_utils.py
# python 3.9
from decimal import Decimal
import logging
from datetime import datetime
from sqlalchemy import update, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import StrategyOpenTrade


logger = logging.getLogger("verifier")


async def confirm_open_trade(
    db: AsyncSession, trade: StrategyOpenTrade, position_data: dict
):
    """
    Borsayı tek otorite kabul ederek StrategyOpenTrade kaydını kesinleştirir.
    Config'e bakmaz; yön kararını sadece exchange çıktısından verir:
      - positionSide == LONG/SHORT → hedge bacağı
      - positionSide == BOTH       → one-way; yönü positionAmt işaretinden seç
    ONE-WAY (BOTH) durumda ters bacak açıksa kapatır (aynı sembol+exchange için tek açık kayıt).
    """
    try:
        entry_price = Decimal(str(position_data.get("entryPrice", 0)))
        position_amt = Decimal(
            str(position_data.get("positionAmt", position_data.get("size", 0)))
        )
        leverage = int(float(position_data.get("leverage", 1)))
        position_side = str(position_data.get("positionSide", "BOTH")).upper()
    except Exception as e:
        logger.warning(f"[confirm_open_trade parse error] {e}")
        return

    # Yön seçimi (yalnızca exchange verisi)
    decided_side = None
    if position_side == "LONG":
        decided_side = "long"
    elif position_side == "SHORT":
        decided_side = "short"
    elif position_side == "BOTH":
        if position_amt > 0:
            decided_side = "long"
        elif position_amt < 0:
            decided_side = "short"

    # Guardlar
    if not decided_side or entry_price <= 0 or position_amt.copy_abs() <= 0:
        logger.warning(
            f"[confirm_open_trade] insufficient data "
            f"(side={decided_side}, entry={entry_price}, amt={position_amt}) for {trade.symbol}"
        )
        return

    # One-way (BOTH) ise ters bacağı kapat
    if position_side == "BOTH":
        other_side = "short" if decided_side == "long" else "long"
        res = await db.execute(
            select(StrategyOpenTrade)
            .where(func.upper(StrategyOpenTrade.symbol) == (trade.symbol or "").upper())
            .where(StrategyOpenTrade.exchange == (trade.exchange or ""))
            .where(StrategyOpenTrade.side == other_side)
            .where(StrategyOpenTrade.status == "open")
        )
        other = res.scalar_one_or_none()
        if other:
            other.status = "closed"
            await db.flush()

    # Mevcut trade’i borsa verisiyle kesinleştir
    now = datetime.utcnow()
    await db.execute(
        update(StrategyOpenTrade)
        .where(StrategyOpenTrade.id == trade.id)
        .values(
            side=decided_side,
            entry_price=entry_price,
            position_size=position_amt,
            leverage=leverage,
            status="open",
            exchange_verified=True,
            confirmed_at=now,
            last_checked_at=now,
        )
    )
    await db.flush()
    logger.info(
        f"[confirm_open_trade] {trade.symbol} side={decided_side},"
        f" entry={entry_price}, size={position_amt}, lev={leverage}"
    )


def position_matches(position: dict) -> bool:
    logger.debug("position_matches() real implementation is in use.")

    amt = Decimal(str(position.get("positionAmt", position.get("size", 0)))).copy_abs()
    entry_price = Decimal(str(position.get("entryPrice", 0)))

    has_position = amt > Decimal("0")

    logger.debug(
        f"🔍 Pozisyon durumu → has_position={has_position}, positionAmt={amt}, entryPrice={entry_price}"
    )
    return has_position
