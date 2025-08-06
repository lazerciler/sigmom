#!/usr/bin/env python3
# app/exchanges/binance_futures_testnet/order_handler.py

import logging
import httpx
from urllib.parse import urlencode

from app.schemas import WebhookSignal
from .settings import BASE_URL
from .utils import (
    sign_payload,
    get_signed_headers,
    get_binance_server_time,
    adjust_quantity,
    set_leverage
)

logger = logging.getLogger(__name__)

async def place_order(signal_data: WebhookSignal) -> dict:
    """
    Binance Futures testnet üzerinde bir piyasa emri gönderir.
    """
    # Kaldıraç ayarını utils üzerinden çağır
    await set_leverage(signal_data.symbol, signal_data.leverage)
    logger.info(f"OrderHandler → Leverage çağırıldı: {signal_data.symbol} x{signal_data.leverage}")

    endpoint = "/fapi/v1/order"
    url = BASE_URL + endpoint

    symbol = signal_data.symbol.upper()
    order_type = signal_data.order_type.upper()
    quantity = await adjust_quantity(signal_data.symbol, signal_data.position_size)

    side_map = {"long": "BUY", "short": "SELL"}
    side = side_map.get(signal_data.side.lower(), signal_data.side.upper())

    server_time = await get_binance_server_time()
    params = {
        "symbol": symbol,
        "side": side,
        "type": order_type,
        "quantity": quantity,
        "timestamp": server_time,
        "recvWindow": 5000,
    }

    query_string = urlencode(sorted(params.items()))
    signature = sign_payload(params)
    full_query = f"{query_string}&signature={signature}"

    headers = get_signed_headers()
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{url}?{full_query}", headers=headers)
            response.raise_for_status()
            return {"success": True, "data": response.json()}
    except httpx.HTTPStatusError as exc:
        logger.error(f"Binance API Error {exc.response.status_code}: {exc.response.text}")
        return {"success": False, "message": exc.response.text, "data": {}}
    except Exception as e:
        logger.exception("Unexpected error occurred while placing order.")
        return {"success": False, "message": str(e), "data": {}}


async def get_position(symbol: str) -> dict:
    """
    Binance Futures pozisyon bilgilerini alır.
    """
    endpoint = "/fapi/v2/positionRisk"
    url = BASE_URL + endpoint

    server_time = await get_binance_server_time()
    params = {"symbol": symbol, "timestamp": server_time, "recvWindow": 5000}
    query_string = urlencode(sorted(params.items()))
    signature = sign_payload(params)
    full_query = f"{query_string}&signature={signature}"

    headers = get_signed_headers()
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{url}?{full_query}", headers=headers)
            response.raise_for_status()
            data = response.json()
    except Exception:
        logger.exception("Error fetching position.")
        return {}

    if isinstance(data, list):
        for p in data:
            if p.get("symbol") == symbol:
                return p
    logger.error(f"Position for {symbol} not found: {data}")
    return {}
