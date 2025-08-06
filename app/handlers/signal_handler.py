#!/usr/bin/env python3
# app/handlers/signal_handler.py

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from datetime import datetime
import uuid

from app.schemas import WebhookSignal
from app.models import StrategyOpenTrade
from app.utils.exchange_loader import load_execution_module

from crud.raw_signal import insert_raw_signal
from crud.trade import (
    insert_strategy_trade_from_open,
    get_open_trade_by_symbol_and_exchange,
    insert_strategy_open_trade,
    delete_strategy_open_trade,
)

logger = logging.getLogger(__name__)


async def handle_signal(signal_data: WebhookSignal, db: AsyncSession) -> dict:
    """
    TradingView webhook sinyalini işler.
    """
    # 1. Raw sinyali her durumda kaydet (try/except ile güvenli hale getir)
    try:
        raw_signal = await insert_raw_signal(db, signal_data)
        logger.info("Raw sinyal veritabanına kaydedildi.")
    except Exception as e:
        logger.error(f"Raw sinyal kaydı başarısız: {e}")
        raw_signal = None

    # 2. Exchange modülünü yükle
    try:
        execution = load_execution_module(signal_data.exchange)
    except Exception as e:
        logger.error(f"Borsa modülü yüklenemedi: {e}")
        raise HTTPException(status_code=400, detail="Borsa modülü yüklenemedi")

    # OPEN sinyali kısmı (signal_handler içinden)
    if signal_data.mode == "open":
        try:
            # ▶ Binance kaldıraç ayarını tetikle
            await execution.order_handler.set_leverage(
                signal_data.symbol,
                signal_data.leverage
            )
            logger.info(f"SignalHandler → Leverage çağırıldı: "
                        f"{signal_data.symbol} x{signal_data.leverage}")

            existing_trade = await get_open_trade_by_symbol_and_exchange(
                db, signal_data.symbol, signal_data.exchange
            )
            if existing_trade:
                return {"success": False, "message": "Açık pozisyon zaten var"}

            # 3) Borsaya açma emri gönder ve yanıtı al
            order_response = await execution.order_handler.place_order(signal_data)

            if not order_response.get("success"):

                return {
                    "success": False,
                    "message": "Pozisyon açılamadı",
                    "response": order_response,
                }
            exchange_order_id = order_response["data"]["orderId"]

            trade = StrategyOpenTrade(
                public_id=str(uuid.uuid4()),
                raw_signal_id=raw_signal.id if raw_signal else None,
                symbol=signal_data.symbol,
                side=signal_data.side,
                entry_price=signal_data.entry_price,
                position_size=signal_data.position_size,
                leverage=signal_data.leverage,
                order_type=signal_data.order_type,
                timestamp=datetime.utcnow(),
                unrealized_pnl=0,
                exchange=signal_data.exchange,
                fund_manager_id=signal_data.fund_manager_id,
                response_data=order_response["data"],
                exchange_order_id=exchange_order_id,
                status="pending",  # yeni alan
                exchange_verified=False,  # yeni alan
            )

            # Transaction kontrolü: zaten transaction varsa sadece ekle, yoksa yeni başlat
            if db.get_transaction() is None:
                async with db.begin():
                    await insert_strategy_open_trade(db, trade)
            else:
                await insert_strategy_open_trade(db, trade)
                await db.commit()
            # ---------------------------------

            return {
                "success": True,
                "message": "Pozisyon pending olarak kaydedildi",
                "response": order_response,
            }

        except Exception as e:
            # rollback gerekiyorsa
            if db.get_transaction() is not None:
                await db.rollback()
            logger.exception(f"OPEN işlemi başarısız: {e}")
            return {"success": False, "message": f"OPEN hatası: {e}"}

    # Close sinyal işleme mantığı

    if signal_data.mode == "close":
        try:
            # 1) Close raw sinyalini kaydet
            raw_signal = await insert_raw_signal(db, signal_data)
            logger.info("Raw sinyal veritabanına kaydedildi (close).")

            # 2) Açık pozisyonu al
            open_trade = await get_open_trade_by_symbol_and_exchange(
                db, signal_data.symbol, signal_data.exchange
            )
            if not open_trade:
                logger.info(
                    "Close sinyali geldi ama açık pozisyon yok",
                    extra={
                        "symbol": signal_data.symbol,
                        "exchange": signal_data.exchange,
                    },
                )
                return {"success": False, "message": "Açık pozisyon bulunamadı"}

            # 3) Kapama emri: side'ı tersine çevir, reduce_only flag'i koy
            if open_trade.side.lower() == "long":
                signal_data.side = "SELL"
            else:
                signal_data.side = "BUY"
            # Pydantic modeline reduce_only alanı eklediğini varsayıyorum
            signal_data.reduce_only = True

            # 4) Emir gönder
            order_response = await execution.order_handler.place_order(signal_data)
            if not order_response.get("success"):
                return {
                    "success": False,
                    "message": "Pozisyon kapatılamadı",
                    "response": order_response,
                }

            # 5) DB işlemlerini tek transaction’da yap
            if db.get_transaction() is None:
                async with db.begin():
                    await insert_strategy_trade_from_open(
                        db, open_trade, signal_data, order_response, raw_signal
                    )
                    await delete_strategy_open_trade(
                        db, open_trade.symbol, open_trade.exchange
                    )
            else:
                await insert_strategy_trade_from_open(
                    db, open_trade, signal_data, order_response, raw_signal
                )
                await delete_strategy_open_trade(
                    db, open_trade.symbol, open_trade.exchange
                )

            return {
                "success": True,
                "message": "Pozisyon kapatıldı",
                "response": order_response,
            }

        except Exception as e:
            if db.get_transaction() is not None:
                await db.rollback()
            logger.exception(f"CLOSE işlemi başarısız: {e}")
            return {"success": False, "message": f"CLOSE hatası: {e}"}
