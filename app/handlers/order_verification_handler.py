#!/usr/bin/env python3
# app/handlers/order_verification_handler.py
# python 3.9
import logging
from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import StrategyOpenTrade, StrategyTrade
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
            # Hedge ise doğru bacağı sor
            try:
                pm = getattr(execution.order_handler, "POSITION_MODE", "one_way")
            except Exception:
                pm = "one_way"
            if pm == "hedge":
                pos = await execution.order_handler.get_position(
                    trade.symbol, side=trade.side
                )
            else:
                pos = await execution.order_handler.get_position(trade.symbol)

        except Exception as e:
            logger.warning(f"[closed-verify/get_position] {trade.symbol} hata: {e}")
            continue

        amt = Decimal(str((pos or {}).get("positionAmt", "0"))).copy_abs()
        if amt == 0:
            # Bu open trade için zaten bir kapanış trade’i yazılmış mı?
            exists_q = await db.execute(
                select(func.count())
                .select_from(StrategyTrade)
                .where(StrategyTrade.open_trade_public_id == trade.public_id)
            )
            if (exists_q.scalar_one() or 0) > 0:
                # Kayıt zaten var → sadece statüyü kapatıp geç (ikinci trade yazma)
                if (trade.status or "").lower() != "closed":
                    trade.status = "closed"
                    await db.flush()
                logger.info(
                    "[verify] skip: already recorded close for %s", trade.public_id
                )
                continue
            logger.info(
                f"[closed-verify] {trade.symbol} → There is no position in the stock market; closing is recorded."
            )
            await close_open_trade_and_record(db, trade, pos)
            # await db.commit()
        else:
            logger.debug(f"[closed-verify] {trade.symbol} → still open (amt={amt}).")
