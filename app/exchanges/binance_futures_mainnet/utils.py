#!/usr/bin/env python3
# app/exchanges/binance_futures_mainnet/utils.py
# Python 3.9

import logging
import httpx
import hmac
import hashlib
from urllib.parse import urlencode
from typing import Any
from decimal import Decimal, ROUND_DOWN
from time import time as _time
import asyncio
from .settings import API_KEY, API_SECRET, BASE_URL, ENDPOINTS

logger = logging.getLogger(__name__)


async def get_position_mode() -> dict:
    """
    Returns {"success": True, "mode": "hedge"|"one_way"} or {"success": False, ...}
    """
    url = f"{BASE_URL}{ENDPOINTS['POSITION_SIDE_DUAL']}"
    headers = get_signed_headers()

    async def _once() -> dict:
        ts = await get_binance_server_time()
        # Binance Futures testnet/mainnet için recvWindow üst sınırı 60000 ms
        params: dict[str, Any] = {"timestamp": ts, "recvWindow": 30000}
        # urlencode tip uyarılarını kesmek için tüm değerleri str'e çevir
        query = urlencode(sorted((k, str(v)) for k, v in params.items()))
        sig = sign_payload(params)
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{url}?{query}&signature={sig}", headers=headers)
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
                "(-1021) time drift yakalandı; serverTime yeniden alınıp 1 kez denenecek."
            )
            try:
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
    ts = await get_binance_server_time()
    dual = (mode or "").lower() == "hedge"
    params = {
        "dualSidePosition": "true" if dual else "false",
        "timestamp": ts,
        "recvWindow": 30000,  # 5000,
    }
    query = urlencode(sorted((k, str(v)) for k, v in params.items()))
    sig = sign_payload(params)
    headers = get_signed_headers()
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.post(f"{url}?{query}&signature={sig}", headers=headers)
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
    """Binance Futures Mainnet üzerinde sembol için kaldıracı ayarlar."""
    sym = (symbol or "").upper()
    try:
        lev = max(1, min(125, int(leverage)))
    except (ValueError, TypeError):
        return {"success": False, "message": "invalid leverage"}
    logger.info("Binance API → Leverage adjustment begins: %s x%s", sym, lev)
    endpoint = ENDPOINTS["LEVERAGE"]
    url = BASE_URL + endpoint

    # Sunucu saatini al ve parametreleri hazırla
    timestamp = await get_binance_server_time()
    params = {
        "symbol": sym,
        "leverage": lev,
        "timestamp": timestamp,
        "recvWindow": 7000,
    }
    # Imzalı query string oluştur
    query = urlencode(sorted((k, str(v)) for k, v in params.items()))
    signature = hmac.new(
        API_SECRET.encode("utf-8"), query.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    full_query = f"{query}&signature={signature}"

    headers = {"X-MBX-APIKEY": API_KEY}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{url}?{full_query}", headers=headers)
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


def sign_payload(params: dict) -> str:
    """
    Parametre sözlüğünü URL-encoded query string'e dönüştürüp HMAC SHA256 ile imzalar.
    """
    if not isinstance(params, dict):
        raise TypeError("Payload must be a dictionary.")
    query = urlencode(sorted((k, str(v)) for k, v in params.items()))
    return hmac.new(
        API_SECRET.encode("utf-8"), query.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def get_signed_headers() -> dict:
    """
    Binance API anahtarını header olarak döner.
    """
    return {"X-MBX-APIKEY": API_KEY}


async def get_binance_server_time() -> int:
    """
    Binance sunucu zamanını timestamp (ms) olarak alır.
    """
    url = f"{BASE_URL}{ENDPOINTS['TIME']}"
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        return data.get("serverTime", int(_time() * 1000))


# ---------------------- Symbol meta cache (EXCHANGE_INFO) ----------------------
_EXINFO_CACHE: dict[str, dict] = {}
_EXINFO_AT: float = 0.0
_EXINFO_TTL = 900.0  # 15 dk
_EXINFO_LOCK = asyncio.Lock()


async def _ensure_exchange_info() -> dict[str, dict]:
    """
    TTL cache: {'BTCUSDT': {'step': Decimal('0.001'), 'min': Decimal('0.001')}, ...}
    """
    global _EXINFO_CACHE, _EXINFO_AT
    now = _time()
    if _EXINFO_CACHE and (now - _EXINFO_AT) < _EXINFO_TTL:
        return _EXINFO_CACHE
    async with _EXINFO_LOCK:
        # double-check
        now = _time()
        if _EXINFO_CACHE and (now - _EXINFO_AT) < _EXINFO_TTL:
            return _EXINFO_CACHE
        url = f"{BASE_URL}{ENDPOINTS['EXCHANGE_INFO']}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=6.0)
            resp.raise_for_status()
            info = resp.json()
        m: dict[str, dict] = {}
        for item in info.get("symbols", []):
            sym = str(item.get("symbol") or "").upper()
            if not sym:
                continue
            filters = {f["filterType"]: f for f in item.get("filters", [])}
            lot = filters.get("LOT_SIZE") or {}

            # step = Decimal(str(lot.get("stepSize", "0.001")))
            # mn = Decimal(str(lot.get("minQty",   "0.001")))
            # # m[sym] = {"step": step, "min": mn}
            # tick = Decimal(str(pflt.get("tickSize", "0.01")))
            # m[sym] = {"step": step, "min": mn, "tick": tick}

            # ← FİKS: PRICE_FILTER al
            pflt = filters.get("PRICE_FILTER") or {}
            step = Decimal(str(lot.get("stepSize", "0.001")))
            mn = Decimal(str(lot.get("minQty", "0.001")))
            tick = Decimal(str(pflt.get("tickSize", "0.01")))
            m[sym] = {"step": step, "min": mn, "tick": tick}

        _EXINFO_CACHE = m
        _EXINFO_AT = now
        return _EXINFO_CACHE


async def get_symbol_meta_map() -> dict[str, dict]:
    """Tüm semboller için {'step': Decimal, 'min': Decimal, 'tick': Decimal} haritası."""
    return await _ensure_exchange_info()


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
    info = await _ensure_exchange_info()
    meta = info.get(str(symbol).upper())
    if not meta:
        # tek sefer daha deneyelim (çok nadir race)
        info = await _ensure_exchange_info()
        meta = info.get(str(symbol).upper())
    step = meta["step"] if meta else Decimal("0.001")
    sign = "-" if float(quantity) < 0 else ""
    q = _q_floor(abs(Decimal(str(quantity))), step)
    return sign + format(q, "f")


async def quantize_price(symbol: str, price: float) -> float:
    """
    Fiyatı PRICE_FILTER.tickSize'a göre aşağı yuvarlar (tick)
    """
    info = await _ensure_exchange_info()
    meta = info.get(str(symbol).upper())
    tick = meta["tick"] if meta else Decimal("0.01")
    p = _p_floor(Decimal(str(price)), tick)
    return float(p)


async def adjust_quantity(symbol: str, quantity: float) -> str:
    """
    EMİR için miktarı ayarlar: max(minQty, qty) + stepSize'a göre quantize.
    trailing zero korunarak string döner.
    """
    info = await _ensure_exchange_info()
    meta = info.get(str(symbol).upper())
    if not meta:
        # cache tazele ve bir daha dene
        _EXINFO_CACHE.clear()
        info = await _ensure_exchange_info()
        meta = info.get(str(symbol).upper())
        if not meta:
            raise ValueError(f"Symbol {symbol} not found in exchangeInfo")
    step = meta["step"]
    mn = meta["min"]
    q = max(Decimal(str(quantity)), mn)
    q = _q_floor(q, step)
    return format(q, "f")
