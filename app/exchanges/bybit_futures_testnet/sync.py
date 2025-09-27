#!/usr/bin/env python3
# app/exchanges/bybit_futures_testnet/sync.py
# Python 3.9

import logging
import httpx

from app.exchanges.common.http.retry import arequest_with_retry
from .settings import BASE_URL, ENDPOINTS, HTTP_TIMEOUT_SHORT
from .utils import build_signed_get

logger = logging.getLogger(__name__)


async def get_open_position(symbol: str) -> dict:
    """Bybit V5 Testnet üzerinde verilen sembol için açık pozisyonu getirir."""
    try:
        endpoint = ENDPOINTS["POSITION_RISK"]
        # Bybit V5: category zorunlu (USDT-M = "linear")
        params = {"category": "linear", "symbol": symbol.upper()}
        full_url, headers = await build_signed_get(f"{BASE_URL}{endpoint}", params)

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

        # Bybit V5 şeması: {"result":{"list":[...]}}
        result = data.get("result") if isinstance(data, dict) else None
        rows = result.get("list") if isinstance(result, dict) else None
        positions = rows if isinstance(rows, list) else []
        for p in positions:
            if str(p.get("symbol") or "").upper() == symbol.upper():
                size_s = str(p.get("size", "0") or "0")
                try:
                    size = float(size_s)
                except Exception:
                    size = 0.0
                side = "long" if size > 0.0 else "short" if size < 0.0 else "flat"
                return {
                    "success": True,
                    "symbol": p.get("symbol"),
                    "positionAmt": str(
                        p.get("size", "0")
                    ),  # Binance anahtarlarına uyumlu dönüş
                    "entryPrice": str(p.get("avgPrice", "0")),
                    "leverage": str(p.get("leverage", "0")),
                    "unRealizedProfit": str(p.get("unrealisedPnl", "0")),
                    "side": side,
                }

        return {"success": False, "message": "Position not found"}

    except Exception as e:
        logger.exception("Error while fetching open position")
        return {"success": False, "message": str(e)}
