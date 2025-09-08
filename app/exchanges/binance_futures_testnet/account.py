#!/usr/bin/env python3
# app/exchanges/binance_futures_testnet/account.py
# Python 3.9
import httpx
import re
import time
from datetime import datetime
from typing import Optional, Any, Iterable, Dict, Tuple
from urllib.parse import urlencode


from .settings import BASE_URL, ENDPOINTS
from .utils import sign_payload, get_binance_server_time, get_signed_headers


async def get_account_balance():
    """
    Binance Futures hesabındaki tüm bakiyeleri döner.
    """
    endpoint = ENDPOINTS["BALANCE"]
    url = BASE_URL + endpoint

    # 1) Sunucu saatine göre ts
    try:
        ts = await get_binance_server_time()
    except Exception:
        ts = int(time.time() * 1000)
    # 2) Sıralı query + aynı sırayla imza ve gönderim
    params = {"timestamp": ts, "recvWindow": 5000}
    query = urlencode(sorted(params.items()))
    sig = sign_payload(params)
    headers = get_signed_headers()  # {"X-MBX-APIKEY": API_KEY}
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{url}?{query}&signature={sig}", headers=headers, timeout=15
        )
        r.raise_for_status()
        return r.json()


# -------------------- Yardımcılar: balances & exchangeInfo --------------------
_EXINFO_CACHE: Dict[str, Any] = {"t": 0, "data": None}


def _unwrap_balances(rows: Any) -> list:
    """/fapi/v2/balance bazen list, bazen {'balances':[...]} dönebilir."""
    if isinstance(rows, dict) and "balances" in rows:
        return list(rows["balances"])
    return list(rows) if isinstance(rows, Iterable) else []


async def _get_exchange_info() -> dict:
    """/fapi/v1/exchangeInfo — 5 dk cache"""
    now = time.time()
    if _EXINFO_CACHE["data"] and (now - _EXINFO_CACHE["t"] < 300):
        return _EXINFO_CACHE["data"]
    ep = ENDPOINTS.get("EXCHANGE_INFO")
    if not ep:
        return {}
    async with httpx.AsyncClient() as client:
        r = await client.get(BASE_URL + ep)
        r.raise_for_status()
        data = r.json()
        _EXINFO_CACHE.update({"t": now, "data": data})
        return data


def _normalize_symbol(sym: str) -> str:
    """BINANCE:BTCUSDT.P → BTCUSDT"""
    s = str(sym or "").strip().upper()
    if ":" in s:
        s = s.split(":", 1)[1]
    s = re.sub(r"\.P$", "", s)  # TV perpetual eki
    return s


async def get_unrealized(symbol: Optional[str] = None, return_all: bool = False):
    """
    USDⓈ-M açık pozisyonlardan canlı (unrealized) PnL döndürür.
    - symbol verilirse o sembolün uPnL'i, verilmezse toplam ve detay listesi.
    """
    ep = ENDPOINTS.get("POSITION_RISK", "/fapi/v2/positionRisk")
    url = BASE_URL + ep
    try:
        ts = await get_binance_server_time()
    except Exception:
        ts = int(time.time() * 1000)
    params = {"timestamp": ts, "recvWindow": 5000}
    query = urlencode(sorted(params.items()))
    sig = sign_payload(params)
    headers = get_signed_headers()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{url}?{query}&signature={sig}", headers=headers, timeout=15
        )
        r.raise_for_status()
        rows = r.json()  # list[dict]

    # yalnızca açık (positionAmt != 0)

    def fnum(v) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    open_pos = [p for p in rows if abs(fnum(p.get("positionAmt"))) > 0]
    if symbol:
        s = _normalize_symbol(symbol)
        legs = [
            {
                "symbol": str(p.get("symbol", "")).upper(),
                "positionSide": str(p.get("positionSide") or "").upper(),
                "unRealizedProfit": fnum(p.get("unRealizedProfit")),
                "positionAmt": fnum(p.get("positionAmt")),
                "entryPrice": fnum(p.get("entryPrice")),
                "leverage": fnum(p.get("leverage")),
                "markPrice": fnum(p.get("markPrice")),
                "liquidationPrice": fnum(p.get("liquidationPrice")),
            }
            for p in open_pos
            if str(p.get("symbol", "")).upper() == s
        ]
        if return_all:
            return legs
        return legs
    # tüm semboller
    details = [
        {
            "symbol": str(p.get("symbol", "")).upper(),
            "unrealized": fnum(p.get("unRealizedProfit")),
            "position_amt": fnum(p.get("positionAmt")),
            "entry_price": fnum(p.get("entryPrice")),
            "leverage": fnum(p.get("leverage")),
            "mark_price": fnum(p.get("markPrice")),
            "liquidation_price": fnum(p.get("liquidationPrice")),
        }
        for p in open_pos
    ]
    total = sum(d["unrealized"] for d in details)
    if return_all:
        return {"total": total, "positions": details}
    return {"unrealized": total}


# --------------------------- Net PnL (income summary) ---------------------------
async def income_summary(
    symbol: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> float:
    """
    Binance USDⓈ-M Futures gelir dökümünden (REALIZED_PNL) net toplamı döndürür.
    - symbol: 'BTCUSDT' gibi (opsiyonel)
    - since/until: datetime(UTC); sayfalama ile /fapi/v1/income taranır.
    Not: Testnet'te de bu uç desteklenir; limit=1000 sayfalanır.
    """
    ep = ENDPOINTS.get("INCOME", "/fapi/v1/income")
    url = BASE_URL + ep

    # Zaman damgaları (ms)
    start_ms = int((since or datetime.utcfromtimestamp(0)).timestamp() * 1000)
    end_ms: Optional[int] = int(until.timestamp() * 1000) if until else None

    # Ortak başlıklar / imza
    try:
        ts = await get_binance_server_time()
    except Exception:
        ts = int(time.time() * 1000)
    headers = get_signed_headers()  # {"X-MBX-APIKEY": ...}

    total = 0.0
    page_guard = 0
    cursor = start_ms
    sym = _normalize_symbol(symbol) if symbol else None

    async with httpx.AsyncClient(timeout=20.0) as client:
        while True:
            page_guard += 1
            if page_guard > 20:  # emniyet: 20k kayıt ~ 20 sayfa
                break

            params = {
                "timestamp": ts,
                "recvWindow": 5000,
                "incomeType": "REALIZED_PNL",
                "limit": 1000,
                "startTime": cursor,
            }
            if end_ms:
                params["endTime"] = end_ms
            if sym:
                params["symbol"] = sym

            # İmza **parametrelerin sıralı hali** üzerinden
            query = urlencode(sorted(params.items()))
            sig = sign_payload(params)
            r = await client.get(f"{url}?{query}&signature={sig}", headers=headers)
            r.raise_for_status()
            rows = r.json() or []
            if not isinstance(rows, list) or not rows:
                break

            # Toplamı ekle; bir sonraki sayfa için zaman imlecini güncelle
            last_time = cursor
            for it in rows:
                try:
                    # Sadece REALIZED_PNL; diğer income türlerini dahil etmiyoruz
                    if str(it.get("incomeType", "")).upper() != "REALIZED_PNL":
                        continue
                    total += float(it.get("income", 0) or 0)
                    t = int(it.get("time") or 0)
                    if t > last_time:
                        last_time = t
                except Exception:
                    continue

            # Sayfalama: bir sonraki sorgu, son kaydın +1 ms'inden
            # (Binance aynı ms'teki kayıtları tekrar döndürmesin diye)
            if last_time <= cursor:
                break
            cursor = last_time + 1
    return float(total)


def _split_symbol_tokens(s: str) -> Optional[Tuple[str, str]]:
    """ETH/BTC, ETH-BTC, ETH_BTC, ETH:BTC → ('ETH','BTC')"""
    for sep in ("/", "-", "_", ":"):
        if sep in s:
            a, b = s.split(sep, 1)
            # coin-m varyantları: USD_PERP → USD
            b = re.sub(r"^USD_?PERP$", "USD", b)
            return a or None, b or None
    return None


def _candidate_assets(balance_rows: list, exinfo: dict) -> list:
    assets = {str(r.get("asset", "")).upper() for r in balance_rows if r.get("asset")}
    quotes = {
        str(x.get("quoteAsset", "")).upper()
        for x in (exinfo.get("symbols") or [])
        if x.get("quoteAsset")
    }
    c = [a for a in (assets | quotes) if a]
    # sondan eşlemede doğru çalışsın diye uzun isimler önce
    return sorted(set(c), key=len, reverse=True)


def _infer_quote_concat(s: str, cands: list) -> Optional[str]:
    for q in cands:
        if s.endswith(q) and len(s) > len(q):
            return q
    if s.endswith("USD"):
        return "USD"
    return None


async def infer_quote_from_symbol(symbol: str) -> Optional[str]:
    """
    Sembolden quote çıkar: önce ayraçlı formatlar, yoksa bakiye/exchangeInfo ile sondan eşleme.
    ETHBTC(.P), BTCUSDT, ETH/BTC, BTCUSD_PERP hepsi desteklenir.
    """
    s = _normalize_symbol(symbol)
    s_no_perp = re.sub(r"[_-]PERP$", "", s)
    tok = _split_symbol_tokens(s_no_perp)
    if tok:
        _, quote = tok
        return quote
    rows = _unwrap_balances(await get_account_balance())
    exi = await _get_exchange_info()
    q = _infer_quote_concat(s_no_perp, _candidate_assets(rows, exi))
    if q:
        return q
    # exchangeInfo tam eşleşme fallback
    for row in exi.get("symbols") or []:
        if str(row.get("symbol", "")).upper() == s:
            return str(row.get("quoteAsset", "")).upper() or None
    return None


async def get_available(
    asset: Optional[str] = None,
    symbol: Optional[str] = None,
    currency: Optional[str] = None,
    return_all: bool = False,
):

    rows_raw = await get_account_balance()  # /fapi/v2/balance
    if return_all:
        return {"balances": rows_raw}
    rows = _unwrap_balances(rows_raw)
    want = (currency or asset or "").upper()

    if not want and symbol:
        want = await infer_quote_from_symbol(symbol)

    row = next((r for r in rows if str(r.get("asset", "")).upper() == want), None)
    if not row:
        return {"asset": want or None, "available": 0.0, "balance": 0.0}

    return {
        "asset": want,
        "available": float(row.get("availableBalance") or 0.0),
        "balance": float(row.get("balance") or row.get("walletBalance") or 0.0),
    }
