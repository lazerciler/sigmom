#!/usr/bin/env python3
# app/exchanges/binance_futures_testnet/positions.py

import httpx

from app.exchanges.common.http.retry import arequest_with_retry
from .settings import BASE_URL, ENDPOINTS, HTTP_TIMEOUT_LONG, RECV_WINDOW_LONG_MS
from .utils import build_signed_get


async def get_open_positions():
    """
    Binance Futures'taki açık pozisyonları getirir (tüm semboller için).
    """
    endpoint = ENDPOINTS["POSITION_RISK"]
    url = BASE_URL + endpoint
    full_url, headers = await build_signed_get(url)

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_LONG) as client:
        response = await arequest_with_retry(
            client,
            "GET",
            full_url,
            headers=headers,
            timeout=HTTP_TIMEOUT_LONG,
            max_retries=1,
            retry_on_binance_1021=True,
            rebuild_async=lambda: build_signed_get(
                url, {}, recv_window=RECV_WINDOW_LONG_MS
            ),
        )
        response.raise_for_status()
        return response.json()
