#!/usr/bin/env python3
# app/routers/market.py
# Python 3.9
from fastapi import APIRouter, HTTPException, Query
from app.config import settings
from importlib import import_module
import httpx

router = APIRouter(prefix="/api/market", tags=["market"])

def _get_exchange_settings():
    try:
        s = import_module(f"app.exchanges.{settings.DEFAULT_EXCHANGE}.settings")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ayar modülü yüklenemedi: {e}")

    base = getattr(s, "BASE_URL", None)
    if not base:
        raise HTTPException(status_code=500, detail="Seçili borsa settings.BASE_URL yok")

    # Her borsa kendi path ve param isimlerini tanımlar
    path = getattr(s, "KLINES_PATH", "/fapi/v1/klines")
    param_keys = getattr(
        s, "KLINES_PARAMS",
        {"symbol": "symbol", "interval": "interval", "limit": "limit"}
    )
    tf_map = getattr(s, "TF_MAP", None)
    limit_max = int(getattr(s, "KLINES_LIMIT_MAX", 1500))

    return base, path, param_keys, tf_map, limit_max

def _normalize(data):
    out = []
    for r in data or []:
        if isinstance(r, (list, tuple)) and len(r) >= 5:
            out.append({"t": int(r[0]), "o": float(r[1]), "h": float(r[2]),
                        "l": float(r[3]), "c": float(r[4])})
        elif isinstance(r, dict):
            t = r.get("t") or r.get("ts") or r.get("time")
            o = r.get("o") or r.get("open")
            h = r.get("h") or r.get("high")
            l = r.get("l") or r.get("low")
            c = r.get("c") or r.get("close")
            if None in (t, o, h, l, c):
                continue
            out.append({"t": int(t), "o": float(o), "h": float(h),
                        "l": float(l), "c": float(c)})
    return out

@router.get("/klines")
# async def klines(symbol: str = Query("BTCUSDT"),
#                  tf: str = Query("15m"),
#                  limit: int = Query(500, ge=1, le=1500)):
async def klines(
    symbol: str = Query(..., min_length=3, max_length=24),  # ← zorunlu
    tf: str = Query("15m"),
    limit: int = Query(500, ge=1, le=1500),
):
    symbol = symbol.upper()

    base, path, P, tf_map, limit_max = _get_exchange_settings()
    interval = tf_map.get(tf, tf) if tf_map else tf
    params = {
        P["symbol"]: symbol,
        P["interval"]: interval,
        P["limit"]: min(int(limit), limit_max),
    }
    try:
        async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
            r = await client.get(path, params=params)
            r.raise_for_status()
            return _normalize(r.json())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Klines alınamadı: {e}")
