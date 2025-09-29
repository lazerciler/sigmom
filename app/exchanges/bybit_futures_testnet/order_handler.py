#!/usr/bin/env python3
# app/exchanges/bybit_futures_testnet/order_handler.py
# Python 3.9

import logging
import httpx
import uuid
import asyncio
import json

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
    build_signed_post,
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
    """
    Saf kural fonksiyonu:
      - one_way + close  → reduceOnly=true, positionSide=None, side=ters
      - hedge   + open   → reduceOnly yok, positionSide=LONG/SHORT, side=doğru
      - hedge   + close  → reduceOnly yok, positionSide=LONG/SHORT, side=ters
      - one_way + open   → reduceOnly yok, positionSide=None, side=doğru
    Dönen değerler: (reduce_only: bool, position_side: str|None, api_side: 'BUY'|'SELL')
    """
    pm = (position_mode or "").lower()
    md = (mode or "").lower()
    sd = (side_in or "").lower()

    reduce_only = md == "close" and pm != "hedge"
    if md == "close":
        api_side = "SELL" if sd == "long" else "BUY"
    else:
        api_side = "BUY" if sd == "long" else "SELL"

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
    # Hesap modunu süreçte bir kez doğrula/ayarla (async-safe)
    # Hold aktifse hiç deneme
    blocked, reason = _GATE.is_blocked()
    if blocked:
        return {"success": False, "message": "SAFETY_HOLD: " + reason, "data": {}}

    # Hesap modunu süreçte bir kez doğrula/ayarla (async-safe)
    await _GATE.ensure_position_mode_once()
    # ensure sonrası tekrar bak (bu sırada hold açılmış olabilir)
    blocked, reason = _GATE.is_blocked()
    if blocked:
        return {"success": False, "message": "SAFETY_HOLD: " + reason, "data": {}}

    """Bybit V5 testnet üzerinde bir piyasa emri gönderir."""
    if signal_data.order_type.lower() != "market":
        raise ValueError("Limit orders are not currently supported by the system.")

    url = BASE_URL + ENDPOINTS["ORDER"]
    symbol = signal_data.symbol.upper()
    quantity = await adjust_quantity(symbol, signal_data.position_size)
    mode = signal_data.mode or ""
    side_in = signal_data.side or ""
    reduce_only, position_side, api_side = _build_param_rules(
        POSITION_MODE, mode, side_in
    )

    params: dict[str, Any] = {
        "category": "linear",
        "symbol": symbol,
        "side": "Buy" if api_side == "BUY" else "Sell",
        "orderType": "Market",
        "qty": str(quantity),
    }

    if reduce_only:
        params["reduceOnly"] = True

    if position_side is not None:
        # Bybit hedge modunda bacak → positionIdx: 1=LONG, 2=SHORT
        params["positionIdx"] = 1 if position_side == "LONG" else 2
        # Emniyet: hedge modda reduceOnly göndermeyelim
        params.pop("reduceOnly", None)

    # clientOrderId opsiyonel → yoksa servis tarafında üret (idempotency için faydalı)
    if client_order_id:
        params["orderLinkId"] = client_order_id
    else:
        params["orderLinkId"] = f"svc-{uuid.uuid4().hex[:8]}"
    full_url, headers = await build_signed_post(url, params, recv_window=RECV_WINDOW_MS)

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as client:
            # body = json.dumps(params).encode("utf-8")

            # Gönderilecek gövdeyi kanonik JSON olarak üret (imza ile birebir)
            body = json.dumps(params, separators=(",", ":"), ensure_ascii=False).encode(
                "utf-8"
            )
            headers["Content-Type"] = "application/json"
            # 1. deneme
            response = await client.post(
                full_url, headers=headers, content=body, timeout=HTTP_TIMEOUT_SHORT
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                # 2. deneme: taze imza/ts ile yeniden hazırla
                full_url, headers = await build_signed_post(
                    url, params, recv_window=RECV_WINDOW_LONG_MS
                )
                # body = json.dumps(params).encode("utf-8")

                # Gövde ve Content-Type aynı kalsın (kanonik JSON)
                body = json.dumps(
                    params, separators=(",", ":"), ensure_ascii=False
                ).encode("utf-8")
                headers["Content-Type"] = "application/json"
                response = await client.post(
                    full_url, headers=headers, content=body, timeout=HTTP_TIMEOUT_SHORT
                )
                response.raise_for_status()
            data = response.json()
            # Üst katman sorgulamak isterse kimlikleri net döndür
            return {
                "success": True,
                "data": data,
                "orderId": (data.get("result") or {}).get("orderId"),
                "clientOrderId": (data.get("result") or {}).get("orderLinkId")
                or params.get("orderLinkId"),
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
    """Bybit V5 pozisyon bilgilerini alır."""
    logger.debug("get_position() → %s", symbol)
    url = BASE_URL + ENDPOINTS["POSITION_RISK"]
    sym = (symbol or "").upper()

    params: dict[str, Any] = {"category": "linear", "symbol": sym}

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
                rebuild_async=lambda: build_signed_get(
                    url, params, recv_window=RECV_WINDOW_LONG_MS
                ),
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Position fetch failed (%s): %s %s",
            sym,
            exc.response.status_code,
            exc.response.text,
        )
        return {}
    except (httpx.RequestError, asyncio.TimeoutError) as exc:
        logger.error("Network error while fetching position %s: %s", sym, exc)
        return {}

    # Bybit V5: {"result":{"list":[...]}}
    lst = (data.get("result") or {}).get("list") if isinstance(data, dict) else None
    rows = lst if isinstance(lst, list) else []
    if not rows:
        logger.error("Position for %s not found: %s", sym, data)
        return {}
    side_norm = (side or "").strip().lower()
    if POSITION_MODE == "hedge" and side_norm in ("long", "short"):
        want_idx = 1 if side_norm == "long" else 2
        for p in rows:
            if int(str(p.get("positionIdx", 0))) == want_idx:
                return p
    for p in rows:
        try:
            if float(p.get("size", "0")) != 0.0:
                return p
        except (ValueError, TypeError):
            pass
    return rows[0]


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
