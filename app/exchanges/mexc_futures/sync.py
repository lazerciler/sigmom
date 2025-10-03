#!/usr/bin/env python3
# app/exchanges/mexc_futures/sync.py
# Python 3.9

import logging
import httpx
from app.exchanges.common.http.retry import arequest_with_retry
from .settings import BASE_URL, ENDPOINTS, HTTP_TIMEOUT_SHORT
from .utils import build_signed_get

logger = logging.getLogger(__name__)


async def get_open_position(symbol: str) -> dict:
    try:
        params = {"symbol": _to_mexc_symbol(symbol)}
        url = BASE_URL + ENDPOINTS["OPEN_POSITIONS"]
        full_url, headers = await build_signed_get(url, params)
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as client:
            resp = await arequest_with_retry(
                client,
                "GET",
                full_url,
                headers=headers,
                timeout=HTTP_TIMEOUT_SHORT,
                max_retries=1,
            )
            resp.raise_for_status()
            data = resp.json()

        rows = data.get("data") or []
        for p in rows:
            if p.get("symbol") == params["symbol"]:
                hold = float(p.get("holdVol", 0) or 0)
                side = "long" if hold > 0 else "short" if hold < 0 else "flat"
                return {
                    "success": True,
                    "symbol": p.get("symbol"),
                    "positionAmt": str(p.get("holdVol", "0")),
                    "entryPrice": str(p.get("holdAvgPrice", "0")),
                    "leverage": str(p.get("leverage", "0")),
                    "unRealizedProfit": "0",  # MEXC bu uçta mark/unrealized vermez
                    "side": side,
                }
        return {"success": False, "message": "Position not found"}
    except Exception as e:
        logger.exception("Error while fetching open position")
        return {"success": False, "message": str(e)}


def _to_mexc_symbol(symbol: str) -> str:
    s = str(symbol or "").upper()
    if s.endswith(".P"):
        s = s[:-2]
    if "_" not in s and len(s) >= 6:
        s = s[:-4] + "_" + s[-4:]
    return s
