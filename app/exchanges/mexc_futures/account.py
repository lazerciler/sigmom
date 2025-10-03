#!/usr/bin/env python3
# app/exchanges/mexc_futures/account.py
# Python 3.9

import httpx
import re

from datetime import datetime, timezone
from typing import Optional, Any, Iterable

from app.exchanges.common.http.retry import arequest_with_retry
from .settings import (
    BASE_URL,
    ENDPOINTS,
    RECV_WINDOW_MS,
    HTTP_TIMEOUT_SHORT,
)
from .utils import (
    build_signed_get,
)


def _normalize_symbol(sym: str) -> str:
    s = str(sym or "").strip().upper()
    if ":" in s:
        s = s.split(":", 1)[1]
    s = re.sub(r"\.P$", "", s)
    if "_" not in s and len(s) >= 6:
        s = s[:-4] + "_" + s[-4:]
    return s


async def get_account_balance():
    url = BASE_URL + ENDPOINTS["ASSETS"]
    full_url, headers = await build_signed_get(url, {}, recv_window=RECV_WINDOW_MS)
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as client:
        r = await arequest_with_retry(
            client,
            "GET",
            full_url,
            headers=headers,
            timeout=HTTP_TIMEOUT_SHORT,
            max_retries=1,
        )
        r.raise_for_status()
        return r.json()


def _unwrap_assets(resp: Any) -> list:
    if isinstance(resp, dict):
        return list(resp.get("data") or [])
    return list(resp) if isinstance(resp, Iterable) else []


async def get_unrealized(symbol: Optional[str] = None, return_all: bool = False):
    """
    MEXC tarafında toplam unrealized için /account/assets döndüren satırlardaki 'unrealized' alanı kullanılabilir.
    Sembole göre bacak bazında detay için open_positions filtrelenir.
    """
    # Toplam
    assets = _unwrap_assets(await get_account_balance())
    total = 0.0
    for a in assets:
        try:
            total += float(a.get("unrealized") or 0.0)
        except Exception:
            pass
    if not symbol:
        return (
            {"unrealized": float(total)}
            if not return_all
            else {"total": float(total), "positions": []}
        )

    # Sembole göre bacak detayı
    url = BASE_URL + ENDPOINTS["OPEN_POSITIONS"]
    params = {"symbol": _normalize_symbol(symbol)}
    full_url, headers = await build_signed_get(url, params, recv_window=RECV_WINDOW_MS)
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as c:
        r = await arequest_with_retry(
            c,
            "GET",
            full_url,
            headers=headers,
            timeout=HTTP_TIMEOUT_SHORT,
            max_retries=1,
        )
        r.raise_for_status()
        j = r.json() or {}
    rows = j.get("data") or []
    legs = []
    for p in rows:
        try:
            legs.append(
                {
                    "symbol": str(p.get("symbol") or ""),
                    "positionSide": (
                        "LONG" if int(p.get("positionType") or 0) == 1 else "SHORT"
                    ),
                    # MEXC open_positions gerçek zamanlı mark price döndürmez; unrealized hesap dışı.
                    # Mevcut alanlar:
                    "unRealizedProfit": 0.0,
                    "positionAmt": float(p.get("holdVol") or 0.0),
                    "entryPrice": float(p.get("holdAvgPrice") or 0.0),
                    "leverage": float(p.get("leverage") or 0.0),
                    "markPrice": 0.0,
                    "liquidationPrice": float(p.get("liquidatePrice") or 0.0),
                }
            )
        except Exception:
            continue
    return legs if not return_all else legs


# Binance ile eşlenen alt fonksiyonlar ve Account sınıfı
class Account:
    async def get_unrealized(self, symbol=None, return_all=False):
        return await get_unrealized(symbol=symbol, return_all=return_all)

    async def get_account_balance(self):
        return await get_account_balance()

    async def income_summary(self, symbol=None, since=None, until=None):
        # income_breakdown order deals üzerinden; burada sade toplam döndürmek istiyorsanız
        # order_handler.income_breakdown’u kullanın
        from .order_handler import income_breakdown

        start_ms = int((since or datetime.utcfromtimestamp(0)).timestamp() * 1000)
        end_ms = int((until or datetime.now(timezone.utc)).timestamp() * 1000)
        r = await income_breakdown(start_ms, end_ms, symbol=symbol, limit=1000)
        return float(r.get("net", 0.0))

    async def get_available(
        self, asset=None, symbol=None, currency=None, return_all=False
    ):
        resp = await get_account_balance()
        rows = _unwrap_assets(resp)
        want = (currency or asset or "USDT").upper()
        row = next(
            (r for r in rows if str(r.get("currency", "")).upper() == want), None
        )
        if not row:
            return {"asset": want, "available": 0.0, "balance": 0.0}
        return {
            "asset": want,
            "available": float(row.get("availableBalance") or 0.0),
            "balance": float(row.get("equity") or 0.0),
        }


account = Account()
