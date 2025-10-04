#!/usr/bin/env python3
# app/exchanges/bybit_futures_testnet/order_handler.py
# Python 3.9

import logging
import httpx
import uuid
import asyncio

# import json

from app.exchanges.common.http.retry import arequest_with_retry
from app.models import StrategyOpenTrade
from typing import Optional, Any
from app.schemas import WebhookSignal
from .settings import (
    BASE_URL,
    ENDPOINTS,
    POSITION_MODE,
    RECV_WINDOW_MS,
    RECV_WINDOW_LONG_MS,
    HTTP_TIMEOUT_SHORT,
    HTTP_TIMEOUT_LONG,
)
from .utils import (
    build_signed_get,
    build_signed_post_with_body,
    adjust_quantity,
    set_leverage as _utils_set_leverage,
    get_position_mode,
    set_position_mode,
)
from app.exchanges.common.safety import SafetyGate

logger = logging.getLogger(__name__)

_GATE = SafetyGate(
    position_mode_expected=POSITION_MODE,
    get_mode=get_position_mode,
    set_mode=set_position_mode,
)
# Yalnızca dışa açmak istediğimiz semboller
__all__ = [
    "set_leverage",
    "build_open_trade_model",
    "place_order",
    "get_position",
    "query_order_status",
]


def _build_param_rules(position_mode: str, mode: str, side_in: str):
    pm = (position_mode or "").lower()
    md = (mode or "").lower()
    sd = (side_in or "").lower()
    reduce_only = md == "close" and pm != "hedge"
    api_side = (
        "Buy"
        if md != "close" and sd == "long"
        else (
            "Sell"
            if md != "close" and sd == "short"
            else "Sell" if md == "close" and sd == "long" else "Buy"
        )
    )
    position_side = None
    if pm == "hedge":
        position_side = "LONG" if sd == "long" else "SHORT"
    return reduce_only, position_side, api_side


async def set_leverage(symbol: str, leverage: int) -> dict:
    return await _utils_set_leverage(symbol, leverage)


# Geriye dönük isimler (kullanan kod varsa bozulmasın)
is_safety_hold = _GATE.is_blocked  # type: ignore
_ensure_position_mode_once = _GATE.ensure_position_mode_once  # type: ignore


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
    # Binance ile aynı akış: safety gate → params → POST → retCode kontrol
    endpoint = ENDPOINTS["ORDER"]
    url = BASE_URL + endpoint
    symbol = signal_data.symbol.upper()
    order_type = "Market"
    quantity = await adjust_quantity(symbol, signal_data.position_size)
    mode = signal_data.mode or ""
    side_in = signal_data.side or ""
    reduce_only, position_side, api_side = _build_param_rules(
        POSITION_MODE, mode, side_in
    )
    params: dict[str, Any] = {
        "category": "linear",
        "symbol": symbol,
        "side": api_side,  # 'Buy' | 'Sell'
        "orderType": order_type,  # 'Market'
        "qty": quantity,
    }
    if reduce_only:
        params["reduceOnly"] = True
    if position_side is not None:
        params["positionIdx"] = 1 if position_side == "LONG" else 2
        params.pop("reduceOnly", None)
    if client_order_id:
        params["orderLinkId"] = client_order_id
    else:
        params["orderLinkId"] = f"svc-{uuid.uuid4().hex[:8]}"
    full_url, headers, body = await build_signed_post_with_body(
        url, params, recv_window=RECV_WINDOW_MS
    )
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as client:
            response = await arequest_with_retry(
                client,
                "POST",
                full_url,
                headers=headers,
                timeout=HTTP_TIMEOUT_SHORT,
                max_retries=1,
                retry_on_binance_1021=False,
                content=body,  # ← imzalanan JSON ile bire bir aynı gövde
            )
            response.raise_for_status()
            data = response.json() or {}
            if data.get("retCode") != 0:
                return {"success": False, "message": data.get("retMsg"), "data": data}
            oid = (data.get("result") or {}).get("orderId")
            return {
                "success": True,
                "data": data,
                "orderId": oid,
                "clientOrderId": params["orderLinkId"],
            }
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Bybit API Error %s: %s", exc.response.status_code, exc.response.text
        )
        return {"success": False, "message": exc.response.text, "data": {}}
    except (httpx.RequestError, asyncio.TimeoutError) as e:
        logger.exception("Network error while placing order.")
        return {"success": False, "message": str(e), "data": {}}


async def get_position(symbol: str, side: Optional[str] = None) -> dict:
    endpoint = ENDPOINTS["POSITION_RISK"]
    url = BASE_URL + endpoint
    params = {"category": "linear", "symbol": symbol.upper()}
    full_url, headers = await build_signed_get(url, params, recv_window=RECV_WINDOW_MS)
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as client:
            response = await arequest_with_retry(
                client,
                "GET",
                full_url,
                headers=headers,
                timeout=HTTP_TIMEOUT_SHORT,
                max_retries=1,
            )
            response.raise_for_status()
            data = response.json() or {}
    except Exception as exc:
        logger.error("Position fetch failed (%s): %s", symbol, exc)
        return {}
    if not isinstance(data, dict) or data.get("retCode") != 0:
        return {}
    rows = (data.get("result") or {}).get("list") or []
    cands = [r for r in rows if str(r.get("symbol") or "").upper() == symbol.upper()]
    if not cands:
        return {}
    if POSITION_MODE == "hedge" and (side or "").lower() in ("long", "short"):
        want = "Buy" if side.lower() == "long" else "Sell"
        for r in cands:
            if (r.get("side") or "").capitalize() == want:
                return r
    # one_way: açık olanı seç
    for r in cands:
        try:
            if float(r.get("size") or 0) != 0.0:
                return r
        except (TypeError, ValueError):
            pass
    return cands[0]


async def query_order_status(
    symbol: str,
    order_id: Optional[str] = None,
    client_order_id: Optional[str] = None,
) -> dict:
    """Bybit V5'te bir order'ın durumunu kontrol eder."""
    try:
        url = BASE_URL + ENDPOINTS["ORDER_STATUS"]

        params: dict[str, Any] = {
            "category": "linear",
            "symbol": (symbol or "").upper(),
        }
        if order_id:
            params["orderId"] = order_id
        elif client_order_id:
            params["orderLinkId"] = client_order_id
        else:
            return {"success": False, "message": "order_id or client_order_id required"}

        full_url, headers = await build_signed_get(
            url, params, recv_window=RECV_WINDOW_MS
        )

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as client:
            response = await arequest_with_retry(
                client,
                "GET",
                full_url,
                headers=headers,
                timeout=HTTP_TIMEOUT_SHORT,
                max_retries=1,
                rebuild_async=lambda: build_signed_get(
                    url, params, recv_window=RECV_WINDOW_LONG_MS
                ),
            )
            response.raise_for_status()
            data = response.json()
            status = None
            lst = (
                (data.get("result") or {}).get("list")
                if isinstance(data, dict)
                else None
            )
            if isinstance(lst, list) and lst:
                status = lst[0].get("orderStatus")
            return {"success": True, "status": status, "data": data}
    except httpx.HTTPStatusError as e:
        # Non-200 yanıtları burada yakalayıp mesajı döndür
        return {
            "success": False,
            "message": e.response.text,
        }
    # Ağ hatalarını da yakala
    except (httpx.RequestError, asyncio.TimeoutError) as e:
        logger.error("Network error while querying order status: %s", e)
        return {"success": False, "message": str(e)}


# ---------------------- Borsa-onaylı Net PnL (income) ------------------------
async def income_breakdown(
    start_ms: int,
    end_ms: int,
    symbol: Optional[str] = None,
    limit: int = 1000,
) -> dict:
    """
    Bybit V5 /v5/position/closed-pnl akışını okuyup işlem tipi bazında toplar.
    Dönen 'net', borsanın verdiği tüm kapalı işlem PnL kalemlerinin toplamıdır.
    """
    endpoint = ENDPOINTS["INCOME"]
    url = BASE_URL + endpoint
    totals: dict[str, float] = {}
    cursor: Optional[str] = None
    page_limit = max(1, min(int(limit), 200))

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_LONG) as c:
            while True:
                params: dict[str, Any] = {"category": "linear", "limit": page_limit}
                if start_ms is not None:
                    params["startTime"] = int(start_ms)
                if end_ms is not None:
                    params["endTime"] = int(end_ms)
                if symbol:
                    params["symbol"] = (symbol or "").upper()
                if cursor:
                    params["cursor"] = cursor

                full_url, headers = await build_signed_get(
                    url, params, recv_window=RECV_WINDOW_LONG_MS
                )
                r = await arequest_with_retry(
                    c,
                    "GET",
                    full_url,
                    headers=headers,
                    timeout=HTTP_TIMEOUT_LONG,
                    max_retries=1,
                    retry_on_binance_1021=False,
                )
                r.raise_for_status()
                data = r.json() or {}
                result = data.get("result") if isinstance(data, dict) else None
                rows = result.get("list") if isinstance(result, dict) else None
                items = rows if isinstance(rows, list) else []
                if not items:
                    break
                for it in items:
                    try:
                        closed_pnl = float(it.get("closedPnl") or 0.0)
                    except (TypeError, ValueError):
                        closed_pnl = 0.0
                    exec_type = it.get("execType") or it.get("category") or "UNKNOWN"
                    key = str(exec_type)
                    totals[key] = totals.get(key, 0.0) + closed_pnl

                next_cursor = (
                    result.get("nextPageCursor") if isinstance(result, dict) else None
                )
                if not next_cursor:
                    break
                cursor = str(next_cursor)
    except httpx.HTTPStatusError as e:
        logger.exception("income_summary HTTP error: %s", e)
        return {"success": False, "net": 0.0, "sum": {}, "message": str(e)}
    except (httpx.RequestError, asyncio.TimeoutError) as e:
        logger.exception("income_summary network error: %s", e)
        return {"success": False, "net": 0.0, "sum": {}, "message": str(e)}

    net = sum(totals.values())

    return {
        "success": True,
        "net": float(net),
        "sum": {k: float(v) for k, v in totals.items()},
    }


# Geriye dönük uyumluluk için async alias:
# (Modül nitelikli çağrılarda kullanılabilir; __all__ içinde olmadığından
# wildcard import ile dışarı çıkmayacak.)
async def income_summary(
    start_ms: int,
    end_ms: int,
    symbol: Optional[str] = None,
    limit: int = 1000,
) -> dict:
    return await income_breakdown(start_ms, end_ms, symbol=symbol, limit=limit)
