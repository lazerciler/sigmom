#!/usr/bin/env python3
# app/handlers/signal_handler.py
# Python 3.9
import logging
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict
# from decimal import Decimal
from app.schemas import WebhookSignal
from app.utils.exchange_loader import load_execution_module
from crud.raw_signal import insert_raw_signal
from crud.trade import (
    insert_strategy_open_trade,
    get_open_trade_for_close,
    close_open_trade_and_record
)
#    close_trade_and_record,

logger = logging.getLogger(__name__)


async def handle_signal(signal_data: WebhookSignal, db: AsyncSession) -> dict:
    logger.info(f"Signal received: {signal_data}")
    logger.info(f"Order type: {signal_data.order_type}")

    if signal_data.order_type.lower() != "market":
        logger.warning("Only market orders are supported. The transaction was rejected.")
        raise HTTPException(
            status_code=400,
            detail="Limit orders are not currently supported by the system.",
        )

    # Borsa modülünü yükle
    try:
        execution = load_execution_module(signal_data.exchange)
    except Exception as e:
        logger.exception("Exchange module failed to load")
        raise HTTPException(status_code=400, detail=str(e))

    # Raw sinyali kaydet
    raw_signal = await insert_raw_signal(db, signal_data)
    logger.info("The received raw signal was recorded.")

    # OPEN
    if signal_data.mode == "open":
        try:
            if signal_data.leverage is not None:
                await execution.order_handler.set_leverage(signal_data.symbol, signal_data.leverage)
                logger.info(f"Leverage adjustment successfully: {signal_data.symbol} x{signal_data.leverage}")
            else:
                logger.debug(f"Leverage skipped (None): {signal_data.symbol}")

            # Emir gönder
            order_result = await execution.order_handler.place_order(signal_data)

            if not order_result.get("success"):
                logger.error(f"OPEN order failed: {order_result}")
                return {
                    "success": False,
                    "message": f"Opening order failed: {order_result.get('message', 'Unknown error')}",
                    "response_data": order_result.get("data", {}),
                }

            # Açık pozisyonu DB'ye kaydet
            open_trade = await insert_strategy_open_trade(
                db=db,
                open_trade=execution.order_handler.build_open_trade_model(
                    signal_data=signal_data,
                    order_response=order_result,
                    raw_signal_id=raw_signal.id,
                ),
            )
            await db.commit()
            return {
                "success": True,
                "message": "The position was opened and recorded.",
                "public_id": open_trade.public_id,
            }

        except Exception as e:
            logger.exception(f"OPEN operation failed: {e}")
            return {"success": False, "message": f"OPEN error: {e}"}

    # CLOSE
    elif signal_data.mode == "close":
        logger.info(f"CLOSE signal received → {signal_data.symbol} | {signal_data.exchange}")

        # 1) Kapatılacak open trade’i güvenli seç
        open_trade = await get_open_trade_for_close(
            db=db,
            public_id=signal_data.public_id,  # sinyalde yoksa None gelir
            symbol=signal_data.symbol,
            exchange=signal_data.exchange,
        )
        if open_trade is None:
            logger.error("[CLOSE] No matching open position found (if there is no public id, "
                         "the last open record is checked).")
            return {"success": False, "message": "No open positions were found to be closed."}

        # 2) Close emrini gönder (LEVERAGE YOK!)
        order_result = await execution.order_handler.place_order(signal_data)
        if not order_result.get("success"):
            logger.error(f"[CLOSE] Order failed: {order_result}")
            return {
                "success": False,
                "message": f"Close order failed: {order_result.get('message', 'Unknown error')}",
                "response_data": order_result.get("data", {}),
            }

        # 3) Anında borsadan pozisyonu kontrol et
        try:
            position = await execution.order_handler.get_position(signal_data.symbol)
        except Exception as e:
            logger.warning(f"[CLOSE] get_position exception: {e}")
            position = None

        from decimal import Decimal

        def _amt(pos: Optional[Dict]) -> Decimal:
            return Decimal(str((pos or {}).get("positionAmt", "0"))).copy_abs()

        if position and _amt(position) == 0:
            # Anında kapanış: kalıcı trade’e taşı, open’dan sil
            await close_open_trade_and_record(db, open_trade, position)
            return {
                "success": True,
                "message": "Position closed and recorded.",
                "public_id": open_trade.public_id,
            }

        # 4) Hemen kapanmadıysa: verifier izleyecek
        await db.commit()
        return {
            "success": True,
            "message": "The closing order has been sent. It will be recorded once the exchange confirms the closing.",
            "public_id": open_trade.public_id,
        }
