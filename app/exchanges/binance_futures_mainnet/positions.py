#!/usr/bin/env python3
# app/exchanges/binance_futures_mainnet/positions.py

import httpx
from .settings import BASE_URL, ENDPOINTS
from .utils import sign_payload, get_binance_server_time, get_signed_headers


async def get_open_positions():
    """
    Binance Futures'taki açık pozisyonları getirir (tüm semboller için).
    """
    endpoint = ENDPOINTS["POSITION_RISK"]
    url = BASE_URL + endpoint

    params = {
        "timestamp": await get_binance_server_time(),
        "recvWindow": 5000,
    }

    params["signature"] = sign_payload(params)
    headers = get_signed_headers()

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()
