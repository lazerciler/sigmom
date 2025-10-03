#!/usr/bin/env python3
# app/exchanges/mexc_futures/utils.py
# Python 3.9+

import json
import hmac
import logging
from hashlib import sha256
from time import time as _time
from typing import Optional, Tuple, Dict
from decimal import Decimal, ROUND_DOWN

import httpx

from .settings import (
    API_KEY,
    API_SECRET,
    BASE_URL,
    ENDPOINTS,
    RECV_WINDOW_MS,
    RECV_WINDOW_LONG_MS,
    HTTP_TIMEOUT_SHORT,
    HTTP_TIMEOUT_LONG,
    POSITION_MODE,
    TF_MAP,
)
from app.exchanges.common.http.retry import arequest_with_retry

logger = logging.getLogger(__name__)

# ============================================================
# Yardımcılar
# ============================================================


def _now_ms() -> int:
    return int(_time() * 1000)


def _to_mexc_symbol(symbol: str) -> str:
    """BTCUSDT -> BTC_USDT ; 'BTCUSDT.P' -> 'BTC_USDT'"""
    s = str(symbol or "").upper().replace(":", "_").replace("-", "_")
    if s.endswith(".P"):
        s = s[:-2]
    if "_" not in s and len(s) >= 6:
        s = s[:-4] + "_" + s[-4:]
    return s


def _sign_str(access_key: str, req_time: int, param_str: str, secret: str) -> str:
    # MEXC sign target: accessKey + timestamp + param_string
    msg = (access_key or "") + str(req_time) + (param_str or "")
    return hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), sha256).hexdigest()


def _headers(recv_window: Optional[int], body_or_query_str: str) -> dict:
    req_time = _now_ms()
    sign = _sign_str(API_KEY, req_time, body_or_query_str, API_SECRET)
    hdr = {
        "ApiKey": API_KEY,
        "Request-Time": str(req_time),
        "Signature": sign,
        "Content-Type": "application/json",
    }
    if recv_window:
        hdr["recv-window"] = str(int(recv_window))
    return hdr


def _full_url(path_or_url: str) -> str:
    if path_or_url.startswith("http"):
        return path_or_url
    if not path_or_url.startswith("/"):
        path_or_url = "/" + path_or_url
    return BASE_URL + path_or_url


# ============================================================
# Signed request builder’lar (Binance ile aynı arayüz)
# ============================================================


async def build_signed_get(
    url: str, params: Optional[Dict] = None, *, recv_window: Optional[int] = None
) -> Tuple[str, dict]:
    q = "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
    headers = _headers(recv_window or RECV_WINDOW_MS, q)
    return _full_url(url), headers


async def build_signed_post(
    url: str, params: Optional[Dict] = None, *, recv_window: Optional[int] = None
) -> Tuple[str, dict]:
    body_json = json.dumps(params or {}, separators=(",", ":"), ensure_ascii=False)
    headers = _headers(recv_window or RECV_WINDOW_MS, body_json)
    return _full_url(url), headers


# ============================================================
# Sembol meta (contract/detail) ve quantize yardımcıları
# ============================================================

_CONTRACT_MAP: dict = {}


async def _load_contract_map() -> dict:
    url = _full_url(ENDPOINTS["CONTRACT_DETAIL"])
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_LONG) as c:
        r = await arequest_with_retry(
            c, "GET", url, timeout=HTTP_TIMEOUT_LONG, max_retries=1
        )
        r.raise_for_status()
        info = r.json() or {}
    m = {}
    for it in info.get("data", []):
        sym = str(it.get("symbol") or "").upper()
        if not sym:
            continue
        price_unit = Decimal(str(it.get("priceUnit", "0.01")))
        vol_unit = Decimal(str(it.get("volUnit", "1")))
        min_vol = Decimal(str(it.get("minVol", "1")))
        m[sym] = {"tick": price_unit, "step": vol_unit, "min": min_vol}
    return m


async def get_symbol_meta_map() -> dict:
    global _CONTRACT_MAP
    if not _CONTRACT_MAP:
        _CONTRACT_MAP = await _load_contract_map()
    return _CONTRACT_MAP


def _q_floor(v: Decimal, step: Decimal) -> Decimal:
    return v.quantize(step, rounding=ROUND_DOWN)


def _p_floor(v: Decimal, tick: Decimal) -> Decimal:
    return v.quantize(tick, rounding=ROUND_DOWN)


async def format_quantity_text(symbol: str, quantity: float) -> str:
    info = await get_symbol_meta_map()
    meta = info.get(_to_mexc_symbol(symbol).upper())
    step = meta["step"] if meta else Decimal("1")
    sign = "-" if float(quantity) < 0 else ""
    q = _q_floor(abs(Decimal(str(quantity))), step)
    return sign + format(q, "f")


async def quantize_price(symbol: str, price: float) -> float:
    info = await get_symbol_meta_map()
    meta = info.get(_to_mexc_symbol(symbol).upper())
    tick = meta["tick"] if meta else Decimal("0.01")
    p = _p_floor(Decimal(str(price)), tick)
    return float(p)


async def adjust_quantity(symbol: str, quantity: float) -> str:
    info = await get_symbol_meta_map()
    meta = info.get(_to_mexc_symbol(symbol).upper())
    if not meta:
        raise ValueError(f"Symbol {symbol} not found in MEXC contract/detail")
    step = meta["step"]
    mn = meta["min"]
    q = max(Decimal(str(quantity)), mn)
    q = _q_floor(q, step)
    return format(q, "f")


# ============================================================
# Sunucu saati
# ============================================================


async def get_server_time() -> dict:
    url = _full_url(ENDPOINTS["SERVER_TIME"])
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as c:
            r = await arequest_with_retry(
                c, "GET", url, timeout=HTTP_TIMEOUT_SHORT, max_retries=1
            )
            r.raise_for_status()
            return {"success": True, "data": r.json()}
    except Exception as e:
        logger.error("get_server_time error: %s", e)
        return {"success": False, "message": str(e)}


# ============================================================
# Position mode
# ============================================================


async def get_position_mode() -> dict:
    """
    Dönen data formatı MEXC’te farklılaşabiliyor:
      - {"data": 1} veya {"data": "1"}
      - {"data": {"positionMode": 1}}
      - {"data": [{"positionMode": 1}, ...]}
      - Hata/boşta data: null
    Hepsini tolere ediyoruz. 1=hedge, 2=one-way
    """
    url = _full_url(ENDPOINTS["POSITION_MODE_GET"])
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as c:
            full_url, headers = await build_signed_get(
                url, {}, recv_window=RECV_WINDOW_LONG_MS
            )
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
            raw = j.get("data", None)

        val = None
        if isinstance(raw, (int, float, str)):
            val = raw
        elif isinstance(raw, dict):
            val = raw.get("positionMode") or raw.get("mode") or raw.get("value")
        elif isinstance(raw, list) and raw:
            first = raw[0]
            if isinstance(first, dict):
                val = (
                    first.get("positionMode") or first.get("mode") or first.get("value")
                )

        if val is None:
            mode = "hedge" if (POSITION_MODE or "").lower() == "hedge" else "one_way"
        else:
            try:
                mode = "hedge" if int(str(val).strip()) == 1 else "one_way"
            except Exception:
                sval = str(val).strip().lower()
                mode = "hedge" if sval in ("1", "hedge", "dual", "true") else "one_way"

        return {"success": True, "mode": mode, "data": j}
    except Exception as e:
        logger.error("get_position_mode error: %s", e)
        return {"success": False, "message": str(e)}


async def set_position_mode(mode: str) -> dict:
    url = _full_url(ENDPOINTS["POSITION_MODE_SET"])
    positionMode = 1 if (mode or "").lower() == "hedge" else 2
    params = {"positionMode": positionMode}
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as c:
            full_url, headers = await build_signed_post(
                url, params, recv_window=RECV_WINDOW_LONG_MS
            )
            r = await arequest_with_retry(
                c,
                "POST",
                full_url,
                headers=headers,
                json=params,
                timeout=HTTP_TIMEOUT_SHORT,
                max_retries=1,
            )
            r.raise_for_status()
            return {"success": True, "data": r.json()}
    except Exception as e:
        logger.error("set_position_mode error: %s", e)
        return {"success": False, "message": str(e)}


# ============================================================
# Leverage
# ============================================================


async def set_leverage(symbol: str, leverage: int) -> dict:
    """
    MEXC 'no-position' yoluyla kaldıraç değiştirme:
      openType: 1=isolated, 2=cross
      positionType: 1=long, 2=short (iki yön ayrı saklanabiliyor)
    Basitlik: positionType=1 ile ayarla; short öncesi tekrar çağırabilirsiniz.
    """
    url = _full_url(ENDPOINTS["LEVERAGE_SET"])
    try:
        lev = max(1, min(125, int(leverage)))
    except Exception:
        return {"success": False, "message": "invalid leverage"}
    params = {
        "openType": 2,
        "leverage": lev,
        "symbol": _to_mexc_symbol(symbol),
        "positionType": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as c:
            full_url, headers = await build_signed_post(
                url, params, recv_window=RECV_WINDOW_MS
            )
            r = await arequest_with_retry(
                c,
                "POST",
                full_url,
                headers=headers,
                json=params,
                timeout=HTTP_TIMEOUT_SHORT,
                max_retries=1,
            )
            r.raise_for_status()
            return {"success": True, "data": r.json()}
    except Exception as e:
        logger.error("set_leverage error: %s", e)
        return {"success": False, "message": str(e)}


# ============================================================
# Klines (panel/TV)
# ============================================================

_INTV_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "8h": 28800,
    "1d": 86400,
    "1w": 604800,
    "1M": 2592000,  # approx
}


async def get_klines(
    symbol: str,
    interval: str,
    limit: int = 500,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
) -> dict:
    """
    MEXC endpoint: GET /api/v1/contract/kline/{symbol}
      params: interval=Min1|Min5|... , start=<ms>, end=<ms>
    Çıktı: {"success": True, "klines": [[openTime, open, high, low, close, volume], ...]}
    """
    sym = _to_mexc_symbol(symbol)
    tf = TF_MAP.get(interval)
    if not tf:
        return {
            "success": False,
            "message": f"unsupported interval: {interval}",
            "klines": [],
        }

    try:
        lim = max(10, min(1500, int(limit)))
    except Exception:
        lim = 500

    now_ms = _now_ms()
    if end_ms is None:
        end_ms = now_ms
    if start_ms is None:
        step = _INTV_SECONDS.get(interval, 60) * 1000
        start_ms = int(end_ms - (lim * step))

    url = _full_url(ENDPOINTS["KLINE"].format(symbol=sym))
    params = {"interval": tf, "start": int(start_ms), "end": int(end_ms)}

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_LONG) as c:
            full_url, headers = await build_signed_get(
                url, params, recv_window=RECV_WINDOW_LONG_MS
            )
            # ÖNEMLİ: imza param’larla hesaplanıyor; param’lar request’e de eklenmeli.
            r = await arequest_with_retry(
                c,
                "GET",
                full_url,
                headers=headers,
                params=params,
                timeout=HTTP_TIMEOUT_LONG,
                max_retries=1,
            )
            r.raise_for_status()
            j = r.json() or {}
            raw = j.get("data") if isinstance(j, dict) else j

        out = []
        if isinstance(raw, list):
            for it in raw:
                try:
                    if isinstance(it, dict):
                        ts = int(
                            it.get("t") or it.get("time") or it.get("timestamp") or 0
                        )
                        o = float(it.get("o") or it.get("open"))
                        h = float(it.get("h") or it.get("high"))
                        l_ = float(it.get("l") or it.get("low"))
                        c_ = float(it.get("c") or it.get("close"))
                        v = float(it.get("v") or it.get("volume") or it.get("vol") or 0)
                        out.append([ts, o, h, l_, c_, v])
                    elif isinstance(it, (list, tuple)) and len(it) >= 6:
                        ts, o, h, l_, c_, v = it[0], it[1], it[2], it[3], it[4], it[5]
                        out.append(
                            [
                                int(ts),
                                float(o),
                                float(h),
                                float(l_),
                                float(c_),
                                float(v),
                            ]
                        )
                except Exception:
                    continue

        out.sort(key=lambda x: x[0])
        if len(out) > lim:
            out = out[-lim:]
        return {"success": True, "symbol": sym, "interval": interval, "klines": out}
    except httpx.HTTPStatusError as exc:
        logger.error(
            "get_klines HTTP %s: %s", exc.response.status_code, exc.response.text
        )
        return {"success": False, "message": exc.response.text, "klines": []}
    except Exception as e:
        logger.error("get_klines error: %s", e)
        return {"success": False, "message": str(e), "klines": []}


# ============================================================
# Dışa açık API
# ============================================================

__all__ = [
    "build_signed_get",
    "build_signed_post",
    "get_server_time",
    "get_position_mode",
    "set_position_mode",
    "set_leverage",
    "get_symbol_meta_map",
    "format_quantity_text",
    "quantize_price",
    "adjust_quantity",
    "get_klines",
]
