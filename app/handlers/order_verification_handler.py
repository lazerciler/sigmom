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


# async def verify_closed_trades_for_execution(db: AsyncSession, execution):
async def verify_closed_trades_for_execution(
    db: AsyncSession, execution, exchange_name: str
):
    """
    Açık trade'leri dolaşır; borsada ilgili sembolde positionAmt == 0 ise
    trade'i kalıcı kayda geçirir ve open listesinden siler.
    (Şimdilik 'close-sinyali gelmiş olanlar' ayrımı yok; tüm open'ları kontrol eder.)
    """
    # res = await db.execute(
    #     select(StrategyOpenTrade).where(StrategyOpenTrade.status == "open")
    # )
    res = await db.execute(
        select(StrategyOpenTrade).where(
            StrategyOpenTrade.status == "open",
            StrategyOpenTrade.exchange == exchange_name,
        )
    )
    open_trades = res.scalars().all()

    for trade in open_trades:
        # Commit/flush sonrası ORM alanlarına dokunmamak için skalarları baştan al
        pid = trade.public_id
        sym = trade.symbol
        # Güvenlik: yanlışlıkla farklı borsadan trade gelirse yine de işlem yapma
        if (trade.exchange or "").strip() != exchange_name:
            logger.debug(
                "[closed-verify/skip] %s trade belongs to %s, runner=%s",
                pid,
                trade.exchange,
                exchange_name,
            )
            continue
        try:
            # Hedge ise doğru bacağı sor
            try:
                pm = getattr(execution.order_handler, "POSITION_MODE", "one_way")
            except AttributeError:
                pm = "one_way"
            if pm == "hedge":
                pos = await execution.order_handler.get_position(sym, side=trade.side)
            else:
                pos = await execution.order_handler.get_position(sym)

        except (
            Exception
        ) as e:  # exchange katmanından gelen çok çeşitli hataları tek noktada ele alıyoruz
            logger.warning(f"[closed-verify/get_position] {sym} hata: {e}")
            continue

        amt = Decimal(str((pos or {}).get("positionAmt", "0"))).copy_abs()
        if amt == 0:
            # Bu open trade için zaten bir kapanış trade’i yazılmış mı?
            exists_q = await db.execute(
                select(func.count())
                .select_from(StrategyTrade)
                .where(StrategyTrade.open_trade_public_id == pid)
            )
            if (exists_q.scalar_one() or 0) > 0:
                # Kayıt zaten var → sadece statüyü kapat ve KALICI yap
                if (trade.status or "").lower() != "closed":
                    trade.status = "closed"
                    await db.flush()
                    await db.commit()
                logger.info("[verify] skip: already recorded close for %s", pid)
                continue
            # logger.info(
            #     f"[closed-verify] {sym} → There is no position in the stock market; closing is recorded."
            # )
            logger.info(
                "[closed-verify] %s | %s → no position on exchange; closing is recorded.",
                exchange_name,
                sym,
            )
            ok = await close_open_trade_and_record(db, trade, pos)
            if not ok:
                logger.error("[closed-verify] failed to record close for %s", pid)
            if ok:
                await db.commit()  # ← kayıt + status değişiklikleri kalıcı
        else:
            logger.debug(f"[closed-verify] {sym} → still open (amt={amt}).")
