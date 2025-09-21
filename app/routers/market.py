#!/usr/bin/env python3
# app/routers/market.py
# Python 3.9

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Callable, Any, Dict
from app.config import settings
from importlib import import_module
import httpx

router = APIRouter(prefix="/api/market", tags=["market"])


def _get_exchange_settings(ex_override: Optional[str] = None):
    try:
        ex_name = (ex_override or settings.DEFAULT_EXCHANGE).strip()
        s = import_module(f"app.exchanges.{ex_name}.settings")
    except (ImportError, ModuleNotFoundError) as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to load configuration module: {e}"
        )

    base = getattr(s, "BASE_URL", None)
    if not base:
        raise HTTPException(
            status_code=500, detail="Seçili borsa settings.BASE_URL yok"
        )

    # Her borsa kendi path ve param isimlerini tanımlar
    # path: KLINES_PATH yoksa ENDPOINTS["KLINES"]'e düş
    endpoints = getattr(s, "ENDPOINTS", {}) or {}
    path = getattr(s, "KLINES_PATH", endpoints.get("KLINES", "/fapi/v1/klines"))

    # Parametre adları: varsayılan (symbol/interval/limit).
    param_keys = getattr(
        s,
        "KLINES_PARAMS",
        {"symbol": "symbol", "interval": "interval", "limit": "limit"},
    )

    tf_map = getattr(s, "TF_MAP", None)
    limit_max = int(getattr(s, "KLINES_LIMIT_MAX", 1500))

    # Opsiyonel: sembol dönüştürücü (ör. BTCUSDT→XBTUSDTM)
    normalize_symbol = getattr(s, "normalize_symbol", None)
    if not callable(normalize_symbol):
        normalize_symbol = None

    # Yeni: borsa-özel kline param kurucu ve parser (opsiyonel)
    build_params: Optional[Callable[[str, str, int], Dict[str, Any]]] = getattr(
        s, "build_klines_params", None
    )
    parse_klines: Optional[Callable[[Any], Any]] = getattr(s, "parse_klines", None)

    return (
        base,
        path,
        param_keys,
        tf_map,
        limit_max,
        normalize_symbol,
        build_params,
        parse_klines,
    )


# def _tf_to_minutes(val):
#     """'15m'→15, '1h'→60, '1d'→1440, '1w'→10080 | int ise aynen döner."""
#     if val is None:
#         return None
#     if isinstance(val, int):
#         return val
#     s = str(val).strip().lower()
#     if s.endswith("m"):
#         return int(s[:-1])
#     if s.endswith("h"):
#         return int(s[:-1]) * 60
#     if s.endswith("d"):
#         return int(s[:-1]) * 1440
#     if s.endswith("w"):
#         return int(s[:-1]) * 10080
#     # doğrudan sayı verilmiş olabilir
#     try:
#         return int(s)
#     except (ValueError, TypeError):
#         return None
# Not: TF dönüşümü, borsa tarafındaki TF_MAP ile çözümlendiği için
# _tf_to_minutes yardımcı fonksiyonuna artık ihtiyaç yok.


def _normalize(data):
    out = []

    for r in data or []:

        if isinstance(r, (list, tuple)) and len(r) >= 5:
            out.append(
                {
                    "t": int(r[0]),
                    "o": float(r[1]),
                    "h": float(r[2]),
                    "l": float(r[3]),
                    "c": float(r[4]),
                }
            )
        elif isinstance(r, dict):
            t = r.get("t") or r.get("ts") or r.get("time")
            o = r.get("o") or r.get("open")
            h = r.get("h") or r.get("high")
            low_v = r.get("l") or r.get("low")
            c = r.get("c") or r.get("close")
            if None in (t, o, h, low_v, c):
                continue
            out.append(
                {
                    "t": int(t),
                    "o": float(o),
                    "h": float(h),
                    "l": float(low_v),
                    "c": float(c),
                }
            )
    return out


@router.get("/klines")
async def klines(
    symbol: str = Query(..., min_length=3, max_length=24),  # ← zorunlu
    tf: str = Query("15m"),
    limit: int = Query(500, ge=1, le=1500),
    ex: Optional[str] = Query(
        None, description="Exchange override; None → DEFAULT_EXCHANGE"
    ),
):
    symbol = symbol.upper()

    base, path, p, tf_map, limit_max, normalize_symbol, build_params, parse_klines = (
        _get_exchange_settings(ex)
    )

    # interval/granularity değeri
    interval_val = tf_map.get(tf, tf) if tf_map else tf
    # sembol dönüştürme (opsiyonel)
    if normalize_symbol:
        try:
            symbol = normalize_symbol(symbol)
        except (ValueError, TypeError):
            pass

    # Paramlar: varsa borsa-özel build_klines_params, yoksa generic (interval+limit)
    if callable(build_params):
        params = build_params(symbol, interval_val, min(int(limit), limit_max))
        if not isinstance(params, dict):
            raise HTTPException(
                status_code=500, detail="build_klines_params invalid return"
            )
    else:
        params = {
            p.get("symbol", "symbol"): symbol,
            p.get("interval", "interval"): interval_val,
            p.get("limit", "limit"): min(int(limit), limit_max),
        }

    try:
        async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
            r = await client.get(path, params=params)
            r.raise_for_status()

            j = r.json()
            # Parse: varsa borsa-özel parse_klines, yoksa generic normalize
            if callable(parse_klines):
                parsed = parse_klines(j)
                return parsed if parsed is not None else []
            return _normalize(j)

    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Klines alınamadı: {e}")
