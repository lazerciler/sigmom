#!/usr/bin/env python3
# app/exchanges/bybit_futures_testnet/positions.py
# Python 3.9

import httpx

from typing import Optional
from .settings import (
    BASE_URL,
    ENDPOINTS,
    HTTP_TIMEOUT_LONG,
    RECV_WINDOW_MS,
    RECV_WINDOW_LONG_MS,
)
from .utils import build_signed_get
from app.exchanges.common.http.retry import arequest_with_retry


async def get_open_positions(symbol: Optional[str] = None):
    """Bybit V5: açık pozisyonları getirir (opsiyonel sembol filtresi)."""
    url = BASE_URL + ENDPOINTS["POSITION_RISK"]
    params = {"category": "linear"}
    if symbol:
        params["symbol"] = symbol.upper()
    full_url, headers = await build_signed_get(url, params, recv_window=RECV_WINDOW_MS)
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_LONG) as client:
        response = await arequest_with_retry(
            client,
            "GET",
            full_url,
            headers=headers,
            timeout=HTTP_TIMEOUT_LONG,
            max_retries=1,
            rebuild_async=lambda: build_signed_get(
                url, params, recv_window=RECV_WINDOW_LONG_MS
            ),
        )
        response.raise_for_status()
        return response.json()
