#!/usr/bin/env python3
# app/exchanges/binance_futures_testnet/utils.py
# Python 3.9
import logging
import httpx
import hmac
import hashlib
from urllib.parse import urlencode
from decimal import Decimal, ROUND_DOWN
from time import time as _time
from .settings import API_KEY, API_SECRET, BASE_URL, ENDPOINTS

logger = logging.getLogger(__name__)


async def get_position_mode() -> dict:
    """
    Returns {"success": True, "mode": "hedge"|"one_way"} or {"success": False, ...}
    """
    url = f"{BASE_URL}{ENDPOINTS['POSITION_SIDE_DUAL']}"
    ts = await get_binance_server_time()
    params = {"timestamp": ts, "recvWindow": 5000}
    query = urlencode(sorted(params.items()))
    sig = sign_payload(params)
    headers = get_signed_headers()
    try:
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{url}?{query}&signature={sig}", headers=headers)
            r.raise_for_status()
            data = r.json()  # {"dualSidePosition": true/false or "true"/"false"}
            dual = data.get("dualSidePosition")
            if isinstance(dual, str):
                dual = dual.strip().lower() == "true"
            mode = "hedge" if bool(dual) else "one_way"
            return {"success": True, "mode": mode, "data": data}
    except httpx.HTTPStatusError as exc:
        logger.error(
            "get_position_mode HTTP %s: %s", exc.response.status_code, exc.response.text
        )
        return {"success": False, "message": exc.response.text}
    except Exception as e:
        logger.exception("get_position_mode unexpected")
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
        "recvWindow": 5000,
    }
    query = urlencode(sorted(params.items()))
    sig = sign_payload(params)
    headers = get_signed_headers()
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{url}?{query}&signature={sig}", headers=headers)
            r.raise_for_status()
            return {"success": True, "data": r.json()}
    except httpx.HTTPStatusError as exc:
        logger.error(
            "set_position_mode HTTP %s: %s", exc.response.status_code, exc.response.text
        )
        return {"success": False, "message": exc.response.text}
    except Exception as e:
        logger.exception("set_position_mode unexpected")
        return {"success": False, "message": str(e)}


async def set_leverage(symbol: str, leverage: int) -> dict:
    """Binance Futures testnet üzerinde sembol için kaldıracı ayarlar."""
    sym = (symbol or "").upper()
    try:
        lev = max(1, min(125, int(leverage)))
    except Exception:
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
    query = urlencode(sorted(params.items()))
    signature = hmac.new(
        API_SECRET.encode("utf-8"), query.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    full_query = f"{query}&signature={signature}"

    headers = {"X-MBX-APIKEY": API_KEY}
    try:
        async with httpx.AsyncClient() as client:
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
    except Exception:
        logger.exception("Unexpected error in set_leverage")
        # return {}
        return {"success": False, "message": "unexpected error"}


def sign_payload(params: dict) -> str:
    """
    Parametre sözlüğünü URL-encoded query string'e dönüştürüp HMAC SHA256 ile imzalar.
    """
    if not isinstance(params, dict):
        raise TypeError("Payload must be a dictionary.")
    query = urlencode(sorted(params.items()))
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
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        return data.get("serverTime", int(_time() * 1000))


async def adjust_quantity(symbol: str, quantity: float) -> str:
    """
    Sembolün lot adımına göre miktarı ayarlar.
    """
    url = f"{BASE_URL}{ENDPOINTS['EXCHANGE_INFO']}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        resp.raise_for_status()
        info = resp.json()

    for item in info.get("symbols", []):
        if item.get("symbol") == symbol:
            filters = {f["filterType"]: f for f in item.get("filters", [])}
            step_size = Decimal(filters["LOT_SIZE"]["stepSize"])
            min_qty = Decimal(filters["LOT_SIZE"]["minQty"])

            adjusted = max(Decimal(str(quantity)), min_qty)
            adjusted = adjusted.quantize(step_size, rounding=ROUND_DOWN)
            return format(adjusted, "f")

    raise ValueError(f"Symbol {symbol} not found in exchangeInfo")
