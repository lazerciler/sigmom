#!/usr/bin/env python3
# app/exchanges/binance_futures_testnet/order_handler.py
# Python 3.9
import logging
import httpx
from urllib.parse import urlencode
from app.models import StrategyOpenTrade
import uuid

from app.schemas import WebhookSignal
from .settings import BASE_URL, ENDPOINTS
from .utils import (
    sign_payload,
    get_signed_headers,
    get_binance_server_time,
    adjust_quantity,
)

logger = logging.getLogger(__name__)


def build_open_trade_model(
    signal_data, order_response, raw_signal_id: int
) -> StrategyOpenTrade:
    return StrategyOpenTrade(
        public_id=str(uuid.uuid4()),
        raw_signal_id=raw_signal_id,
        fund_manager_id=signal_data.fund_manager_id,  # ✅ burası eklendi
        symbol=signal_data.symbol,
        side=signal_data.side,
        entry_price=signal_data.entry_price,
        position_size=signal_data.position_size,
        leverage=signal_data.leverage,
        order_type=signal_data.order_type,
        timestamp=signal_data.timestamp,
        exchange=signal_data.exchange,
        exchange_order_id=order_response.get("data", {}).get("orderId", ""),
        status="pending",
    )


async def place_order(signal_data: WebhookSignal) -> dict:
    """
    Binance Futures testnet üzerinde bir piyasa emri gönderir.
    """
    order_type = signal_data.order_type.lower()
    if order_type != "market":
        raise ValueError("Limit orders are not currently supported by the system.")

    endpoint = ENDPOINTS["ORDER"]
    url = BASE_URL + endpoint

    symbol = signal_data.symbol.upper()
    order_type = signal_data.order_type.upper()  # MARKET
    quantity = await adjust_quantity(signal_data.symbol, signal_data.position_size)

    mode = (signal_data.mode or "").lower()
    side_in = (signal_data.side or "").lower()
    # OPEN → aynı yön, CLOSE → ters yön + reduceOnly
    if mode == "close":
        api_side = "SELL" if side_in == "long" else "BUY"
        reduce_only = True
    else:
        api_side = "BUY" if side_in == "long" else "SELL"
        reduce_only = False

    server_time = await get_binance_server_time()
    params = {
        "symbol": symbol,
        "side": api_side,
        "type": order_type,
        "quantity": quantity,
        "timestamp": server_time,
        "recvWindow": 5000,
    }
    if reduce_only:
        # Binance reduceOnly paramı futures için destekli; bool True yerine "true" güvenli tercih
        params["reduceOnly"] = "true"

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
        logger.error(
            f"Binance API Error {exc.response.status_code}: {exc.response.text}"
        )
        return {"success": False, "message": exc.response.text, "data": {}}
    except Exception as e:
        logger.exception("Unexpected error occurred while placing order.")
        return {"success": False, "message": str(e), "data": {}}


async def get_position(symbol: str) -> dict:
    # logger = logging.getLogger("verifier")
    logger.debug(f"📡 get_position() çağrıldı → {symbol}")
    """
    Binance Futures pozisyon bilgilerini alır.
    """
    endpoint = ENDPOINTS["POSITION_RISK"]
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


async def query_order_status(symbol: str, order_id: str) -> dict:
    """
    Binance Futures'ta bir order'ın durumunu kontrol eder.
    """
    try:
        endpoint = ENDPOINTS["ORDER"]
        url = BASE_URL + endpoint

        server_time = await get_binance_server_time()
        params = {
            "symbol": symbol.upper(),
            "orderId": order_id,
            "timestamp": server_time,
            "recvWindow": 5000,
        }

        query_string = urlencode(sorted(params.items()))
        signature = sign_payload(params)
        full_query = f"{query_string}&signature={signature}"
        headers = get_signed_headers()

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{url}?{full_query}", headers=headers)
            data = response.json()

        if response.status_code == 200:
            return {"success": True, "status": data.get("status"), "data": data}
        else:
            logger.error(f"Binance order query failed: {data}")
            return {"success": False, "message": data.get("msg", "Unknown error")}

    except Exception as e:
        logger.exception("An error occurred during the Binance order status query.")
        return {"success": False, "message": str(e)}
