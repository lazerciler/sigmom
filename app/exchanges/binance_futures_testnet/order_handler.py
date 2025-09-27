#!/usr/bin/env python3
# app/exchanges/binance_futures_testnet/order_handler.py
# Python 3.9

import logging
import httpx
import uuid
import asyncio

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
    "income_breakdown",  # dağılım/kalem kalem gelir
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

    """Binance Futures testnet üzerinde bir piyasa emri gönderir."""
    if signal_data.order_type.lower() != "market":
        raise ValueError("Limit orders are not currently supported by the system.")

    endpoint = ENDPOINTS["ORDER"]
    url = BASE_URL + endpoint
    symbol = signal_data.symbol.upper()
    order_type = "MARKET"
    quantity = await adjust_quantity(symbol, signal_data.position_size)
    mode = signal_data.mode or ""
    side_in = signal_data.side or ""
    reduce_only, position_side, api_side = _build_param_rules(
        POSITION_MODE, mode, side_in
    )

    params: dict[str, Any] = {
        "symbol": symbol,
        "side": api_side,
        "type": order_type,
        "quantity": quantity,
    }

    if reduce_only:
        params["reduceOnly"] = "true"

    if position_side is not None:
        params["positionSide"] = position_side
        # Emniyet: Hedge modda reduceOnly asla gönderilmemeli
        params.pop("reduceOnly", None)

    # clientOrderId opsiyonel → yoksa servis tarafında üret (idempotency için faydalı)
    if client_order_id:
        params["newClientOrderId"] = client_order_id
    else:
        params["newClientOrderId"] = f"svc-{uuid.uuid4().hex[:8]}"
    full_url, headers = await build_signed_post(url, params, recv_window=RECV_WINDOW_MS)

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as client:
            response = await arequest_with_retry(
                client,
                "POST",
                full_url,
                headers=headers,
                timeout=HTTP_TIMEOUT_SHORT,
                max_retries=1,
                retry_on_binance_1021=True,
                # -1021 olursa taze ts/imza ile yeniden POST hazırla
                rebuild_async=lambda: build_signed_post(
                    url, params, recv_window=RECV_WINDOW_LONG_MS
                ),
            )
            response.raise_for_status()
            data = response.json()
            # Üst katman sorgulamak isterse kimlikleri net döndür
            return {
                "success": True,
                "data": data,
                "orderId": data.get("orderId"),
                "clientOrderId": data.get("clientOrderId")
                or params.get("newClientOrderId"),
            }
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Binance API Error %s: %s", exc.response.status_code, exc.response.text
        )
        return {"success": False, "message": exc.response.text, "data": {}}
    except (httpx.RequestError, asyncio.TimeoutError) as e:
        logger.exception("Network error while placing order.")
        return {"success": False, "message": str(e), "data": {}}


async def get_position(symbol: str, side: Optional[str] = None) -> dict:
    """Binance Futures pozisyon bilgilerini alır."""
    logger.debug("get_position() → %s", symbol)
    endpoint = ENDPOINTS["POSITION_RISK"]
    url = BASE_URL + endpoint
    sym = (symbol or "").upper()

    params: dict[str, Any] = {
        "symbol": sym,
    }

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
                retry_on_binance_1021=True,
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

    if isinstance(data, list):
        # Sembol filtrele
        cands = [p for p in data if p.get("symbol") == sym]
        if not cands:
            logger.error("Position for %s not found: %s", sym, data)
            return {}
        # Hedge: doğru bacağı seç
        side_norm = (side or "").strip().lower()
        if POSITION_MODE == "hedge" and side_norm in ("long", "short"):
            target = "LONG" if side_norm == "long" else "SHORT"
            for p in cands:
                if p.get("positionSide") == target:
                    return p
        for p in cands:
            try:
                if float(p.get("positionAmt", "0")) != 0.0:
                    return p
            except (ValueError, TypeError):
                pass
        return cands[0]
    logger.error("Position for %s not found (non-list): %s", sym, data)
    return {}


async def query_order_status(
    symbol: str,
    order_id: Optional[str] = None,
    client_order_id: Optional[str] = None,
) -> dict:
    """Binance Futures'ta bir order'ın durumunu kontrol eder."""
    try:
        endpoint = ENDPOINTS["ORDER"]
        url = BASE_URL + endpoint

        params: dict[str, Any] = {"symbol": (symbol or "").upper()}
        if order_id:
            params["orderId"] = order_id
        elif client_order_id:
            params["origClientOrderId"] = client_order_id
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
                retry_on_binance_1021=True,
                rebuild_async=lambda: build_signed_get(
                    url, params, recv_window=RECV_WINDOW_LONG_MS
                ),
            )
            response.raise_for_status()
            data = response.json()
            return {"success": True, "status": data.get("status"), "data": data}
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
    Binance Futures /fapi/v1/income akışını okuyup tip bazında toplar.
    Dönen 'net', borsanın verdiği tüm gelir/masraf kalemlerinin toplamıdır:
      Net = Σ(REALIZED_PNL, COMMISSION, FUNDING_FEE, …)
    (COMMISSION genelde negatif, FUNDING_FEE pozitif/negatif olabilir.)
    """
    endpoint = ENDPOINTS.get("INCOME", "/fapi/v1/income")
    url = BASE_URL + endpoint
    totals: dict[str, float] = {}
    last = int(start_ms)

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_LONG) as c:
            while True:
                params: dict[str, Any] = {
                    "startTime": last,
                    "endTime": int(end_ms),
                    "limit": limit,
                }
                if symbol:
                    params["symbol"] = (symbol or "").upper()

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
                rows = r.json() or []
                if not rows:
                    break
                for it in rows:
                    k = str(it.get("incomeType") or "")
                    v = float(it.get("income") or 0.0)
                    totals[k] = totals.get(k, 0.0) + v
                    t = int(it.get("time") or 0)
                    if t > last:
                        last = t
                if len(rows) < limit:
                    break
                last += 1  # bir sonraki sayfa
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
