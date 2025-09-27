#!/usr/bin/env python3
# app/exchanges/binance_futures_mainnet/sync.py
# Python 3.9

import logging
import httpx

from app.exchanges.common.http.retry import arequest_with_retry
from .settings import BASE_URL, ENDPOINTS, HTTP_TIMEOUT_SHORT
from .utils import build_signed_get

logger = logging.getLogger(__name__)


async def get_open_position(symbol: str) -> dict:
    """
    Binance Futures Mainnet üzerinde verilen sembol için açık pozisyonu getirir.
    """
    try:
        endpoint = ENDPOINTS["POSITION_RISK"]
        params = {"symbol": symbol.upper()}
        full_url, headers = await build_signed_get(f"{BASE_URL}{endpoint}", params)

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
            data = resp.json()

        # positionRisk bazen tek obje, bazen liste dönebilir; liste bekleyelim:
        positions = data if isinstance(data, list) else [data]
        for p in positions:
            if p.get("symbol") == symbol.upper():
                amt = p.get("positionAmt", "0")
                side = (
                    "long" if float(amt) > 0 else "short" if float(amt) < 0 else "flat"
                )
                return {
                    "success": True,
                    "symbol": p.get("symbol"),
                    "positionAmt": str(
                        p.get("positionAmt", "0")
                    ),  # string dön → üst katmanda Decimal
                    "entryPrice": str(p.get("entryPrice", "0")),
                    "leverage": str(p.get("leverage", "0")),
                    "unRealizedProfit": str(p.get("unRealizedProfit", "0")),
                    "side": side,
                }

        return {"success": False, "message": "Position not found"}

    except Exception as e:
        logger.exception("Error while fetching open position")
        return {"success": False, "message": str(e)}
