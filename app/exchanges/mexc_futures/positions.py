#!/usr/bin/env python3
# app/exchanges/mexc_futures/positions.py
# Python 3.9

import httpx
from app.exchanges.common.http.retry import arequest_with_retry
from .settings import BASE_URL, ENDPOINTS, HTTP_TIMEOUT_LONG, RECV_WINDOW_LONG_MS
from .utils import build_signed_get


async def get_open_positions():
    url = BASE_URL + ENDPOINTS["OPEN_POSITIONS"]
    full_url, headers = await build_signed_get(url, {}, recv_window=RECV_WINDOW_LONG_MS)
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_LONG) as client:
        response = await arequest_with_retry(
            client,
            "GET",
            full_url,
            headers=headers,
            timeout=HTTP_TIMEOUT_LONG,
            max_retries=1,
        )
        response.raise_for_status()
        return response.json()
