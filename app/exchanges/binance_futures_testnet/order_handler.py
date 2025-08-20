#!/usr/bin/env python3
# app/exchanges/binance_futures_testnet/order_handler.py
# Python 3.9
import logging
import httpx
from urllib.parse import urlencode
from app.models import StrategyOpenTrade
import uuid
import asyncio
from typing import Optional

from app.schemas import WebhookSignal
from .settings import BASE_URL, ENDPOINTS, POSITION_MODE
from .utils import (
    sign_payload,
    get_signed_headers,
    get_binance_server_time,
    adjust_quantity,
    set_leverage as _utils_set_leverage,
    get_position_mode,
    set_position_mode,
)

_mode_checked_event = asyncio.Event()

logger = logging.getLogger(__name__)


async def set_leverage(symbol: str, leverage: int) -> dict:
    return await _utils_set_leverage(symbol, leverage)


async def _ensure_position_mode_once():
    if _mode_checked_event.is_set():
        return
    # Başarı olursa event set edelim; başarısızsa tekrar denesin
    success = False
    try:
        chk = await get_position_mode()
        if not chk.get("success"):
            logger.warning("Position mode check failed: %s", chk.get("message"))
            return
        actual = chk.get("mode")
        logger.info(
            "Position mode check → exchange=%s, config=%s", actual, POSITION_MODE
        )
        if actual != POSITION_MODE:
            logger.warning("Position mode mismatch → trying autoswitch...")
            sw = await set_position_mode(POSITION_MODE)
            if not sw.get("success"):
                logger.warning("Position mode autoswitch failed: %s", sw.get("message"))
                # açık pozisyon/aktif emir varsa başarısız olabilir; tekrar denememek için event'i set edebiliriz
                success = True
            else:
                logger.info("Position mode switched to %s", POSITION_MODE)
                success = True
        else:
            success = True
    finally:
        if success:
            _mode_checked_event.set()


def build_open_trade_model(
    signal_data: WebhookSignal, order_response: dict, raw_signal_id: int
) -> StrategyOpenTrade:
    return StrategyOpenTrade(
        public_id=str(uuid.uuid4()),
        raw_signal_id=raw_signal_id,
        fund_manager_id=signal_data.fund_manager_id,
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


async def place_order(
    signal_data: WebhookSignal, client_order_id: Optional[str] = None
) -> dict:
    # Hesap modunu süreçte bir kez doğrula/ayarla (async-safe)
    await _ensure_position_mode_once()

    """Binance Futures testnet üzerinde bir piyasa emri gönderir."""
    if signal_data.order_type.lower() != "market":
        raise ValueError("Limit orders are not currently supported by the system.")

    endpoint = ENDPOINTS["ORDER"]
    url = BASE_URL + endpoint

    symbol = signal_data.symbol.upper()
    order_type = "MARKET"
    quantity = await adjust_quantity(symbol, signal_data.position_size)

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
        params["reduceOnly"] = "true"
    if POSITION_MODE == "hedge":
        params["positionSide"] = "LONG" if side_in == "long" else "SHORT"
    if client_order_id:
        params["newClientOrderId"] = client_order_id

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
            "Binance API Error %s: %s", exc.response.status_code, exc.response.text
        )
        return {"success": False, "message": exc.response.text, "data": {}}
    except Exception as e:
        logger.exception("Unexpected error occurred while placing order.")
        return {"success": False, "message": str(e), "data": {}}


async def get_position(symbol: str) -> dict:
    """Binance Futures pozisyon bilgilerini alır."""
    logger.debug("📡 get_position() → %s", symbol)
    endpoint = ENDPOINTS["POSITION_RISK"]
    url = BASE_URL + endpoint

    sym = (symbol or "").upper()
    server_time = await get_binance_server_time()
    params = {"symbol": sym, "timestamp": server_time, "recvWindow": 5000}
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
            if p.get("symbol") == sym:
                return p
    logger.error("Position for %s not found: %s", sym, data)
    return {}


async def query_order_status(symbol: str, order_id: str) -> dict:
    """Binance Futures'ta bir order'ın durumunu kontrol eder."""
    try:
        endpoint = ENDPOINTS["ORDER"]
        url = BASE_URL + endpoint

        server_time = await get_binance_server_time()
        params = {
            "symbol": (symbol or "").upper(),
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
            logger.error("Binance order query failed: %s", data)
            return {"success": False, "message": data.get("msg", "Unknown error")}
    except Exception as e:
        logger.exception("An error occurred during the Binance order status query.")
        return {"success": False, "message": str(e)}
