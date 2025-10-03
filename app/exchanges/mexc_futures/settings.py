#!/usr/bin/env python3
# app/exchanges/mexc_futures/settings.py
# Python 3.9

from app.config import settings

EXCHANGE_NAME = "mexc_futures"

# HTTP_TIMEOUT_SYNC = settings.MEXC_FUTURES_HTTP_TIMEOUT_SYNC or settings.HTTP_TIMEOUT_SYNC
# HTTP_TIMEOUT_SHORT = settings.MEXC_FUTURES_HTTP_TIMEOUT_SHORT or settings.HTTP_TIMEOUT_SHORT
# HTTP_TIMEOUT_LONG = settings.MEXC_FUTURES_HTTP_TIMEOUT_LONG or settings.HTTP_TIMEOUT_LONG

HTTP_TIMEOUT_SYNC = settings.HTTP_TIMEOUT_SYNC
HTTP_TIMEOUT_SHORT = settings.HTTP_TIMEOUT_SHORT
HTTP_TIMEOUT_LONG = settings.HTTP_TIMEOUT_LONG

# Settings modelinde alan yoksa AttributeError atmasın diye default=None veriyoruz
API_KEY = getattr(settings, f"{EXCHANGE_NAME.upper()}_API_KEY", None)
API_SECRET = getattr(settings, f"{EXCHANGE_NAME.upper()}_API_SECRET", None)

# MEXC futures base URL
BASE_URL = "https://contract.mexc.com"

if not API_KEY or not API_SECRET:
    raise RuntimeError(
        f"[{EXCHANGE_NAME}] API key/secret eksik. .env dosyasına "
        f"{EXCHANGE_NAME.upper()}_API_KEY ve {EXCHANGE_NAME.upper()}_API_SECRET ekleyin."
    )

# Proje genel tutarlılık: one_way | hedge (MEXC: 1=hedge, 2=one-way)
POSITION_MODE = "one_way"

# Recv-window (MEXC header’da, ms; doküman max 60s önerir)
RECV_WINDOW_MS = settings.FUTURES_RECV_WINDOW_MS or 5_000
RECV_WINDOW_LONG_MS = settings.FUTURES_RECV_WINDOW_LONG_MS or 15_000

# Kline haritaları (router 'tf' → borsa interval)
TF_MAP = {
    "1m": "Min1",
    "5m": "Min5",
    "15m": "Min15",
    "30m": "Min30",
    "1h": "Min60",
    "4h": "Hour4",
    "8h": "Hour8",
    "1d": "Day1",
    "1w": "Week1",
    "1M": "Month1",
}


# Router limit emniyeti (MEXC max 1000)
KLINES_LIMIT_MAX = 1000

# Router'ın beklediği path/param sözleşmesi:
# MEXC klines: GET /api/v1/contract/kline/{symbol}?interval=Min15&limit=200
KLINES_PATH = "/api/v1/contract/kline/{symbol}"
KLINES_PARAMS = {"symbol": "symbol", "interval": "interval", "limit": "limit"}


# Sembol dönüştürücü (BTCUSDT → BTC_USDT)
def normalize_symbol(sym: str) -> str:
    s = (sym or "").upper().replace("-", "_").replace(":", "_")
    if s.endswith(".P"):
        s = s[:-2]
    if "_" not in s and len(s) >= 6:
        s = s[:-4] + "_" + s[-4:]
    return s


# Kline çıktısını router'ın _normalize formatına çevir
def parse_klines(j):
    # MEXC bazen {"data":[...]} veya {"kline":[...]} döndürebilir; bazen doğrudan liste.
    data = j.get("data") if isinstance(j, dict) else j
    if isinstance(data, dict) and "kline" in data:
        data = data["kline"]
    out = []
    if isinstance(data, list):
        for it in data:
            if isinstance(it, (list, tuple)) and len(it) >= 5:
                # # [t,o,h,l,c,(v...)]
                # out.append({"t": int(it[0]), "o": float(it[1]), "h": float(it[2]),
                #             "l": float(it[3]), "c": float(it[4])})

                # [t,o,h,l,c,(v...)]  → t: saniye/ms olabilir
                t_raw = int(it[0])
                t_ms = t_raw * 1000 if t_raw < 10**12 else t_raw  # <1e12 ise saniyedir
                out.append(
                    {
                        "t": t_ms,
                        "o": float(it[1]),
                        "h": float(it[2]),
                        "l": float(it[3]),
                        "c": float(it[4]),
                    }
                )
            elif isinstance(it, dict):
                t = it.get("t") or it.get("time") or it.get("T") or it.get("ts")
                op = it.get("o") or it.get("open")
                hi = it.get("h") or it.get("high")
                lo = it.get("l") or it.get("low")
                cl = it.get("c") or it.get("close")
                if None not in (t, op, hi, lo, cl):
                    t_raw = int(t)
                    t_ms = t_raw * 1000 if t_raw < 10**12 else t_raw
                    out.append(
                        {
                            "t": t_ms,
                            "o": float(op),
                            "h": float(hi),
                            "l": float(lo),
                            "c": float(cl),
                        }
                    )
    # return out
    # grafikler artan zamana göre ister
    out.sort(key=lambda row: row["t"])
    return out


# Endpoints (sadece path)
# ENDPOINTS = {
#     # Market
#     "SERVER_TIME": "/api/v1/contract/ping",
#     "CONTRACT_DETAIL": "/api/v1/contract/detail",
#     "KLINE": "/api/v1/contract/kline/{symbol}",
#
#     # Private / Account-Trade
#     "ASSETS": "/api/v1/private/account/assets",
#     "OPEN_POSITIONS": "/api/v1/private/position/open_positions",
#     "POSITION_MODE_GET": "/api/v1/private/position/position_mode",
#     "POSITION_MODE_SET": "/api/v1/private/position/change_position_mode",
#     "LEVERAGE_SET": "/api/v1/private/position/change_leverage",
#     "ORDER_SUBMIT": "/api/v1/private/order/submit",
#     "ORDER_QUERY_BATCH": "/api/v1/private/order/batch_query",
#     "ORDER_DEAL_DETAILS": "/api/v1/private/order/deal_details/{order_id}",
#     "ORDER_DEALS_LIST": "/api/v1/private/order/list/order_deals",
# }


ENDPOINTS = {
    # ---- Market
    "SERVER_TIME": "/api/v1/contract/ping",
    "CONTRACT_DETAIL": "/api/v1/contract/detail",
    # tekil isim MEXC; projedeki opsiyonel 'KLINES' beklentisine eşlemek için utils'te wrapper var
    "KLINE": "/api/v1/contract/kline/{symbol}",
    # ---- Private / Account-Trade
    "ASSETS": "/api/v1/private/account/assets",
    "OPEN_POSITIONS": "/api/v1/private/position/open_positions",
    "POSITION_MODE_GET": "/api/v1/private/position/position_mode",
    "POSITION_MODE_SET": "/api/v1/private/position/change_position_mode",
    "LEVERAGE_SET": "/api/v1/private/position/change_leverage",
    "ORDER_SUBMIT": "/api/v1/private/order/submit",
    "ORDER_QUERY_BATCH": "/api/v1/private/order/batch_query",
    "ORDER_DEAL_DETAILS": "/api/v1/private/order/deal_details/{order_id}",
    "ORDER_DEALS_LIST": "/api/v1/private/order/list/order_deals",
    # ---- Proje sözleşmesi için alias anahtarlar (opsiyonelleri susturur)
    # REQUIRED: TIME
    "TIME": "/api/v1/contract/ping",  # = SERVER_TIME
    # OPTIONALS (alias)
    "KLINES": "/api/v1/contract/kline/{symbol}",  # wrapper utils.get_klines kullanır
    "BALANCE": "/api/v1/private/account/assets",  # = ASSETS
    "POSITION_SIDE_DUAL": "/api/v1/private/position/position_mode",  # = POSITION_MODE_GET
    "POSITION_RISK": "/api/v1/private/position/open_positions",  # = OPEN_POSITIONS
    "EXCHANGE_INFO": "/api/v1/contract/detail",  # = CONTRACT_DETAIL
    "LEVERAGE": "/api/v1/private/position/change_leverage",  # = LEVERAGE_SET
    "INCOME": "/api/v1/private/order/list/order_deals",  # = ORDER_DEALS_LIST
    "ORDER": "/api/v1/private/order/submit",  # = ORDER_SUBMIT
}
