#!/usr/bin/env python3
# app/exchanges/bybit_futures_testnet/utils.py
# Python 3.9

import logging
import httpx
import asyncio
import json
from urllib.parse import urlencode

from typing import Optional, Tuple, Dict
from decimal import Decimal, ROUND_DOWN, InvalidOperation
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
from app.config import settings
from app.exchanges.common.meta_cache import AsyncTTLCache
from app.exchanges.bybit_common.http import BybitHttp
from app.exchanges.common.http.retry import arequest_with_retry

logger = logging.getLogger(__name__)


def build_public_url(url: str, params: Dict) -> str:
    """İmzasız GET için basit query builder."""
    q = urlencode({k: v for k, v in (params or {}).items() if v is not None})
    return f"{url}?{q}" if q else url


def _normalize_symbol(sym: str) -> str:
    """BINANCE:BTCUSDT.P → BTCUSDT (TV ekleri vs.)."""
    s = str(sym or "").strip().upper()
    if ":" in s:
        s = s.split(":", 1)[1]
    if s.endswith(".P"):
        s = s[:-2]
    return s


def _get_server_time_sync() -> int:
    """Senkron serverTime (ms). Hata olursa lokal zamana düşer."""
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT_SYNC) as c:
            r = c.get(f"{BASE_URL}{ENDPOINTS['SERVER_TIME']}")
            r.raise_for_status()
            j = r.json()
            direct_time = j.get("time")
            if direct_time is not None:
                try:
                    return int(Decimal(str(direct_time)))
                except (InvalidOperation, ValueError, TypeError):
                    pass

            result = j.get("result") or {}
            nano = result.get("timeNano")
            if nano is not None:
                try:
                    return int(Decimal(str(nano)) / Decimal("1e6"))
                except (InvalidOperation, ValueError, TypeError):
                    pass

            seconds = result.get("timeSecond")
            if seconds is not None:
                try:
                    return int(Decimal(str(seconds)) * Decimal("1e3"))
                except (InvalidOperation, ValueError, TypeError):
                    pass

            return int(_time() * 1000)
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError, TypeError, KeyError):
        return int(_time() * 1000)


_HTTP = BybitHttp(
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
    window = "long" if (recv_window and recv_window > RECV_WINDOW_MS) else "short"
    endpoint = url[len(BASE_URL) :] if url.startswith(BASE_URL) else url
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    # Binance kalıbı: accountType tek noktadan otomatik eklensin
    _params = dict(params or {})
    try:
        acct = (settings.BYBIT_ACCOUNT_TYPE or "UNIFIED").upper()
        # Bybit v5: accountType sadece wallet-balance'da kullanılıyor
        if endpoint == ENDPOINTS["BALANCE"]:
            _params.setdefault("accountType", acct)
    except Exception:
        pass
    full_url, headers = _HTTP.build_get(endpoint, _params, window)
    return full_url, headers


async def build_signed_post(
    url: str,
    params: Optional[Dict] = None,
    *,
    recv_window: Optional[int] = None,
) -> Tuple[str, dict]:
    window = "long" if (recv_window and recv_window > RECV_WINDOW_MS) else "short"
    endpoint = url[len(BASE_URL) :] if url.startswith(BASE_URL) else url
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    # POST imzasında kanonik JSON ile gövdeyi imzalıyoruz → Binance ile aynı disiplin
    full_url, headers = _HTTP.build_post(endpoint, params or {}, window)
    return full_url, headers


async def build_signed_post_with_body(
    url: str,
    params: Optional[Dict] = None,
    *,
    recv_window: Optional[int] = None,
) -> Tuple[str, dict, bytes]:
    """
    Bybit POST için imzalanan **kanonik JSON gövdeyi** de döndürür; body’yi
    isteğe aynen 'content' olarak gönderin ki imza ile bire bir aynı olsun.
    """
    window = "long" if (recv_window and recv_window > RECV_WINDOW_MS) else "short"
    endpoint = url[len(BASE_URL) :] if url.startswith(BASE_URL) else url
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    full_url, headers, body = _HTTP.build_post_with_body(endpoint, params or {}, window)
    return full_url, headers, body


async def get_position_mode() -> dict:
    """Gerçek modu /v5/position/list (Bybit) üzerinden türetir."""
    url = f"{BASE_URL}{ENDPOINTS['POSITION_RISK']}"

    async def _once(params: Dict) -> dict:
        full_url, headers = await build_signed_get(
            url, params, recv_window=RECV_WINDOW_LONG_MS
        )
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as c:
            r = await arequest_with_retry(
                c,
                "GET",
                full_url,
                headers=headers,
                timeout=HTTP_TIMEOUT_SHORT,
                max_retries=1,
                rebuild_async=lambda: build_signed_get(
                    url, params, recv_window=RECV_WINDOW_LONG_MS
                ),
            )
            r.raise_for_status()
            data = r.json() or {}
            lst = (data.get("result") or {}).get("list") or []
            for row in lst:
                try:
                    if int(str(row.get("positionIdx", 0))) in (1, 2):
                        return {"success": True, "mode": "hedge", "data": data}
                except (ValueError, TypeError):
                    pass
            return {"success": True, "mode": "one_way", "data": data}

    try:
        # sembolsüz dene; boşsa BTCUSDT ile bir daha
        res = await _once({"category": "linear"})
        if res.get("data") and not (
            (res["data"].get("result") or {}).get("list") or []
        ):
            await asyncio.sleep(0.1)
            return await _once({"category": "linear", "symbol": "BTCUSDT"})
        return res
    except httpx.HTTPStatusError as exc:
        try:
            j = exc.response.json()
        except (ValueError, TypeError):
            j = {}
        if j.get("code") in (-1021, "10006"):
            logger.warning(
                "(-1021) time drift was caught; serverTime will be re-fetched and tried once."
            )
            try:
                # küçük bekleme jitter’ı (drift/clock skew ısrarını azaltır)
                await asyncio.sleep(0.15)
                return await _once({"category": "linear"})
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
    """Bybit V5: POST /v5/position/switch-mode (mode=0 one_way, 3 hedge)."""
    url = f"{BASE_URL}{ENDPOINTS['SWITCH_MODE']}"
    target = (mode or "").strip().lower()
    if target not in ("one_way", "hedge"):
        return {"success": False, "message": "invalid mode"}
    params = {"category": "linear", "mode": 0 if target == "one_way" else 3}
    full_url, headers = await build_signed_post(
        url, params, recv_window=RECV_WINDOW_LONG_MS
    )
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as c:
            body = json.dumps(params, separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
            r = await c.post(
                full_url, headers=headers, content=body, timeout=HTTP_TIMEOUT_SHORT
            )
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError:
                # taze imza ile bir kez daha dene
                full_url, headers = await build_signed_post(
                    url, params, recv_window=RECV_WINDOW_LONG_MS
                )
                body = json.dumps(params, separators=(",", ":"), sort_keys=True).encode(
                    "utf-8"
                )
                r = await c.post(
                    full_url, headers=headers, content=body, timeout=HTTP_TIMEOUT_SHORT
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
    """Bybit V5 Testnet üzerinde sembol için kaldıracı ayarlar."""
    sym = (symbol or "").upper()
    try:
        lev = max(1, min(125, int(leverage)))
    except (ValueError, TypeError):
        return {"success": False, "message": "invalid leverage"}
    endpoint = ENDPOINTS["SET_LEVERAGE"]
    url = BASE_URL + endpoint
    params = {
        "category": "linear",
        "symbol": sym,
        "buyLeverage": str(lev),
        "sellLeverage": str(lev),
    }
    full_url, headers = await build_signed_post(url, params, recv_window=RECV_WINDOW_MS)
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as client:
            body = json.dumps(params, separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
            resp = await client.post(
                full_url, headers=headers, content=body, timeout=HTTP_TIMEOUT_SHORT
            )
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                # taze imza ile bir kez daha dene
                full_url, headers = await build_signed_post(
                    url, params, recv_window=RECV_WINDOW_LONG_MS
                )
                body = json.dumps(params, separators=(",", ":"), sort_keys=True).encode(
                    "utf-8"
                )
                resp = await client.post(
                    full_url, headers=headers, content=body, timeout=HTTP_TIMEOUT_SHORT
                )
                resp.raise_for_status()
            data = resp.json()
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

# --------------------------- KLINES (public) ---------------------------
_INTERVAL_MAP = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "1h": "60",
    "4h": "240",
    "1d": "D",
}


async def get_klines(
    symbol: str,
    tf: str,  # <— router UI ‘tf’ gönderiyor; bununla uyumlu
    limit: int = 500,
    end_time: Optional[int] = None,
) -> dict:
    """
    Bybit V5 /v5/market/kline (public). UI'nin beklediği sade formatı döndürür.
    Girdi:
      - symbol: 'BTCUSDT'
      - interval: '1m','5m','15m','1h','4h','1d'
      - limit: max 1000 (Bybit)
      - end_time: ms (opsiyonel)
    Dönen:
      {"success": True, "list": [
          [open_time_ms, open, high, low, close, volume],
          ...
      ]}
    """
    iv = _INTERVAL_MAP.get(tf)
    if not iv:
        return {"success": False, "message": f"unsupported interval: {tf}"}

    url = BASE_URL + ENDPOINTS["KLINES"]
    params = {
        "category": "linear",
        "symbol": _normalize_symbol(symbol),
        "interval": iv,
        "limit": int(limit),
    }
    if end_time is not None:
        params["end"] = int(end_time)

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as client:
        full_url = build_public_url(url, params)
        r = await arequest_with_retry(
            client,
            "GET",
            full_url,
            headers=None,
            timeout=HTTP_TIMEOUT_SHORT,
            max_retries=1,
        )
        r.raise_for_status()
        data = r.json() or {}
        res = data.get("result") or {}
        rows = res.get("list") or []

        out: list[list[float]] = []
        for row in rows:
            # Bybit sırası: start, open, high, low, close, volume, turnover
            try:
                ts = int(row[0])
                open_ = float(row[1])
                high = float(row[2])
                low = float(row[3])
                close = float(row[4])
                volume = float(row[5])
            except (TypeError, ValueError, IndexError):
                continue
            out.append([ts, open_, high, low, close, volume])

        # Eski → yeni ya da yeni → eski beklentisine göre sırayı koru (Bybit yeni→eski döndürür)
        out.sort(key=lambda x: x[0])  # artan zaman
        return {"success": True, "list": out}


# ---------------------- Symbol meta cache (INSTRUMENTS_INFO) ----------------------
async def _load_exchange_info_map() -> dict[str, dict]:
    """Bybit instruments-info → {'SYMBOL': {'step': Decimal, 'min': Decimal, 'tick': Decimal}}"""
    url = f"{BASE_URL}{ENDPOINTS['INSTRUMENTS']}"
    params = {"category": "linear"}
    full_url, headers = await build_signed_get(url, params, recv_window=RECV_WINDOW_MS)
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_LONG) as client:
        resp = await arequest_with_retry(
            client,
            "GET",
            full_url,
            headers=headers,
            timeout=HTTP_TIMEOUT_LONG,
            max_retries=1,
        )
        resp.raise_for_status()
        info = resp.json() or {}
    m: dict[str, dict] = {}
    for item in (info.get("result") or {}).get("list") or []:
        sym = str(item.get("symbol") or "").upper()
        pf = item.get("priceFilter") or {}
        lot = item.get("lotSizeFilter") or {}
        step = Decimal(str(lot.get("qtyStep", "0.001")))
        mn = Decimal(str(lot.get("minOrderQty", "0.001")))
        tick = Decimal(str(pf.get("tickSize", "0.01")))
        if sym:
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
    Fiyatı priceFilter.tickSize'a göre aşağı yuvarlar (tick).
    """
    info = await _EXINFO.get()
    meta = info.get(str(symbol).upper())
    tick = meta["tick"] if meta else Decimal("0.01")
    p = _p_floor(Decimal(str(price)), tick)
    return float(p)


async def adjust_quantity(symbol: str, quantity: float) -> str:
    """
    EMİR için qty: max(minOrderQty, qty) + qtyStep'e göre quantize (string döner).
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
    "build_signed_post_with_body",
    "get_position_mode",
    "set_position_mode",
    "set_leverage",
    "get_symbol_meta_map",
    "format_quantity_text",
    "quantize_price",
    "adjust_quantity",
]
