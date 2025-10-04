#!/usr/bin/env python3
# Python 3.9
# app/exchanges/common/http/retry.py

from __future__ import annotations
import asyncio
import random
from typing import Optional, Dict, Tuple, Callable, Awaitable
import httpx

RebuildAsync = Callable[[], Awaitable[Tuple[str, Dict[str, str]]]]


async def arequest_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
    max_retries: int = 1,
    base_backoff: float = 0.2,
    jitter: float = 0.15,
    retry_on_5xx: bool = True,
    retry_on_network: bool = True,
    retry_on_binance_1021: bool = False,
    rebuild_async: Optional[RebuildAsync] = None,
    #  ) -> httpx.Response:
    **request_kwargs,  # json, data, content, params vb.
) -> httpx.Response:
    """
    Sadece güvenli senaryolarda retry yapar:
      - network (httpx.RequestError)
      - 5xx
      - (opsiyonel) Binance -1021 (timestamp) → rebuild_async() ile URL+headers yeniden üret
    """
    attempt = 0
    cur_url, cur_headers = url, (headers or {})

    while True:
        try:
            # resp = await client.request(
            #     method, cur_url, headers=cur_headers, timeout=timeout
            # )
            resp = await client.request(
                method, cur_url, headers=cur_headers, timeout=timeout, **request_kwargs
            )
            if retry_on_5xx and 500 <= resp.status_code < 600 and attempt < max_retries:
                attempt += 1
                await asyncio.sleep(
                    base_backoff * (2 ** (attempt - 1)) + random.random() * jitter
                )
                continue
            resp.raise_for_status()
            return resp

        except httpx.HTTPStatusError as e:
            if retry_on_binance_1021 and attempt < max_retries:
                try:
                    j = e.response.json()
                except Exception:
                    j = {}
                if j.get("code") == -1021 and rebuild_async is not None:
                    attempt += 1
                    await asyncio.sleep(jitter)
                    cur_url, cur_headers = await rebuild_async()
                    continue
            raise

        except httpx.RequestError:
            if retry_on_network and attempt < max_retries:
                attempt += 1
                await asyncio.sleep(
                    base_backoff * (2 ** (attempt - 1)) + random.random() * jitter
                )
                continue
            raise
