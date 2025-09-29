#!/usr/bin/env python3
# app/exchanges/bybit_futures_testnet/account.py
# Python 3.9

import asyncio
import httpx
import re
import time

from app.exchanges.common.http.retry import arequest_with_retry
from datetime import datetime, timezone
from typing import Optional, Any, Dict, Tuple, cast, Union
from .settings import (
    BASE_URL,
    ENDPOINTS,
    RECV_WINDOW_MS,
    HTTP_TIMEOUT_SHORT,
    HTTP_TIMEOUT_LONG,
    ACCOUNT_TYPE,
)
from .utils import build_signed_get

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
    """Bybit V5: /v5/account/wallet-balance (accountType zorunlu)"""
    url = BASE_URL + ENDPOINTS["BALANCE"]

    async def _call(acc_type: str):
        params = {"accountType": acc_type}
        full_url, headers = await build_signed_get(
            url, params, recv_window=RECV_WINDOW_MS
        )
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

    at = (ACCOUNT_TYPE or "AUTO").upper()
    if at == "AUTO":
        # önce UNIFIED dene, olmazsa CONTRACT
        try:
            return await _call("UNIFIED")
        except httpx.HTTPStatusError:
            return await _call("CONTRACT")
    else:
        return await _call(at)


# -------------------- Yardımcılar: balances & exchangeInfo --------------------
_EXINFO_CACHE: Dict[str, Any] = {"t": 0, "data": None}


def _unwrap_balances(rows: Any) -> list:
    """
    Bybit V5 wallet-balance normalizasyonu → [
      {"asset":"USDT","availableBalance": "...","walletBalance":"..."},
      ...
    ]
    """
    if not isinstance(rows, dict):
        return []
    result = rows.get("result")
    if not isinstance(result, dict):
        return []
    lst = result.get("list")
    if not isinstance(lst, list):
        return []
    out = []
    for acct in lst:
        coins = acct.get("coin") if isinstance(acct, dict) else None
        if not isinstance(coins, list):
            continue
        for c in coins:
            asset = str(c.get("coin") or "").upper()
            if not asset:
                continue
            out.append(
                {
                    "asset": asset,
                    "availableBalance": c.get("availableToWithdraw")
                    or c.get("availableBalance")
                    or "0",
                    "walletBalance": c.get("walletBalance") or "0",
                }
            )
    return out


async def _get_exchange_info() -> dict:
    """Bybit V5 instruments-info — 5 dk cache (exchangeInfo benzeri sadeleştirme)."""
    now = time.time()
    if _EXINFO_CACHE["data"] and (now - _EXINFO_CACHE["t"] < 300):
        return _EXINFO_CACHE["data"]
    ep = ENDPOINTS.get("INSTRUMENTS")
    if not ep:
        return {}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_LONG) as client:
        # Bybit: category=linear (USDT-M)
        url = BASE_URL + ep
        params = {"category": "linear"}
        full_url, headers = await build_signed_get(
            url, params, recv_window=RECV_WINDOW_MS
        )
        r = await arequest_with_retry(
            client,
            "GET",
            full_url,
            headers=headers,
            timeout=HTTP_TIMEOUT_LONG,
            max_retries=1,
        )
        data = r.json() or {}
        # exchangeInfo benzeri sade ‘symbols’ listesi üret
        symbols = []
        lst = (data.get("result") or {}).get("list") or []
        for it in lst:
            sym = str(it.get("symbol") or "").upper()
            quote = str(it.get("quoteCoin") or "").upper()
            if sym:
                symbols.append({"symbol": sym, "quoteAsset": quote})
        shaped = {"symbols": symbols}
        _EXINFO_CACHE.update({"t": now, "data": shaped})
        return shaped


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
    ep = ENDPOINTS.get("POSITION_RISK", "/v5/position/list")
    url = BASE_URL + ep
    params = {"category": "linear"}
    full_url, headers = await build_signed_get(url, params, recv_window=RECV_WINDOW_MS)

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
        data = r.json() or {}
        rows = (data.get("result") or {}).get("list") or []

    # yalnızca açık (positionAmt != 0)

    def fnum(v) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    # Bybit: size alanı (string) ≠ 0 olanları açık kabul
    open_pos = []
    for p in rows:
        try:
            if abs(fnum(p.get("size"))) > 0.0:
                open_pos.append(p)
        except Exception:
            continue
    if symbol:
        s = _normalize_symbol(symbol)
        legs = [
            {
                "symbol": str(p.get("symbol", "")).upper(),
                # Bybit: bacak için positionIdx (1=LONG, 2=SHORT); taraf metni döndürmüyoruz
                "unRealizedProfit": fnum(p.get("unrealisedPnl")),
                "positionAmt": fnum(p.get("size")),
                "entryPrice": fnum(p.get("avgPrice")),
                "leverage": fnum(p.get("leverage")),
                "markPrice": fnum(p.get("markPrice")),
                "liquidationPrice": fnum(p.get("liqPrice")),
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
            "unrealized": fnum(p.get("unrealisedPnl")),
            "position_amt": fnum(p.get("size")),
            "entry_price": fnum(p.get("avgPrice")),
            "leverage": fnum(p.get("leverage")),
            "mark_price": fnum(p.get("markPrice")),
            "liquidation_price": fnum(p.get("liqPrice")),
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
    Bybit V5: /v5/position/closed-pnl üzerinden kapatılan işlemlerin NET PnL toplamı.
    - symbol: 'BTCUSDT' gibi (opsiyonel)
    - since/until: datetime(UTC) (opsiyonel); sağlanmazsa geniş aralık kullanılır.
    Dönen: float (USDT cinsinden net PnL)
    """
    base = BASE_URL + "/v5/position/closed-pnl"
    total = 0.0
    cursor: Optional[str] = None

    # Zaman aralığı → ms
    start_ms: Optional[int] = (
        int(since.replace(tzinfo=timezone.utc).timestamp() * 1000) if since else None
    )
    end_ms: Optional[int] = (
        int(until.replace(tzinfo=timezone.utc).timestamp() * 1000) if until else None
    )
    sym = _normalize_symbol(symbol) if symbol else None

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_LONG) as client:
        while True:
            params: Dict[str, Any] = {"category": "linear", "limit": 200}
            if sym:
                params["symbol"] = sym
            if start_ms is not None:
                params["startTime"] = start_ms
            if end_ms is not None:
                params["endTime"] = end_ms
            if cursor:
                params["cursor"] = cursor

            full_url, headers = await build_signed_get(
                base, params, recv_window=RECV_WINDOW_MS
            )
            r = await arequest_with_retry(
                client,
                "GET",
                full_url,
                headers=headers,
                timeout=HTTP_TIMEOUT_LONG,
                max_retries=1,
            )
            r.raise_for_status()
            data = r.json() or {}
            result = data.get("result") if isinstance(data, dict) else None
            rows = result.get("list") if isinstance(result, dict) else None
            items = rows if isinstance(rows, list) else []

            for it in items:
                try:
                    total += float(it.get("closedPnl") or 0.0)
                except (TypeError, ValueError):
                    continue

            # sayfalama
            next_cursor = (
                result.get("nextPageCursor") if isinstance(result, dict) else None
            )
            if not next_cursor or not items:
                break
            cursor = str(next_cursor)

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
    # Bybit V5: /v5/execution/list — kapanışı oluşturan karşı yön fill’lerden VWAP
    try:
        sym = _normalize_symbol(symbol)
        want_side = "Sell" if (side or "").strip().lower() == "long" else "Buy"

        # opened_at → epoch ms (küçük güvenlik tamponu)
        start_ms = max(0, _to_ms(opened_at) - 60_000)

        url = BASE_URL + "/v5/execution/list"
        params: Dict[str, Any] = {
            "category": "linear",
            "symbol": sym,
            "startTime": start_ms,
            "limit": int(limit),
            # Not: order, cursor vb. gerekirse eklenir; tek sayfa genelde yeterli
        }
        full_url, headers = await build_signed_get(
            url, params, recv_window=RECV_WINDOW_MS
        )

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_LONG) as c:
            r = await arequest_with_retry(
                c,
                "GET",
                full_url,
                headers=headers,
                timeout=HTTP_TIMEOUT_LONG,
                max_retries=1,
            )
            r.raise_for_status()
            data = r.json() or {}

        # Yanıt: {"result":{"list":[{ "side":"Buy|Sell","execPrice":"..","execQty":"..","execTime":"..", ...}]}}
        result = data.get("result") if isinstance(data, dict) else None
        rows = result.get("list") if isinstance(result, dict) else None
        execs = rows if isinstance(rows, list) else []

        fills = []
        qty_sum = 0.0
        notional = 0.0
        last_t = None

        for it in execs:
            try:
                if str(it.get("side") or "") != want_side:
                    continue
                p = float(it.get("execPrice") or 0.0)
                q = float(it.get("execQty") or 0.0)
                t = int(it.get("execTime") or 0)
            except (TypeError, ValueError):
                continue
            if p <= 0.0 or q <= 0.0:
                continue
            fills.append((p, q, t))
            notional += p * q
            qty_sum += q
            last_t = t if (last_t is None or t > last_t) else last_t

        if qty_sum <= 0.0:
            return {"success": False, "message": "no closing fills found"}

        vwap = notional / qty_sum
        return {
            "success": True,
            "price": float(vwap),
            "time": int(last_t or 0),
            "fills": len(fills),
            "qty": float(qty_sum),
        }

    except httpx.HTTPStatusError as e:
        return {
            "success": False,
            "message": f"HTTP {e.response.status_code}: {e.response.text}",
        }
    except (httpx.RequestError, asyncio.TimeoutError, ValueError, TypeError) as e:
        return {"success": False, "message": str(e)}
