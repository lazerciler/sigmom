#!/usr/bin/env python3
# crud/trade.py
# Python 3.9
from decimal import Decimal, InvalidOperation
import uuid
import logging
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, desc
from typing import Union, Optional
from app.models import StrategyOpenTrade, StrategyTrade
# from app.schemas import WebhookSignal  # Bu satır kullanılmıyor
# from app.utils.exchange_loader import load_execution_module  # Bu satır kullanılmıyor
from app.utils.position_utils import position_matches, confirm_open_trade
from sqlalchemy import text

async def get_open_trade_for_close(
    db: AsyncSession,
    public_id: Optional[str],  # str | None yerine Optional[str]
    symbol: str,
    exchange: str,
) -> Union[StrategyOpenTrade, None]:  # StrategyOpenTrade | None yerine
    """
    Close sinyali geldiğinde kapatılacak open trade'i güvenli biçimde seçer.
    - Öncelik public_id (tekil ve güvenli).
    - public_id yoksa: symbol+exchange+status='open' içinden EN SON kaydı alır.
    """
    if public_id:
        q = select(StrategyOpenTrade).where(
            StrategyOpenTrade.public_id == public_id,
            StrategyOpenTrade.status == "open",
        )
        res = await db.execute(q)
        return res.scalar_one_or_none()

    q = (
        select(StrategyOpenTrade)
        .where(
            StrategyOpenTrade.symbol == symbol,
            StrategyOpenTrade.exchange == exchange,
            StrategyOpenTrade.status == "open",
        )
        .order_by(desc(StrategyOpenTrade.timestamp))
    )
    res = await db.execute(q)
    return res.scalars().first()


# async def close_open_trade_and_record(db: AsyncSession, trade: StrategyOpenTrade, position_data: dict):
#     """
#     Açık pozisyon kapanmışsa:
#     - PnL hesaplanır,
#     - StrategyTrade tablosuna yazılır,
#     - StrategyOpenTrade'den silinir.
#     """
#     logger = logging.getLogger("verifier")
#
#     try:
#         # close_price = Decimal(str(position_data.get("markPrice") or position_data.get("entryPrice")))
#         close_price = Decimal(str(position_data.get("markPrice") or position_data.get("entryPrice") or 0))
#         open_price = trade.entry_price
#         position_size = trade.position_size
#
#         # Basit PnL hesaplama (long/short'a göre)
#         if trade.side.lower() == "long":
#             pnl = (close_price - open_price) * position_size
#         else:
#             pnl = (open_price - close_price) * position_size
#
#         closed_trade = StrategyTrade(
#             public_id=str(uuid.uuid4()),
#             open_trade_public_id=getattr(trade, "public_id", None),
#             raw_signal_id=getattr(trade, "raw_signal_id", None),
#             symbol=trade.symbol,
#             side=trade.side,
#             entry_price=open_price,
#             exit_price=close_price,
#             position_size=position_size,
#             leverage=getattr(trade, "leverage", None),
#             realized_pnl=pnl,
#             order_type=getattr(trade, "order_type", "market"),
#             timestamp=datetime.utcnow(),
#             exchange=trade.exchange,
#             fund_manager_id=getattr(trade, "fund_manager_id", None),
#             response_data=getattr(trade, "response_data", {}) or {},
#         )
#
#         # Önce trade'i ekle
#         db.add(closed_trade)
#         await db.flush()  # burada NOT NULL / FK hatalarını hemen yakalar
#
#         # Sonra open trade'i sil
#         await db.delete(trade)
#
#         await db.commit()
#         logger.info(f"[closed-recorded] {trade.symbol} → PnL: {pnl:.2f} was written and open trade was deleted.")
#
#     except Exception as e:
#         logger.exception(f"[close-fail] {trade.symbol} position closing record failed: {e}")


# async def close_open_trade_and_record(db: AsyncSession, trade: StrategyOpenTrade, position_data: dict):
#     """
#     Açık pozisyon kapanmışsa:
#     - PnL hesaplanır,
#     - StrategyTrade tablosuna yazılır,
#     - StrategyOpenTrade'den silinir.
#     """
#     logger = logging.getLogger("verifier")
#
#     try:
#         close_price = Decimal(str(position_data.get("markPrice") or position_data.get("entryPrice") or 0))
#         open_price = trade.entry_price
#         position_size = trade.position_size
#
#         pnl = (close_price - open_price) * position_size if trade.side.lower() == "long" else (open_price - close_price) * position_size
#
#         closed_trade = StrategyTrade(
#             public_id=str(uuid.uuid4()),
#             open_trade_public_id=trade.public_id,
#             raw_signal_id=trade.raw_signal_id,
#             symbol=trade.symbol,
#             side=trade.side,
#             entry_price=open_price,
#             exit_price=close_price,
#             position_size=position_size,
#             leverage=trade.leverage,
#             realized_pnl=pnl,
#             order_type=trade.order_type or "market",
#             timestamp=datetime.utcnow(),
#             exchange=trade.exchange,
#             fund_manager_id=trade.fund_manager_id,
#             response_data=trade.response_data or {},
#         )
#
#         # Önce trade'i ekle
#         db.add(closed_trade)
#         await db.flush()  # FK / NOT NULL kontrolü burada yapılır
#
#         # Sonra open trade'i sil
#         await db.delete(trade)
#
#         # Commit sırasında hata var mı, net görmek için try/except
#         try:
#             await db.commit()
#         except Exception as e:
#             logger.exception(f"[DB-COMMIT-FAIL] {e}")
#             await db.rollback()
#             return
#
#         # Commit başarılı → hemen DB’den doğrula
#         try:
#             result = await db.execute(
#                 text("""
#                     SELECT id, public_id, symbol, realized_pnl
#                     FROM strategy_trades
#                     WHERE open_trade_public_id = :otpid
#                     ORDER BY id DESC LIMIT 1
#                 """),
#                 {"otpid": trade.public_id}
#             )
#
#             row = result.fetchone()
#             if row:
#                 logger.info(f"[DB-VERIFY] Trade kaydı bulundu → ID: {row.id}, Symbol: {row.symbol}, PnL: {row.realized_pnl}")
#             else:
#                 logger.warning(f"[DB-VERIFY] Commit sonrası trade kaydı BULUNAMADI! → open_trade_public_id={trade.public_id}")
#         except Exception as e:
#             logger.exception(f"[DB-VERIFY-FAIL] {e}")
#
#         logger.info(f"[closed-recorded] {trade.symbol} → PnL: {pnl:.2f} was written and open trade was deleted.")
#
#     except Exception as e:
#         await db.rollback()
#         logger.exception(f"[close-fail] {trade.symbol} position closing record failed: {e}")


async def close_open_trade_and_record(db: AsyncSession, trade: StrategyOpenTrade, position_data: dict):
    """
    Açık pozisyon kapanmışsa:
    - PnL hesaplanır,
    - StrategyTrade tablosuna yazılır,
    - StrategyOpenTrade status='closed' yapılır.
    """
    logger = logging.getLogger("verifier")

    try:
        close_price = Decimal(str(position_data.get("markPrice") or position_data.get("entryPrice") or 0))
        open_price = trade.entry_price
        position_size = trade.position_size

        pnl = (close_price - open_price) * position_size if trade.side.lower() == "long" else (open_price - close_price) * position_size

        closed_trade = StrategyTrade(
            public_id=str(uuid.uuid4()),
            open_trade_public_id=trade.public_id,
            raw_signal_id=trade.raw_signal_id,
            symbol=trade.symbol,
            side=trade.side,
            entry_price=open_price,
            exit_price=close_price,
            position_size=position_size,
            leverage=trade.leverage,
            realized_pnl=pnl,
            order_type=trade.order_type or "market",
            timestamp=datetime.utcnow(),
            exchange=trade.exchange,
            fund_manager_id=trade.fund_manager_id,
            response_data=trade.response_data or {},
        )

        # Trade tablosuna ekle
        db.add(closed_trade)
        await db.flush()

        # Açık pozisyonu silme → status='closed' yap
        trade.status = "closed"
        await db.flush()

        # Commit kontrolü
        try:
            await db.commit()
        except Exception as e:
            logger.exception(f"[DB-COMMIT-FAIL] {e}")
            await db.rollback()
            return

        # Commit sonrası doğrulama
        try:
            result = await db.execute(
                text("""
                    SELECT id, public_id, symbol, realized_pnl 
                    FROM strategy_trades 
                    WHERE open_trade_public_id = :otpid
                    ORDER BY id DESC LIMIT 1
                """),
                {"otpid": trade.public_id}
            )
            row = result.fetchone()
            if row:
                logger.info(f"[DB-VERIFY] Trade kaydı bulundu → ID: {row.id}, Symbol: {row.symbol}, PnL: {row.realized_pnl}")
            else:
                logger.warning(f"[DB-VERIFY] Commit sonrası trade kaydı BULUNAMADI! → open_trade_public_id={trade.public_id}")
        except Exception as e:
            logger.exception(f"[DB-VERIFY-FAIL] {e}")

        logger.info(f"[closed-recorded] {trade.symbol} → PnL: {pnl:.2f} was written and open trade status set to CLOSED.")

    except Exception as e:
        await db.rollback()
        logger.exception(f"[close-fail] {trade.symbol} position closing record failed: {e}")


async def increment_attempt_count(db: AsyncSession, trade_id: int) -> StrategyOpenTrade:
    await db.execute(
        update(StrategyOpenTrade)
        .where(StrategyOpenTrade.id == trade_id)
        .values(
            verification_attempts=StrategyOpenTrade.verification_attempts + 1,
            last_checked_at=datetime.utcnow(),
        )
    )
    # Değişikliği yaptıktan sonra modeli geri çekip return etmelisin
    result = await db.execute(select(StrategyOpenTrade).where(StrategyOpenTrade.id == trade_id))
    trade = result.scalar_one()
    return trade


async def get_pending_open_trades(db: AsyncSession) -> list[StrategyOpenTrade]:
    result = await db.execute(
        select(StrategyOpenTrade).where(StrategyOpenTrade.status == "pending")
    )
    return result.scalars().all()


async def mark_trade_as_open(db: AsyncSession, trade: StrategyOpenTrade):
    await db.execute(
        update(StrategyOpenTrade)
        .where(StrategyOpenTrade.id == trade.id)
        .values(
            status="open",
            exchange_verified=True,
            confirmed_at=datetime.utcnow(),
            last_checked_at=datetime.utcnow(),
        )
    )


async def mark_trade_as_failed(db: AsyncSession, trade: StrategyOpenTrade):
    await db.execute(
        update(StrategyOpenTrade)
        .where(StrategyOpenTrade.id == trade.id)
        .values(
            status="failed",
            exchange_verified=False,
            last_checked_at=datetime.utcnow(),
            verification_attempts=StrategyOpenTrade.verification_attempts + 1,
        )
    )


async def verify_pending_trades_for_execution(db: AsyncSession, execution, max_retries: int = 3):
    """
    Pending durumdaki açık pozisyonları exchange ile doğrular.
    Başarılıysa status="open", exchange_verified=True;
    retry aşıldıysa status="failed".
    """
    verifier_logger = logging.getLogger("verifier")

    result = await db.execute(
        select(StrategyOpenTrade).where(StrategyOpenTrade.status == "pending")
    )
    pending_trades = result.scalars().all()
    verifier_logger.info(f"[loop] {len(pending_trades)} pending trade found")

    for open_trade in pending_trades:
        now = datetime.utcnow()

        if open_trade.last_checked_at and (now - open_trade.last_checked_at) < timedelta(seconds=5):
            verifier_logger.debug(f"[skip] {open_trade.symbol} - checked too recently")
            continue

        verifier_logger.debug(f"[verify-start] {open_trade.symbol} | side: {open_trade.side}, size: {open_trade.position_size}")
        verifier_logger.debug(f"🧩 execution.order_handler.get_position: {getattr(execution.order_handler, 'get_position', 'NONE')}")

        try:
            position = await execution.order_handler.get_position(open_trade.symbol)
        except Exception as e:
            verifier_logger.warning(f"[exception] get_position({open_trade.symbol}) exception: {e}")
            continue

        verifier_logger.debug(f"[position] {open_trade.symbol}: {position!r}")
        verifier_logger.debug(f"📦 Position was brought: {open_trade.symbol} → {position}")

        if not position:
            verifier_logger.warning(f"[no-position] Could not get a position for {open_trade.symbol}")
            continue

        # ✅ Yeni signature ile kullan
        if position_matches(position):
            open_trade.status = "open"
            open_trade.exchange_verified = True
            open_trade.confirmed_at = now
            await confirm_open_trade(db, open_trade, position)  # 👈 bunu ekle
            verifier_logger.info(f"[verified] {open_trade.symbol} position confirmed.")
        else:
            await increment_attempt_count(db, open_trade.id)
            await db.refresh(open_trade)

            if open_trade.verification_attempts >= max_retries:
                open_trade.status = "failed"
                verifier_logger.warning(f"[failed] ❌ {open_trade.symbol} max retries ({max_retries}) exceeded, position is invalid.")
            else:
                verifier_logger.debug(f"[retry] {open_trade.symbol} retries {open_trade.verification_attempts}/{max_retries}")

        open_trade.last_checked_at = now
        await db.commit()


async def insert_strategy_trade_from_open(
    db: AsyncSession,
    open_trade,
    signal_data,
    order_response: dict,
    close_raw_signal,  # yeni parametre
):
    try:
        entry_price = Decimal(str(open_trade.entry_price))
        exit_price = Decimal(str(getattr(signal_data, "exit_price", None)))
        position_size = Decimal(str(open_trade.position_size))
    except (InvalidOperation, TypeError) as e:
        raise RuntimeError(f"Price conversion error: {e}")

    side = open_trade.side.lower()
    if side == "long":
        pnl_value = (exit_price - entry_price) * position_size
    else:
        pnl_value = (entry_price - exit_price) * position_size

    trade = StrategyTrade(
        public_id=str(uuid.uuid4()),
        raw_signal_id=close_raw_signal.id,  # close sinyalinin raw_signal.id'si
        open_trade_public_id=open_trade.public_id,
        symbol=signal_data.symbol,
        side=signal_data.side,
        entry_price=entry_price,
        exit_price=exit_price,
        position_size=position_size,
        leverage=open_trade.leverage,
        realized_pnl=pnl_value,
        order_type=signal_data.order_type,
        timestamp=datetime.utcnow(),
        exchange=signal_data.exchange,
        fund_manager_id=signal_data.fund_manager_id,
        response_data=order_response.get("data", {}),
    )
    db.add(trade)


async def insert_strategy_open_trade(db: AsyncSession, open_trade: StrategyOpenTrade):
    """
    Yeni açık pozisyonu DB'ye ekler. open_trade.exchange_order_id
    ve status="pending" olarak gelmiş olmalı.
    """
    db.add(open_trade)
    await db.flush()
    return open_trade


async def insert_strategy_trade(db: AsyncSession, signal_data, order_response: dict):
    open_trade = await get_open_trade_by_symbol_and_exchange(
        db, signal_data.symbol, signal_data.exchange
    )
    if not open_trade:
        raise RuntimeError("No open positions found for Close")

    # Fiyatları Decimal'a çevir
    try:
        entry_price = Decimal(str(open_trade.entry_price))
        exit_price = Decimal(str(getattr(signal_data, "exit_price", None)))
    except (InvalidOperation, TypeError) as e:
        raise RuntimeError(f"Price conversion error: {e}")

    position_size = Decimal(str(open_trade.position_size))
    side = open_trade.side.lower()

    if side == "long":
        realized_pnl = (exit_price - entry_price) * position_size
    else:
        realized_pnl = (entry_price - exit_price) * position_size

    trade = StrategyTrade(
        public_id=str(uuid.uuid4()),
        open_trade_public_id=open_trade.public_id,
        symbol=signal_data.symbol,
        side=signal_data.side,
        entry_price=entry_price,
        exit_price=exit_price,
        position_size=position_size,
        leverage=open_trade.leverage,
        realized_pnl=realized_pnl,
        exchange=signal_data.exchange,
        fund_manager_id=signal_data.fund_manager_id,
        response_data=order_response.get("data", {}),
        timestamp=datetime.utcnow(),
    )
    db.add(trade)


async def get_open_trade_by_symbol_and_exchange(
    db: AsyncSession, symbol: str, exchange: str
):
    query = select(StrategyOpenTrade).where(
        StrategyOpenTrade.symbol == symbol, StrategyOpenTrade.exchange == exchange
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def delete_open_trade_by_id(db: AsyncSession, trade_id: str):
    query = delete(StrategyOpenTrade).where(StrategyOpenTrade.id == trade_id)
    await db.execute(query)
    await db.commit()


# async def handle_signal(db: AsyncSession, signal: WebhookSignal) -> dict:
#     """
#     TradingView'den gelen sinyali işler:
#     - Raw sinyali kaydeder
#     - Pozisyon açık mı kontrol eder (borsadan)
#     - Açık değilse emir gönderir ve başarılıysa veritabanına kaydeder
#     """
#
#     # 2. Execution modülünü yükle
#     execution = load_execution_module(signal.exchange)
#
#     # 3. Açık pozisyon kontrolü
#     position_info = await execution.sync.get_open_position(signal.symbol)
#     if not position_info["success"]:
#         return {
#             "success": False,
#             "message": f"Position check failed: {position_info['message']}",
#         }
#
#     if position_info["side"] != "flat":
#         return {
#             "success": False,
#             "message": f"There is already an open position: {position_info['side']}",
#         }
#
#     # 4. Emir gönder
#     order_result = await execution.order_handler.place_order(signal)
#
#     if not order_result.get("success"):
#         return {
#             "success": False,
#             "message": f"Order failed: {order_result.get('message', 'Unknown error')}",
#             "response_data": order_result.get("data", {}),
#         }
#
#     # 5. Emir başarılıysa strategy_open_trades tablosuna yaz
#     open_trade = StrategyOpenTrade(
#         public_id=str(uuid.uuid4()),
#         symbol=signal.symbol,
#         side=signal.side,
#         entry_price=signal.entry_price,
#         position_size=signal.position_size,
#         leverage=signal.leverage,
#         exchange=signal.exchange,
#         order_type=signal.order_type,
#         opened_at=datetime.utcnow(),
#         # raw_signal_id=raw.id,
#         response_data=order_result["data"],
#     )
#     await insert_strategy_open_trade(db, open_trade)
#
#     return {
#         "success": True,
#         "message": "Position opened",
#         "public_id": open_trade.public_id,
#     }


async def delete_strategy_open_trade(db: AsyncSession, symbol: str, exchange: str):
    """
    Belirtilen sembol ve borsaya ait açık pozisyon kaydını siler.
    """
    query = delete(StrategyOpenTrade).where(
        StrategyOpenTrade.symbol == symbol, StrategyOpenTrade.exchange == exchange
    )
    await db.execute(query)
    await db.commit()
