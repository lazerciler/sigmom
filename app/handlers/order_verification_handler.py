#!/usr/bin/env python3
# app/handlers/order_verification_handler.py
# python 3.9
import logging
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import StrategyOpenTrade
from crud.trade import close_open_trade_and_record

logger = logging.getLogger("verifier")


async def verify_closed_trades_for_execution(db: AsyncSession, execution):
    """
    Açık trade'leri dolaşır; borsada ilgili sembolde positionAmt == 0 ise
    trade'i kalıcı kayda geçirir ve open listesinden siler.
    (Şimdilik 'close-sinyali gelmiş olanlar' ayrımı yok; tüm open'ları kontrol eder.)
    """
    res = await db.execute(
        select(StrategyOpenTrade).where(StrategyOpenTrade.status == "open")
    )
    open_trades = res.scalars().all()

    for trade in open_trades:
        try:
            pos = await execution.order_handler.get_position(trade.symbol)
        except Exception as e:
            logger.warning(f"[closed-verify/get_position] {trade.symbol} hata: {e}")
            continue

        amt = Decimal(str((pos or {}).get("positionAmt", "0"))).copy_abs()
        if amt == 0:
            logger.info(
                f"[closed-verify] {trade.symbol} → borsada pozisyon yok; kapanış kaydı yapılıyor."
            )
            await close_open_trade_and_record(db, trade, pos)
        else:
            logger.debug(f"[closed-verify] {trade.symbol} → hâlâ açık (amt={amt}).")
