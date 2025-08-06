#!/usr/bin/env python3
# crud/trade.py

from decimal import Decimal, InvalidOperation
import uuid
import logging
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models import StrategyOpenTrade, StrategyTrade
from app.schemas import WebhookSignal
from app.utils.exchange_loader import load_execution_module
from app.utils.position_utils import position_matches


# async def verify_pending_trades(db: AsyncSession, execution, max_retries: int = 3):
#     """
#     Pending durumdaki açık pozisyonları exchange ile doğrular.
#     Başarılıysa status="open", exchange_verified=True;
#     retry aşıldıysa status="failed".
#     """
#     # 1. Pending kayıtları çek
#     result = await db.execute(
#         select(StrategyOpenTrade).where(StrategyOpenTrade.status == "pending")
#     )
#     pending_trades = result.scalars().all()
#     logging.getLogger("verifier").info(f"   found {len(pending_trades)} pending trades")
#
#     for open_trade in pending_trades:
#         # 2. Çok sık denemeyi engelle (örn. 5 saniyeden önce yeniden deneme)
#         if open_trade.last_checked_at and (
#             datetime.utcnow() - open_trade.last_checked_at
#         ) < timedelta(seconds=5):
#             continue
#
#         # 3. Exchange’ten pozisyonu çek
#         position = await execution.order_handler.get_position(open_trade.symbol)
#
#         # Eğer veri gelmediyse, bu turu atla
#         if not position:
#             logging.getLogger("verifier") \
#                    .warning(f"Could not fetch position for {open_trade.symbol}, skipping")
#             continue
#
#         if position_matches(open_trade, position):
#             open_trade.status = "open"
#             open_trade.exchange_verified = True
#             open_trade.confirmed_at = datetime.utcnow()
#         elif open_trade.verification_attempts >= max_retries:
#             open_trade.status = "failed"
#
#         # 4. Eşleşme kontrolü (size & side & price toleransı)
#         ok_size = Decimal(str(position["positionAmt"])) == open_trade.position_size
#         ok_side = position["positionSide"].lower() == open_trade.side.lower()
#         # entry_price kontrolünü kendi toleransına göre uyarlayabilirsin
#         ok_price = abs(
#             Decimal(str(position["entryPrice"])) - open_trade.entry_price
#         ) < Decimal("0.5")
#
#         open_trade.last_checked_at = datetime.utcnow()
#         open_trade.verification_attempts += 1
#
#         if ok_size and ok_side and ok_price:
#             open_trade.status = "open"
#             open_trade.exchange_verified = True
#             open_trade.confirmed_at = datetime.utcnow()
#         elif open_trade.verification_attempts >= max_retries:
#             open_trade.status = "failed"
#
#         # 5. Değişiklikleri kaydet
#         await db.commit()
# crud/trade.py içinde:
async def verify_pending_trades(db: AsyncSession, execution, max_retries: int = 3):
    """
    Pending durumdaki açık pozisyonları exchange ile doğrular.
    Başarılıysa status="open", exchange_verified=True;
    retry aşıldıysa status="failed".
    """
    # 1. Pending kayıtları çek
    result = await db.execute(
        select(StrategyOpenTrade).where(StrategyOpenTrade.status == "pending")
    )
    pending_trades = result.scalars().all()
    verifier_logger = logging.getLogger("verifier")
    verifier_logger.info(f"   found {len(pending_trades)} pending trades")

    for open_trade in pending_trades:
        # 2. Çok sık denemeyi engelle (örn. 5 saniyeden önce yeniden deneme)
        if open_trade.last_checked_at and (
            datetime.utcnow() - open_trade.last_checked_at
        ) < timedelta(seconds=5):
            continue

        # 3. Exchange’ten pozisyonu çek
        position = await execution.order_handler.get_position(open_trade.symbol)
        verifier_logger.debug(f"[verify] Raw position response for {open_trade.symbol}: {position!r}")

        if not position:
            verifier_logger.warning(f"Could not fetch position for {open_trade.symbol}, skipping")
            continue

        # 4. Eşleşme kontrolü (position_matches helper)
        if position_matches(open_trade, position):
            open_trade.status = "open"
            open_trade.exchange_verified = True
            open_trade.confirmed_at = datetime.utcnow()
        else:
            open_trade.verification_attempts += 1
            open_trade.last_checked_at = datetime.utcnow()
            if open_trade.verification_attempts >= max_retries:
                open_trade.status = "failed"

        # 5. Değişiklikleri kaydet
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
        raise RuntimeError(f"Fiyat dönüştürme hatası: {e}")

    side = open_trade.side.lower()
    if side == "long":
        pnl_value = (exit_price - entry_price) * position_size
    else:
        pnl_value = (entry_price - exit_price) * position_size

    trade = StrategyTrade(
        public_id=str(uuid.uuid4()),
        raw_signal_id=close_raw_signal.id,  # buraya close sinyalinin raw_signal.id'si
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
    # flush edin ki open_trade.id ve diğer default değerler gelsin
    await db.flush()
    return open_trade


async def insert_strategy_trade(db: AsyncSession, signal_data, order_response: dict):
    open_trade = await get_open_trade_by_symbol_and_exchange(
        db, signal_data.symbol, signal_data.exchange
    )
    if not open_trade:
        raise RuntimeError("Close için açık pozisyon bulunamadı")

    # Fiyatları Decimal'a çevir
    try:
        entry_price = Decimal(str(open_trade.entry_price))
        exit_price = Decimal(str(getattr(signal_data, "exit_price", None)))
    except (InvalidOperation, TypeError) as e:
        raise RuntimeError(f"Fiyat dönüştürme hatası: {e}")

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


async def handle_signal(db: AsyncSession, signal: WebhookSignal) -> dict:
    """
    TradingView'den gelen sinyali işler:
    - Raw sinyali kaydeder
    - Pozisyon açık mı kontrol eder (borsadan)
    - Açık değilse emir gönderir ve başarılıysa veritabanına kaydeder
    """

    # 2. Execution modülünü yükle
    execution = load_execution_module(signal.exchange)

    # 3. Açık pozisyon kontrolü
    position_info = await execution.sync.get_open_position(signal.symbol)
    if not position_info["success"]:
        return {
            "success": False,
            "message": f"Pozisyon kontrolü başarısız: {position_info['message']}",
        }

    if position_info["side"] != "flat":
        return {
            "success": False,
            "message": f"Açık pozisyon zaten var: {position_info['side']}",
        }

    # 4. Emir gönder
    order_result = await execution.order_handler.place_order(signal)

    if not order_result.get("success"):
        return {
            "success": False,
            "message": f"Emir başarısız: {order_result.get('message', 'Bilinmeyen hata')}",
            "response_data": order_result.get("data", {}),
        }

    # 5. Emir başarılıysa strategy_open_trades tablosuna yaz
    open_trade = StrategyOpenTrade(
        public_id=str(uuid.uuid4()),
        symbol=signal.symbol,
        side=signal.side,
        entry_price=signal.entry_price,
        position_size=signal.position_size,
        leverage=signal.leverage,
        exchange=signal.exchange,
        order_type=signal.order_type,
        opened_at=datetime.utcnow(),
        # raw_signal_id=raw.id,
        response_data=order_result["data"],
    )
    await insert_strategy_open_trade(db, open_trade)

    return {
        "success": True,
        "message": "Pozisyon açıldı",
        "public_id": open_trade.public_id,
    }


async def delete_strategy_open_trade(db: AsyncSession, symbol: str, exchange: str):
    """
    Belirtilen sembol ve borsaya ait açık pozisyon kaydını siler.
    """
    query = delete(StrategyOpenTrade).where(
        StrategyOpenTrade.symbol == symbol, StrategyOpenTrade.exchange == exchange
    )
    await db.execute(query)
    await db.commit()
