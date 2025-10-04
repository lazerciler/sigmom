#!/usr/bin/env python3
# app/exchanges/bybit_futures_testnet/sync.py
# Python 3.9

import logging
import httpx
from app.exchanges.common.http.retry import arequest_with_retry
from .settings import BASE_URL, ENDPOINTS, HTTP_TIMEOUT_SHORT
from .utils import build_signed_get
from decimal import Decimal

logger = logging.getLogger(__name__)


async def get_open_position(symbol: str) -> dict:
    """
    Bybit Futures Testnet üzerinde verilen sembol için açık pozisyonu getirir.
    DÖNÜŞ: Binance sync.get_open_position ile aynı sözleşme.
    """
    ep = ENDPOINTS["POSITION_RISK"]
    params = {
        "category": "linear",
        "symbol": symbol.upper(),
    }  # accountType utils'den gelir
    full_url, headers = await build_signed_get(f"{BASE_URL}{ep}", params)

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as client:
            resp = await arequest_with_retry(
                client,
                "GET",
                full_url,
                headers=headers,
                timeout=HTTP_TIMEOUT_SHORT,
                max_retries=1,
                retry_on_binance_1021=False,
            )
            resp.raise_for_status()
            data = resp.json() or {}
    except Exception as e:
        logger.exception("Error while fetching open position")
        return {"success": False, "message": str(e)}

    if not isinstance(data, dict) or data.get("retCode") != 0:
        return {"success": False, "message": str(data)}
    rows = (data.get("result") or {}).get("list") or []
    for r in rows:
        if str(r.get("symbol") or "").upper() != symbol.upper():
            continue
        size = Decimal(str(r.get("size") or "0"))
        raw_side = str(r.get("side") or "").strip().lower()
        if raw_side in ("sell", "short"):
            size = -abs(size)
            side = "short"
        elif raw_side in ("buy", "long"):
            side = "long"
        else:
            side = "long" if size > 0 else "short" if size < 0 else "flat"
        return {
            "success": True,
            "symbol": str(r.get("symbol") or "").upper(),
            "positionAmt": str(size),
            "entryPrice": str(r.get("avgPrice") or "0"),
            "leverage": str(r.get("leverage") or "0"),
            "unRealizedProfit": str(r.get("unrealisedPnl") or "0"),
            "side": side,
        }
    return {"success": False, "message": "Position not found"}
