#!/usr/bin/env python3
# app/exchanges/binance_futures_testnet/sync.py

import httpx
import logging
from app.exchanges.binance_futures_testnet.settings import API_KEY, API_SECRET, BASE_URL
from app.exchanges.binance_futures_testnet.utils import (
    sign_payload,
    get_binance_server_time,
)

logger = logging.getLogger(__name__)


async def get_open_position(symbol: str) -> dict:
    """
    Binance Futures testnet üzerinde verilen sembol için açık pozisyonu getirir.
    """
    try:
        endpoint = "/fapi/v2/positionRisk"
        url = f"{BASE_URL}{endpoint}"
        params = {"timestamp": await get_binance_server_time()}

        params["signature"] = sign_payload(params)

        headers = {"X-MBX-APIKEY": API_KEY}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()

            for position in data:
                if position["symbol"] == symbol:
                    return {
                        "success": True,
                        "positionAmt": float(position["positionAmt"]),
                        "entryPrice": float(position["entryPrice"]),
                        "leverage": int(position["leverage"]),
                        "unrealizedProfit": float(position["unRealizedProfit"]),
                        "side": "long"
                        if float(position["positionAmt"]) > 0
                        else "short"
                        if float(position["positionAmt"]) < 0
                        else "flat",
                    }

            return {"success": False, "message": "Position not found"}

    except Exception as e:
        logger.exception("Error while fetching open position")
        return {"success": False, "message": str(e)}
