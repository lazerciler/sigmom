#!/usr/bin/env python3
# app/exchanges/binance_futures_testnet/sync.py
# Python 3.9
import logging
import httpx
from app.exchanges.binance_futures_testnet.settings import API_KEY, BASE_URL
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

        # Tüm parametreler imzaya dahil edilmeli
        params = {
            "symbol": symbol.upper(),
            "timestamp": await get_binance_server_time(),
            "recvWindow": 7000,
        }
        signature = sign_payload(params)

        headers = {"X-MBX-APIKEY": API_KEY}

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params={**params, "signature": signature}, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        # positionRisk bazen tek obje, bazen liste dönebilir; liste bekleyelim:
        positions = data if isinstance(data, list) else [data]
        for p in positions:
            if p.get("symbol") == symbol.upper():
                amt = p.get("positionAmt", "0")
                side = "long" if float(amt) > 0 else "short" if float(amt) < 0 else "flat"
                return {
                    "success": True,
                    "symbol": p.get("symbol"),
                    "positionAmt": str(p.get("positionAmt", "0")),   # string dön → üst katmanda Decimal
                    "entryPrice": str(p.get("entryPrice", "0")),
                    "leverage": str(p.get("leverage", "0")),
                    "unRealizedProfit": str(p.get("unRealizedProfit", "0")),
                    "side": side,
                }

        return {"success": False, "message": "Position not found"}

    except Exception as e:
        logger.exception("Error while fetching open position")
        return {"success": False, "message": str(e)}

