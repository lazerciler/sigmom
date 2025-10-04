#!/usr/bin/env python3
# app/exchanges/bybit_futures_testnet/positions.py
# Python 3.9

import httpx
from decimal import Decimal
from app.exchanges.common.http.retry import arequest_with_retry
from .settings import BASE_URL, ENDPOINTS, HTTP_TIMEOUT_LONG, RECV_WINDOW_LONG_MS
from .utils import build_signed_get
import logging

logger = logging.getLogger(__name__)


def _norm_row(row: dict) -> dict:
    # Bybit v5: row = {'symbol','size','avgPrice','leverage','unrealisedPnl','side','positionIdx',...}
    sym = str(row.get("symbol") or "").upper()
    size = Decimal(str(row.get("size") or "0"))
    # Binance şeması: short için negatif miktar kullanıyoruz
    if str(row.get("side") or "").upper() == "SELL":
        size = -abs(size)
    return {
        "symbol": sym,
        "positionAmt": str(size),  # Binance: string miktar
        "entryPrice": str(row.get("avgPrice") or "0"),
        "leverage": str(row.get("leverage") or "0"),
        "unRealizedProfit": str(row.get("unrealisedPnl") or "0"),
        # Hedge uyumluluğu için (one_way'da LONG varsayım; SELL gelirse SHORT)
        "positionSide": "SHORT" if size < 0 else "LONG",
        # ham veri dursun (debug için)
        "_raw": row,
    }


async def get_open_positions():
    """
    Bybit Futures Testnet'teki açık pozisyonları getirir (tüm semboller).
    DÖNÜŞ: Binance positionRisk ile aynı şema (list[dict]).
    """
    endpoint = ENDPOINTS["POSITION_RISK"]  # /v5/position/list
    url = BASE_URL + endpoint
    params = {"category": "linear"}
    full_url, headers = await build_signed_get(
        url, params, recv_window=RECV_WINDOW_LONG_MS
    )

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_LONG) as client:
        resp = await arequest_with_retry(
            client,
            "GET",
            full_url,
            headers=headers,
            timeout=HTTP_TIMEOUT_LONG,
            max_retries=1,
            retry_on_binance_1021=False,
        )
        resp.raise_for_status()
        data = resp.json() or {}

    if not isinstance(data, dict) or data.get("retCode") != 0:
        logger.error("bybit get_open_positions failed: %s", data)
        return []
    rows = (data.get("result") or {}).get("list") or []
    return [_norm_row(r) for r in rows if isinstance(r, dict)]
