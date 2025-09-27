#!/usr/bin/env python3
# app/exchanges/binance_futures_mainnet/account.py
# Python 3.9

import asyncio
import httpx
import re
import time

from app.exchanges.common.http.retry import arequest_with_retry
from datetime import datetime, timezone
from typing import Optional, Any, Iterable, Dict, Tuple, cast, Union
from .settings import (
    BASE_URL,
    ENDPOINTS,
    POSITION_MODE,
    USERTRADES_LOOKBACK_MS,
    RECV_WINDOW_MS,
    RECV_WINDOW_LONG_MS,
    HTTP_TIMEOUT_SHORT,
    HTTP_TIMEOUT_LONG,
)
from .utils import (
    build_signed_get,
    quantize_price,
)

# --- Tip güvenli query yardımcıları -------------------------------------------------
# urlencode için (key, value) ikililerini **sıralı** ve tipli döndürmek üzere
Items = Tuple[Tuple[str, Any], ...]


def _sorted_items(params: Dict[str, Any]) -> Items:
    """urlencode için sıralı (key, value) ikilileri (tuple of tuples) döndürür."""
    return cast(Items, tuple(sorted(params.items())))


# --- Timestamp normalizasyonu ------------------------------------------------------
def _to_ms(ts_like: Union[int, float, str, datetime]) -> int:
    """
    Desteklenen girişler:
      - int/float: saniye veya milisaniye olabilir (10/13 haneli ayrımı)
      - ISO/“YYYY-MM-DD HH:MM:SS” string (tz içermezse UTC varsayılır)
      - datetime (tz yoksa UTC varsayılır)
    Çıkış: UTC epoch millisecond (int)
    """
    if isinstance(ts_like, (int, float)):
        v = float(ts_like)
        # 13+ hane → ms; 10± → saniye
        return int(v if v >= 1e12 else v * 1000)
    if isinstance(ts_like, datetime):
        dt = ts_like if ts_like.tzinfo else ts_like.replace(tzinfo=timezone.utc)
        return int(dt.astimezone(timezone.utc).timestamp() * 1000)
    if isinstance(ts_like, str):
        s = ts_like.strip()
        if s.isdigit():
            return _to_ms(int(s))
        # ISO8601 dene
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            # "YYYY-MM-DD HH:MM:SS"
            try:
                dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                raise ValueError(f"Unsupported timestamp format: {s!r}")
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.astimezone(timezone.utc).timestamp() * 1000)
    raise TypeError(f"Unsupported timestamp type: {type(ts_like).__name__}")


async def get_account_balance():
    """
    Binance Futures hesabındaki tüm bakiyeleri döner.
    """
    endpoint = ENDPOINTS["BALANCE"]
    url = BASE_URL + endpoint

    # imzalı URL + header
    full_url, headers = await build_signed_get(url, {})
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as client:
        r = await arequest_with_retry(
            client,
            "GET",
            full_url,
            headers=headers,
            timeout=HTTP_TIMEOUT_SHORT,
            max_retries=1,
            retry_on_binance_1021=False,
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
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_LONG) as client:
        r = await arequest_with_retry(
            client,
            "GET",
            BASE_URL + ep,
            timeout=HTTP_TIMEOUT_LONG,
            max_retries=1,
        )
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
    USDⓈ-M açık pozisyonlardan **borsa verisi** ile canlı (unrealized) PnL döndürür.
    Davranış:
      • `symbol=None` ve `return_all=True`  → `{"total": float, "positions": [ {..}, ... ]}`
      • `symbol=None` ve `return_all=False` → `{"unrealized": float}` (toplam)
      • `symbol='BTCUSDT'` (hedge/one-way fark etmeksizin) → İlgili sembolün **bacak/detay listesi**
        (toplam tek bir sayı döndürmez). Gerekirse toplam, liste üzerinden
        çağıran tarafça toplanabilir.
    Not: Dönen değerler doğrudan borsa yanıtından normalize edilir (örn. `unRealizedProfit`).
    """
    ep = ENDPOINTS.get("POSITION_RISK", "/fapi/v2/positionRisk")
    url = BASE_URL + ep
    full_url, headers = await build_signed_get(url, {})

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as client:
        r = await arequest_with_retry(
            client,
            "GET",
            full_url,
            headers=headers,
            timeout=HTTP_TIMEOUT_SHORT,
            max_retries=1,
            retry_on_binance_1021=False,
        )
        r.raise_for_status()
        rows = r.json()

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
    Not: Mainnet'te de bu uç desteklenir; limit=1000 sayfalanır.
    """
    ep = ENDPOINTS.get("INCOME", "/fapi/v1/income")
    url = BASE_URL + ep

    # Zaman damgaları (ms)
    start_ms = int((since or datetime.utcfromtimestamp(0)).timestamp() * 1000)
    end_ms: Optional[int] = int(until.timestamp() * 1000) if until else None
    total = 0.0
    page_guard = 0
    cursor = start_ms
    sym = _normalize_symbol(symbol) if symbol else None

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_LONG) as client:
        while True:
            page_guard += 1
            if page_guard > 20:  # emniyet: 20k kayıt ~ 20 sayfa
                break

            params = {"incomeType": "REALIZED_PNL", "limit": 1000, "startTime": cursor}

            if end_ms:
                params["endTime"] = end_ms
            if sym:
                params["symbol"] = sym

            full_url, headers = await build_signed_get(
                url, params, recv_window=RECV_WINDOW_LONG_MS
            )
            r = await arequest_with_retry(
                client,
                "GET",
                full_url,
                headers=headers,
                timeout=HTTP_TIMEOUT_LONG,
                max_retries=1,
                retry_on_binance_1021=False,
            )
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
                except (TypeError, ValueError, KeyError):
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


class Account:
    # noinspection PyMethodMayBeStatic
    async def get_unrealized(self, symbol=None, return_all=False):
        return await get_unrealized(symbol=symbol, return_all=return_all)

    # noinspection PyMethodMayBeStatic
    async def get_account_balance(self):
        return await get_account_balance()

    # noinspection PyMethodMayBeStatic
    async def income_summary(self, symbol=None, since=None, until=None):
        return await income_summary(symbol=symbol, since=since, until=until)

    # noinspection PyMethodMayBeStatic
    async def get_available(
        self, asset=None, symbol=None, currency=None, return_all=False
    ):
        return await get_available(
            asset=asset, symbol=symbol, currency=currency, return_all=return_all
        )


account = Account()


# --------------------------- CLOSE PRICE (userTrades→VWAP) ---------------------------
async def get_close_price_from_usertrades(
    symbol: str,
    opened_at: Union[int, float, str, datetime],
    side: str,  # "long" | "short"
    limit: int = 1000,
) -> dict:
    """
    Pozisyonu KAPATAN fill'lerin VWAP'ını döndürür.
    Döner: {"success": True, "price": float, "time": int, "fills": int, "qty": float}
           bulunamazsa {"success": False, "message": "..."}
    """
    url = BASE_URL + ENDPOINTS["USER_TRADES"]
    sym = _normalize_symbol(symbol)
    want_side = "SELL" if (side or "").lower() == "long" else "BUY"
    want_pos_side = "LONG" if (side or "").lower() == "long" else "SHORT"

    # opened_at → epoch ms (60 sn güvenlik tamponu). Bunu ÖNCE hesapla.
    try:
        start_ms = _to_ms(opened_at)
    except (TypeError, ValueError) as e:
        return {"success": False, "message": f"invalid opened_at: {e}"}
    start_ms = max(0, int(start_ms) - int(USERTRADES_LOOKBACK_MS))

    params = {
        "symbol": sym,
        "limit": limit,
        "startTime": int(start_ms),
    }

    full_url, headers = await build_signed_get(url, params, recv_window=RECV_WINDOW_MS)
    # rows'u iç blokta doldurup hemen kullanıyoruz (IDE false-positive'lerini kapatmak için)
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_LONG) as c:
            r = await arequest_with_retry(
                c,
                "GET",
                full_url,
                headers=headers,
                timeout=HTTP_TIMEOUT_LONG,
                max_retries=1,
                retry_on_binance_1021=False,
            )
            r.raise_for_status()
            rows = r.json() or []
    except httpx.HTTPStatusError as e:
        return {
            "success": False,
            "message": f"HTTP {e.response.status_code}: {e.response.text}",
        }
    except (httpx.RequestError, asyncio.TimeoutError, ValueError, TypeError) as e:
        return {"success": False, "message": str(e)}

    # Kapanışı yapan fill'leri sırayla topla ve VWAP hesapla
    fills = []
    qty_sum = 0.0
    notional = 0.0
    last_t = None

    for it in rows:
        s = str(it.get("side", "")).upper()
        ps = str(it.get("positionSide", "")).upper()
        if POSITION_MODE == "hedge":
            if s != want_side or ps != want_pos_side:
                continue
        else:
            if s != want_side:
                continue
        try:
            p = float(it.get("price") or 0.0)
            q = float(it.get("qty") or 0.0)
            t = int(it.get("time") or 0)
        except (ValueError, TypeError):
            continue
        if p <= 0 or q <= 0:
            continue
        fills.append((p, q, t))
        notional += p * q
        qty_sum += q
        last_t = t

    if qty_sum <= 0:
        return {"success": False, "message": "no closing fills found"}

    vwap = notional / qty_sum

    # Fiyatı exchange tick'e göre quantize et (uyum için)
    try:
        qprice = await quantize_price(sym, vwap)
    except (ValueError, TypeError, KeyError, asyncio.TimeoutError, httpx.HTTPError):
        # quantize başarısızsa (tip hatası / cache / ağ) → raw VWAP'a düş
        qprice = float(vwap)

    return {
        "success": True,
        "price": float(qprice),
        "time": int(last_t or 0),
        "fills": len(fills),
        "qty": float(qty_sum),
    }
