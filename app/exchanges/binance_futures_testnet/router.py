#!/usr/bin/env python3
# app/exchanges/binance_futures_testnet/router.py

import logging
from fastapi import APIRouter, HTTPException
from .order_handler import place_order
from .positions import get_open_positions
from .account import get_account_balance
from .account import set_leverage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/binance_futures_testnet", tags=["Binance Futures Testnet"])


@router.get("/positions")
async def fetch_positions():
    """
    Açık pozisyonları getirir.
    """
    try:
        return await get_open_positions()
    except Exception as e:
        logger.exception(f"Pozisyonlar alınırken hata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/balance")
async def fetch_balance():
    """
    Hesap bakiyelerini getirir.
    """
    try:
        return await get_account_balance()
    except Exception as e:
        logger.exception(f"Bakiyeler alınırken hata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/order")
async def create_order(
    symbol: str,
    side: str,
    quantity: float,
    order_type: str = "MARKET",
    price: float = None,
):
    """
    Yeni bir emir oluşturur.
    """
    try:
        return await place_order(symbol, side, quantity, order_type, price)
    except Exception as e:
        logger.exception(f"Emir oluşturulurken hata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/leverage")
async def update_leverage(symbol: str, leverage: int):
    """
    Belirtilen sembol için kaldıraç ayarlar.
    """
    try:
        return await set_leverage(symbol, leverage)
    except Exception as e:
        logger.exception(f"Kaldıraç ayarlanırken hata: {e}")
        raise HTTPException(status_code=500, detail=str(e))
