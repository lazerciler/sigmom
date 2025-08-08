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
from .settings import API_KEY, API_SECRET, BASE_URL

logger = logging.getLogger(__name__)

async def set_leverage(symbol: str, leverage: int) -> dict:
    """
    Binance Futures testnet üzerinde sembol için kaldıracı ayarlar.
    """
    logger.info(f"Binance API → leverage ayarı başlıyor: {symbol} x{leverage}")
    endpoint = "/fapi/v1/leverage"
    url = BASE_URL + endpoint

    # Sunucu saatini al ve parametreleri hazırla
    timestamp = await get_binance_server_time()
    params = {
        "symbol": symbol,
        "leverage": leverage,
        "timestamp": timestamp,
        "recvWindow": 7000,
    }
    # Imzalı query string oluştur
    query = urlencode(sorted(params.items()))
    signature = hmac.new(
        API_SECRET.encode('utf-8'),
        query.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    full_query = f"{query}&signature={signature}"

    headers = {"X-MBX-APIKEY": API_KEY}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{url}?{full_query}", headers=headers)
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Binance API → kaldıraç ayarı başarılı: {symbol} x{leverage}")
            return data
    except httpx.HTTPStatusError as exc:
        logger.error(f"Leverage Error {exc.response.status_code}: {exc.response.text}")
        return {}
    except Exception:
        logger.exception("Unexpected error in set_leverage")
        return {}


def sign_payload(params: dict) -> str:
    """
    Parametre sözlüğünü URL-encoded query string'e dönüştürüp HMAC SHA256 ile imzalar.
    """
    if not isinstance(params, dict):
        raise TypeError("Payload must be a dictionary.")
    query = urlencode(sorted(params.items()))
    return hmac.new(
        API_SECRET.encode('utf-8'),
        query.encode('utf-8'),
        hashlib.sha256
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
    url = f"{BASE_URL}/fapi/v1/time"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        return data.get("serverTime", int(_time() * 1000))


async def adjust_quantity(symbol: str, quantity: float) -> str:
    """
    Sembolün lot adımına göre miktarı ayarlar.
    """
    url = f"{BASE_URL}/fapi/v1/exchangeInfo"
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
            return format(adjusted, 'f')

    raise ValueError(f"Symbol {symbol} not found in exchangeInfo")
