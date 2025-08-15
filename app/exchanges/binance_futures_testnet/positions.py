#!/usr/bin/env python3
# app/exchanges/binance_futures_testnet/positions.py

import time
import httpx
# from .settings import API_KEY, API_SECRET, BASE_URL, ENDPOINTS
from .settings import API_KEY, BASE_URL, ENDPOINTS
from .utils import sign_payload


async def get_open_positions():
    """
    Binance Futures'taki açık pozisyonları getirir (tüm semboller için).
    """
    endpoint = ENDPOINTS["POSITION_RISK"]
    url = BASE_URL + endpoint

    params = {
        "timestamp": int(time.time() * 1000),
        "recvWindow": 5000,
    }

    # query_string = "&".join(f"{key}={value}" for key, value in params.items())
    # params["signature"] = sign_payload(query_string, API_SECRET)

    params["signature"] = sign_payload(params)
    headers = {"X-MBX-APIKEY": API_KEY}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()
