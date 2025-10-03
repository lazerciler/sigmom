#!/usr/bin/env python3
# app/exchanges/mexc_futures/order_handler.py
# Python 3.9

import logging
import httpx
import uuid
import asyncio

from typing import Optional, Any

from app.exchanges.common.http.retry import arequest_with_retry
from app.exchanges.common.safety import SafetyGate
from app.models import StrategyOpenTrade
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
    get_position_mode,
    set_position_mode,
)

logger = logging.getLogger(__name__)

_GATE = SafetyGate(
    position_mode_expected=POSITION_MODE,
    get_mode=get_position_mode,
    set_mode=set_position_mode,
)

__all__ = [
    "set_leverage",
    "build_open_trade_model",
    "place_order",
    "get_position",
    "query_order_status",
    "income_breakdown",
]


# MEXC side mapping:
# 1 open long, 2 close short, 3 open short, 4 close long
def _build_param_rules(position_mode: str, mode: str, side_in: str):
    pm = (position_mode or "").lower()
    md = (mode or "").lower()
    sd = (side_in or "").lower()

    if md == "open":
        api_side = 1 if sd == "long" else 3
        reduce_only = (
            False  # MEXC: reduceOnly sadece one-way’de geçerli param; open için yok
        )
    else:  # close
        api_side = 4 if sd == "long" else 2
        reduce_only = (
            pm != "hedge"
        )  # MEXC submit’de reduceOnly only one-way için meaningful
    # positionMode paramını göndermeye gerek yok; hesap ayarı kullanılabilir
    return reduce_only, None, api_side


async def set_leverage(symbol: str, leverage: int) -> dict:
    # utils.set_leverage ile aynı imza
    from .utils import set_leverage as _set

    return await _set(symbol, leverage)


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
        exchange_order_id=str(order_response.get("data") or ""),
        status="pending",
    )


async def place_order(
    signal_data: WebhookSignal, client_order_id: Optional[str] = None
) -> dict:
    blocked, reason = _GATE.is_blocked()
    if blocked:
        return {"success": False, "message": "SAFETY_HOLD: " + reason, "data": {}}
    await _GATE.ensure_position_mode_once()
    blocked, reason = _GATE.is_blocked()
    if blocked:
        return {"success": False, "message": "SAFETY_HOLD: " + reason, "data": {}}

    if signal_data.order_type.lower() != "market":
        raise ValueError("Limit orders are not currently supported by the system.")

    endpoint = ENDPOINTS["ORDER_SUBMIT"]
    url = BASE_URL + endpoint

    symbol_in = signal_data.symbol
    quantity = await adjust_quantity(symbol_in, signal_data.position_size)

    reduce_only, _position_side_unused, api_side = _build_param_rules(
        POSITION_MODE, signal_data.mode or "", signal_data.side or ""
    )

    params: dict[str, Any] = {
        "symbol": _to_mexc_symbol(symbol_in),
        # MEXC market order: type=5, price alanı dokümana göre zorunlu → 0 gönderilebilir
        "price": 0,
        "vol": quantity,
        "side": api_side,
        "type": 5,  # market
        "openType": 2,  # 1=isolated, 2=cross (ihtiyacınıza göre)
    }
    if client_order_id:
        params["externalOid"] = client_order_id
    else:
        params["externalOid"] = f"svc-{uuid.uuid4().hex[:8]}"

    # one-way moddaysa ve kapatma emri ise reduceOnly aktifleştir
    if reduce_only:
        params["reduceOnly"] = True

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as c:
            full_url, headers = await build_signed_post(
                url, params, recv_window=RECV_WINDOW_MS
            )
            # r = await arequest_with_retry(
            #     c, "POST", full_url, headers=headers, json=params,
            #     timeout=HTTP_TIMEOUT_SHORT, max_retries=1
            # )

            # Tip uyarısını susturmak için POST'u doğrudan yapıyoruz;
            # retry helper bazı projelerde 'json' paramını tip olarak tanımlamıyor.
            r = await c.post(
                full_url, headers=headers, json=params, timeout=HTTP_TIMEOUT_SHORT
            )
            r.raise_for_status()
            data = r.json()
            return {
                "success": True,
                "data": data,
                "orderId": data.get("data"),
                "clientOrderId": params["externalOid"],
            }
    except httpx.HTTPStatusError as exc:
        logger.error(
            "MEXC API Error %s: %s", exc.response.status_code, exc.response.text
        )
        return {"success": False, "message": exc.response.text, "data": {}}
    except (httpx.RequestError, asyncio.TimeoutError) as e:
        logger.exception("Network error while placing order.")
        return {"success": False, "message": str(e), "data": {}}


def _to_mexc_symbol(symbol: str) -> str:
    s = str(symbol or "").upper().replace(":", "_").replace("-", "_")
    if s.endswith(".P"):
        s = s[:-2]
    if "_" not in s and len(s) >= 6:
        s = s[:-4] + "_" + s[-4:]
    return s


async def get_position(symbol: str, side: Optional[str] = None) -> dict:
    url = BASE_URL + ENDPOINTS["OPEN_POSITIONS"]
    try:
        params = {"symbol": _to_mexc_symbol(symbol)}
        full_url, headers = await build_signed_get(
            url, params, recv_window=RECV_WINDOW_MS
        )
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as c:
            r = await arequest_with_retry(
                c,
                "GET",
                full_url,
                headers=headers,
                timeout=HTTP_TIMEOUT_SHORT,
                max_retries=1,
            )
            r.raise_for_status()
            data = r.json() or {}
    except Exception as e:
        logger.error("Position fetch failed (%s): %s", symbol, e)
        return {}

    rows = data.get("data") or []
    if not isinstance(rows, list):
        rows = [rows]
    # side filtreleme (1=long, 2=short)
    target = None
    if (side or "").lower() in ("long", "short"):
        want = 1 if side.lower() == "long" else 2
        for p in rows:
            if not isinstance(p, dict):
                continue
            if int(p.get("positionType", 0)) == want:
                target = p
                break
    if not target:
        # non-zero holdVol varsa onu yakala
        for p in rows:
            if not isinstance(p, dict):
                continue
            try:
                if float(p.get("holdVol", 0)) != 0:
                    target = p
                    break
            except Exception:
                pass
    return target or (rows[0] if rows else {})


async def query_order_status(
    symbol: str, order_id: Optional[str] = None, client_order_id: Optional[str] = None
) -> dict:
    _ = symbol  # arayüz uyumu, IDE uyarısını sustur
    # MEXC’te tek tek sorgu için doğrudan ID ile batch_query kullanılabilir; externalOid ile ayrı uç var.
    if not order_id and not client_order_id:
        return {"success": False, "message": "order_id or client_order_id required"}

    url = BASE_URL + ENDPOINTS["ORDER_QUERY_BATCH"]
    try:
        order_ids = []
        params = {}
        if order_id:
            order_ids = [str(order_id)]
        # externalOid ile arama için "order/query" ucu yerine batch ile ID gerekiyorsa
        # önce externalOid->ID eşleyiciniz olmalı.
        # Burada sadece order_ids üzerinden ilerliyoruz.
        params["order_ids"] = ",".join(order_ids) if order_ids else ""
        full_url, headers = await build_signed_get(
            url, params, recv_window=RECV_WINDOW_MS
        )
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as c:
            r = await arequest_with_retry(
                c,
                "GET",
                full_url,
                headers=headers,
                timeout=HTTP_TIMEOUT_SHORT,
                max_retries=1,
            )
            r.raise_for_status()
            data = r.json()
            # state: 1 uninformed, 2 uncompleted, 3 completed, 4 cancelled, 5 invalid
            return {
                "success": True,
                "status": (data.get("data") or [{}])[0].get("state"),
                "data": data,
            }
    except httpx.HTTPStatusError as e:
        return {"success": False, "message": e.response.text}
    except (httpx.RequestError, asyncio.TimeoutError) as e:
        logger.error("Network error while querying order status: %s", e)
        return {"success": False, "message": str(e)}


async def income_breakdown(
    start_ms: int, end_ms: int, symbol: Optional[str] = None, limit: int = 1000
) -> dict:
    """
    Binance 'income' eşleniği MEXC’te tek uç değil; gerçekleşen PnL ve ücretler
    `order_deals` akışından elde edilebilir (profit, fee, taker/maker).
    Basit toplulaştırma uyguluyoruz.
    """
    url = BASE_URL + ENDPOINTS["ORDER_DEALS_LIST"]
    totals = {"REALIZED_PNL": 0.0, "COMMISSION": 0.0}
    page = 1
    # 'limit' paramını sayfa boyutu olarak kullan (MEXC max 100)
    try:
        page_size = max(1, min(100, int(limit)))
    except Exception:
        page_size = 100
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_LONG) as c:
            while True:
                params = {
                    "symbol": _to_mexc_symbol(symbol) if symbol else "",
                    "start_time": int(start_ms),
                    "end_time": int(end_ms),
                    "page_num": page,
                    "page_size": page_size,
                }
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
                )
                r.raise_for_status()
                j = r.json() or {}
                rows = (j.get("data") or {}).get("resultList") or []
                for it in rows:
                    try:
                        totals["REALIZED_PNL"] += float(it.get("profit") or 0.0)
                        totals["COMMISSION"] += float(it.get("fee") or 0.0) * (-1.0)
                    except Exception:
                        pass
                if len(rows) < page_size:
                    break
                page += 1
    except Exception as e:
        logger.exception("income_breakdown error: %s", e)
        return {"success": False, "net": 0.0, "sum": {}, "message": str(e)}

    net = sum(totals.values())
    return {
        "success": True,
        "net": float(net),
        "sum": {k: float(v) for k, v in totals.items()},
    }
