#!/usr/bin/env python3
# app/exchanges/binance_futures_testnet/utils.py
# Python 3.9

import logging
import httpx
import asyncio

from typing import Optional, Tuple, Dict
from decimal import Decimal, ROUND_DOWN
from time import time as _time
from .settings import (
    API_KEY,
    API_SECRET,
    BASE_URL,
    ENDPOINTS,
    RECV_WINDOW_MS,
    RECV_WINDOW_LONG_MS,
    HTTP_TIMEOUT_SYNC,
    HTTP_TIMEOUT_SHORT,
    HTTP_TIMEOUT_LONG,
)
from app.exchanges.common.meta_cache import AsyncTTLCache
from app.exchanges.binance_common.http import BinanceHttp
from app.exchanges.common.http.retry import arequest_with_retry

logger = logging.getLogger(__name__)


def _get_server_time_sync() -> int:
    """Senkron serverTime (ms). Hata olursa lokal zamana düşer."""
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT_SYNC) as c:
            r = c.get(f"{BASE_URL}{ENDPOINTS['TIME']}")
            r.raise_for_status()
            j = r.json()
            st = j.get("serverTime")
            return int(st) if st is not None else int(_time() * 1000)
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError, TypeError, KeyError):
        return int(_time() * 1000)


_HTTP = BinanceHttp(
    base_url=BASE_URL,
    api_key=API_KEY,
    api_secret=API_SECRET,
    get_server_time=_get_server_time_sync,
    recv_window_short_ms=RECV_WINDOW_MS,
    recv_window_long_ms=RECV_WINDOW_LONG_MS,
)


async def build_signed_get(
    url: str,
    params: Optional[Dict] = None,
    *,
    recv_window: Optional[int] = None,
) -> Tuple[str, dict]:
    """İmzalı GET için tam URL + header (binanceHttp çekirdeği üzerinden)."""
    window = "long" if (recv_window and recv_window > RECV_WINDOW_MS) else "short"
    endpoint = url[len(BASE_URL) :] if url.startswith(BASE_URL) else url
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    full_url, headers = _HTTP.build_get(endpoint, params or {}, window)
    return full_url, headers


async def build_signed_post(
    url: str,
    params: Optional[Dict] = None,
    *,
    recv_window: Optional[int] = None,
) -> Tuple[str, dict]:
    """İmzalı POST için tam URL + header (binanceHttp çekirdeği üzerinden)."""
    window = "long" if (recv_window and recv_window > RECV_WINDOW_MS) else "short"
    endpoint = url[len(BASE_URL) :] if url.startswith(BASE_URL) else url
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    full_url, headers = _HTTP.build_post(endpoint, params or {}, window)
    return full_url, headers


async def get_position_mode() -> dict:
    """
    Returns {"success": True, "mode": "hedge"|"one_way"} or {"success": False, ...}
    """
    url = f"{BASE_URL}{ENDPOINTS['POSITION_SIDE_DUAL']}"

    async def _once() -> dict:
        # İmzalı URL ve header'ları ortak çekirdek hazırlasın
        full_url, headers = await build_signed_get(
            url, {}, recv_window=RECV_WINDOW_LONG_MS
        )

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as c:
            r = await arequest_with_retry(
                c,
                "GET",
                full_url,
                headers=headers,
                timeout=HTTP_TIMEOUT_SHORT,
                max_retries=1,
                retry_on_binance_1021=True,
                rebuild_async=lambda: build_signed_get(
                    url, {}, recv_window=RECV_WINDOW_LONG_MS
                ),
            )
            r.raise_for_status()
            data = r.json()
            dual = data.get("dualSidePosition")
            if isinstance(dual, str):
                dual = dual.strip().lower() == "true"
            mode = "hedge" if bool(dual) else "one_way"
            return {"success": True, "mode": mode, "data": data}

    try:
        return await _once()
    except httpx.HTTPStatusError as exc:
        try:
            j = exc.response.json()
        except (ValueError, TypeError):
            j = {}
        if j.get("code") == -1021:
            logger.warning(
                "(-1021) time drift was caught; serverTime will be re-fetched and tried once."
            )
            try:
                # küçük bekleme jitter’ı (drift/clock skew ısrarını azaltır)
                await asyncio.sleep(0.15)
                return await _once()
            except (
                httpx.HTTPStatusError,
                httpx.RequestError,
                asyncio.TimeoutError,
                ValueError,
                TypeError,
            ):
                pass
        logger.error(
            "get_position_mode HTTP %s: %s", exc.response.status_code, exc.response.text
        )
        return {"success": False, "message": exc.response.text}
    except (httpx.RequestError, asyncio.TimeoutError, ValueError, TypeError) as e:
        logger.exception("get_position_mode unexpected: %s", e)
        return {"success": False, "message": str(e)}


async def set_position_mode(mode: str) -> dict:
    """
    POST set dualSidePosition (hedge=true / one_way=false)
    """
    url = f"{BASE_URL}{ENDPOINTS['POSITION_SIDE_DUAL']}"
    dual = (mode or "").lower() == "hedge"
    params = {"dualSidePosition": "true" if dual else "false"}
    full_url, headers = await build_signed_post(
        url, params, recv_window=RECV_WINDOW_LONG_MS
    )

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as c:
            r = await arequest_with_retry(
                c,
                "POST",
                full_url,
                headers=headers,
                timeout=HTTP_TIMEOUT_SHORT,
                max_retries=1,
                retry_on_binance_1021=True,
                rebuild_async=lambda: build_signed_post(
                    url, params, recv_window=RECV_WINDOW_LONG_MS
                ),
            )
            r.raise_for_status()
            return {"success": True, "data": r.json()}
    except httpx.HTTPStatusError as exc:
        logger.error(
            "set_position_mode HTTP %s: %s", exc.response.status_code, exc.response.text
        )
        return {"success": False, "message": exc.response.text}
    except (httpx.RequestError, asyncio.TimeoutError, ValueError, TypeError) as e:
        logger.exception("set_position_mode unexpected: %s", e)
        return {"success": False, "message": str(e)}


async def set_leverage(symbol: str, leverage: int) -> dict:
    """Binance Futures Testnet üzerinde sembol için kaldıracı ayarlar."""
    sym = (symbol or "").upper()
    try:
        lev = max(1, min(125, int(leverage)))
    except (ValueError, TypeError):
        return {"success": False, "message": "invalid leverage"}
    logger.info("Binance API → Leverage adjustment begins: %s x%s", sym, lev)
    endpoint = ENDPOINTS["LEVERAGE"]
    url = BASE_URL + endpoint
    params = {"symbol": sym, "leverage": lev}
    full_url, headers = await build_signed_post(url, params, recv_window=RECV_WINDOW_MS)
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as client:
            resp = await arequest_with_retry(
                client,
                "POST",
                full_url,
                headers=headers,
                timeout=HTTP_TIMEOUT_SHORT,
                max_retries=1,
                retry_on_binance_1021=True,
                # -1021 olursa taze ts/imza ile yeniden hazırla
                rebuild_async=lambda: build_signed_post(
                    url, params, recv_window=RECV_WINDOW_LONG_MS
                ),
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(
                "Binance API → Leverage adjustment successful: %s x%s", sym, lev
            )
            return {"success": True, "data": data}

    except httpx.HTTPStatusError as exc:
        logger.error(
            "Leverage Error %s: %s", exc.response.status_code, exc.response.text
        )
        return {"success": False, "message": exc.response.text}
    except (httpx.RequestError, asyncio.TimeoutError, ValueError, TypeError) as e:
        logger.exception("Unexpected error in set_leverage: %s", e)
        return {"success": False, "message": str(e)}


# (Not) Eski 3 yardımcı kaldırıldı; sign_payload/get_signed_headers/get_binance_server_time
# imza/headers/zaman işleri artık BinanceHttp üzerinden yönetiliyor.


# ---------------------- Symbol meta cache (EXCHANGE_INFO) ----------------------
async def _load_exchange_info_map() -> dict[str, dict]:
    """
    Binance exchangeInfo → {'SYMBOL': {'step': Decimal, 'min': Decimal, 'tick': Decimal}}
    """
    url = f"{BASE_URL}{ENDPOINTS['EXCHANGE_INFO']}"
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_LONG) as client:
        resp = await arequest_with_retry(
            client,
            "GET",
            url,
            timeout=HTTP_TIMEOUT_LONG,
            max_retries=1,
        )
        resp.raise_for_status()
        info = resp.json()
    m: dict[str, dict] = {}
    for item in info.get("symbols", []):
        sym = str(item.get("symbol") or "").upper()
        if not sym:
            continue
        filters = {f["filterType"]: f for f in item.get("filters", [])}
        lot = filters.get("LOT_SIZE") or {}
        pflt = filters.get("PRICE_FILTER") or {}
        step = Decimal(str(lot.get("stepSize", "0.001")))
        mn = Decimal(str(lot.get("minQty", "0.001")))
        tick = Decimal(str(pflt.get("tickSize", "0.01")))
        m[sym] = {"step": step, "min": mn, "tick": tick}
    return m


_EXINFO = AsyncTTLCache(ttl=900.0, loader=_load_exchange_info_map)


async def get_symbol_meta_map() -> dict[str, dict]:
    return await _EXINFO.get()


def _q_floor(value: Decimal, step: Decimal) -> Decimal:
    return value.quantize(step, rounding=ROUND_DOWN)


def _p_floor(value: Decimal, tick: Decimal) -> Decimal:
    return value.quantize(tick, rounding=ROUND_DOWN)


async def format_quantity_text(symbol: str, quantity: float) -> str:
    """
    GÖSTERİM için miktarı borsa LOT_SIZE.stepSize'a göre quantize edip
    trailing zero korunarak string döndürür. (minQty ile kıstırma yapmaz.)
    Örn: 0.12 -> "0.120"
    """
    info = await _EXINFO.get()
    meta = info.get(str(symbol).upper())
    if not meta:
        # tek sefer daha deneyelim (çok nadir yarış)
        info = await _EXINFO.get()
        meta = info.get(str(symbol).upper())
    step = meta["step"] if meta else Decimal("0.001")
    sign = "-" if float(quantity) < 0 else ""
    q = _q_floor(abs(Decimal(str(quantity))), step)
    return sign + format(q, "f")


async def quantize_price(symbol: str, price: float) -> float:
    """
    Fiyatı PRICE_FILTER.tickSize'a göre aşağı yuvarlar (tick)
    """
    info = await _EXINFO.get()
    meta = info.get(str(symbol).upper())
    tick = meta["tick"] if meta else Decimal("0.01")
    p = _p_floor(Decimal(str(price)), tick)
    return float(p)


async def adjust_quantity(symbol: str, quantity: float) -> str:
    """
    EMİR için miktarı ayarlar: max(minQty, qty) + stepSize'a göre quantize.
    trailing zero korunarak string döner.
    """
    info = await _EXINFO.get()
    meta = info.get(str(symbol).upper())
    if not meta:
        # cache tazele ve bir daha dene
        _EXINFO.clear()
        info = await _EXINFO.get()
        meta = info.get(str(symbol).upper())
        if not meta:
            raise ValueError(f"Symbol {symbol} not found in exchangeInfo")
    step = meta["step"]
    mn = meta["min"]
    q = max(Decimal(str(quantity)), mn)
    q = _q_floor(q, step)
    return format(q, "f")


__all__ = [
    "build_signed_get",
    "build_signed_post",
    "get_position_mode",
    "set_position_mode",
    "set_leverage",
    "get_symbol_meta_map",
    "format_quantity_text",
    "quantize_price",
    "adjust_quantity",
]
