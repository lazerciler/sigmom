#!/usr/bin/env python3
# app/exchanges/binance_futures_mainnet/order_handler.py
# Python 3.9

import logging
import httpx
import time
from urllib.parse import urlencode
from app.models import StrategyOpenTrade
import uuid
import asyncio
from typing import Optional, Any
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

# _mode_checked_event = asyncio.Event()
_mode_checked_event = asyncio.Event()
# ---- SAFETY HOLD (in-memory) ----
_HOLD_UNTIL = 0.0
_HOLD_REASON = ""
_MODE_READ_RETRY = 3
_MODE_READ_DELAY = 1.0
_HOLD_SECONDS = 300  # 5 dk


def is_safety_hold() -> tuple[bool, str]:
    return (time.time() < _HOLD_UNTIL), _HOLD_REASON


def _start_hold(reason: str) -> None:
    global _HOLD_UNTIL, _HOLD_REASON
    _HOLD_UNTIL = time.time() + _HOLD_SECONDS
    _HOLD_REASON = reason
    logger.error("SAFETY HOLD %ss: %s", _HOLD_SECONDS, reason)


logger = logging.getLogger(__name__)


async def set_leverage(symbol: str, leverage: int) -> dict:
    return await _utils_set_leverage(symbol, leverage)


async def _ensure_position_mode_once():
    if _mode_checked_event.is_set():
        return

    success = False
    try:
        # 1) Modu birkaç kez dene
        last_err = ""
        chk = None
        for _ in range(_MODE_READ_RETRY):
            chk = await get_position_mode()
            if chk.get("success"):
                break
            last_err = str(chk.get("message") or "mode_read_failed")
            await asyncio.sleep(_MODE_READ_DELAY)

        # 1b) hâlâ yoksa → HOLD aç ve çık
        if not (chk and chk.get("success")):
            logger.warning("Position mode read failed (retry exhausted): %s", last_err)
            _start_hold(
                "Uncertain trading mode: unable to read mode information from exchange"
            )
            success = True  # bu süreçte tekrar denemesin diye event'i set edeceğiz
            return

        # 2) mevcut mod vs config
        actual = chk.get("mode")
        logger.info(
            "Position mode check → exchange=%s, config=%s", actual, POSITION_MODE
        )

        if actual != POSITION_MODE:
            logger.warning("Position mode mismatch → trying autoswitch.")
            sw = await set_position_mode(POSITION_MODE)
            if not sw.get("success"):
                logger.warning("Position mode autoswitch failed: %s", sw.get("message"))
                _start_hold("Belirsiz işlem modu: borsa modu config ile uyumsuz")
                success = True
                return
            logger.info("Position mode switched to %s", POSITION_MODE)
            success = True
            return

        # 3) zaten uyumlu
        success = True
        return

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

    # Hold aktifse hiç deneme
    blocked, reason = is_safety_hold()
    if blocked:
        return {"success": False, "message": "SAFETY_HOLD: " + reason, "data": {}}

    # Hesap modunu süreçte bir kez doğrula/ayarla (async-safe)
    await _ensure_position_mode_once()
    # ensure sonrası tekrar bak (bu sırada hold açılmış olabilir)
    blocked, reason = is_safety_hold()
    if blocked:
        return {"success": False, "message": "SAFETY_HOLD: " + reason, "data": {}}

    """Binance Futures mainnet üzerinde bir piyasa emri gönderir."""
    if signal_data.order_type.lower() != "market":
        raise ValueError("Limit orders are not currently supported by the system.")

    endpoint = ENDPOINTS["ORDER"]
    url = BASE_URL + endpoint
    symbol = signal_data.symbol.upper()
    order_type = "MARKET"
    quantity = await adjust_quantity(symbol, signal_data.position_size)
    mode = (signal_data.mode or "").lower()
    side_in = (signal_data.side or "").lower()
    # One-Way:  CLOSE ⇒ ters yön + reduceOnly
    # Hedge:    CLOSE ⇒ ters yön (reduceOnly YOK; Binance reddeder)
    if mode == "close":
        api_side = "SELL" if side_in == "long" else "BUY"
        reduce_only = POSITION_MODE != "hedge"
    else:
        api_side = "BUY" if side_in == "long" else "SELL"
        reduce_only = False
    server_time = await get_binance_server_time()
    params: dict[str, Any] = {
        "symbol": symbol,
        "side": api_side,
        "type": order_type,
        "quantity": quantity,
        "timestamp": server_time,
        "recvWindow": 5000,
    }
    if reduce_only and POSITION_MODE != "hedge":
        params["reduceOnly"] = "true"
    if POSITION_MODE == "hedge":
        params["positionSide"] = "LONG" if side_in == "long" else "SHORT"
        # Emniyet: Hedge modda reduceOnly asla gönderilmemeli
        params.pop("reduceOnly", None)

    if client_order_id:
        params["newClientOrderId"] = client_order_id

    query_string = urlencode(sorted((k, str(v)) for k, v in params.items()))
    signature = sign_payload(params)
    full_query = f"{query_string}&signature={signature}"
    headers = get_signed_headers()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(f"{url}?{full_query}", headers=headers)
            response.raise_for_status()
            return {"success": True, "data": response.json()}
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
    logger.debug("📡 get_position() → %s", symbol)
    endpoint = ENDPOINTS["POSITION_RISK"]
    url = BASE_URL + endpoint
    sym = (symbol or "").upper()
    server_time = await get_binance_server_time()
    params: dict[str, Any] = {
        "symbol": sym,
        "timestamp": server_time,
        "recvWindow": 5000,
    }
    query_string = urlencode(sorted((k, str(v)) for k, v in params.items()))
    signature = sign_payload(params)
    full_query = f"{query_string}&signature={signature}"
    headers = get_signed_headers()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}?{full_query}", headers=headers)
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


async def query_order_status(symbol: str, order_id: str) -> dict:
    """Binance Futures'ta bir order'ın durumunu kontrol eder."""
    try:
        endpoint = ENDPOINTS["ORDER"]
        url = BASE_URL + endpoint
        server_time = await get_binance_server_time()
        params: dict[str, Any] = {
            "symbol": (symbol or "").upper(),
            "orderId": order_id,
            "timestamp": server_time,
            "recvWindow": 5000,
        }
        query_string = urlencode(sorted((k, str(v)) for k, v in params.items()))
        signature = sign_payload(params)
        full_query = f"{query_string}&signature={signature}"
        headers = get_signed_headers()
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}?{full_query}", headers=headers)
            response.raise_for_status()
            data = response.json()
            return {"success": True, "status": data.get("status"), "data": data}
    except httpx.HTTPStatusError as e:
        # Non-200 yanıtları burada yakalayıp mesajı döndürelim
        return {
            "success": False,
            "message": e.response.text,
        }


# ---------------------- Borsa-onaylı Net PnL (income) ------------------------
async def income_summary(
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
    totals = {}
    last = int(start_ms)
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            while True:
                ts = await get_binance_server_time()
                params: dict[str, Any] = {
                    "timestamp": ts,
                    "recvWindow": 5000,
                    "startTime": last,
                    "endTime": int(end_ms),
                    "limit": limit,
                }
                if symbol:
                    params["symbol"] = (symbol or "").upper()

                q = urlencode(sorted((k, str(v)) for k, v in params.items()))
                sig = sign_payload(params)
                r = await c.get(
                    f"{url}?{q}&signature={sig}", headers=get_signed_headers()
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
