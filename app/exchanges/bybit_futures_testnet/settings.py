#!/usr/bin/env python3
# app/exchanges/bybit_futures_testnet/settings.py
# Python 3.9

from app.config import settings

EXCHANGE_NAME = "bybit_futures_testnet"

# HTTP_TIMEOUT_SYNC = settings.BYBIT_FUTURES_TESTNET_HTTP_TIMEOUT_SYNC or settings.HTTP_TIMEOUT_SYNC
# HTTP_TIMEOUT_SHORT = settings.BYBIT_FUTURES_TESTNET_HTTP_TIMEOUT_SHORT or settings.HTTP_TIMEOUT_SHORT
# HTTP_TIMEOUT_LONG = settings.BYBIT_FUTURES_TESTNET_HTTP_TIMEOUT_LONG or settings.HTTP_TIMEOUT_LONG
#
# # RECV_WINDOW_MS = settings.FUTURES_RECV_WINDOW_MS
# # RECV_WINDOW_LONG_MS = settings.FUTURES_RECV_WINDOW_LONG_MS
# RECV_WINDOW_MS = settings.BYBIT_FUTURES_TESTNET_RECV_WINDOW_MS or settings.FUTURES_RECV_WINDOW_MS
# RECV_WINDOW_LONG_MS = settings.BYBIT_FUTURES_TESTNET_RECV_WINDOW_LONG_MS or settings.FUTURES_RECV_WINDOW_LONG_MS

# Proje standardı: borsaya özel timeout/recv_window yok → global değerleri kullan
HTTP_TIMEOUT_SYNC = settings.HTTP_TIMEOUT_SYNC
HTTP_TIMEOUT_SHORT = settings.HTTP_TIMEOUT_SHORT
HTTP_TIMEOUT_LONG = settings.HTTP_TIMEOUT_LONG
FUTURES_RECV_WINDOW_MS = settings.FUTURES_RECV_WINDOW_MS
FUTURES_RECV_WINDOW_LONG_MS = settings.FUTURES_RECV_WINDOW_LONG_MS

# Binance modülleriyle aynı isimleri bekleyen yerler için alias:
RECV_WINDOW_MS = settings.FUTURES_RECV_WINDOW_MS or 5_000
RECV_WINDOW_LONG_MS = settings.FUTURES_RECV_WINDOW_LONG_MS or 15_000

# Settings modelinde alan yoksa AttributeError atmasın diye default=None veriyoruz
API_KEY = getattr(settings, f"{EXCHANGE_NAME.upper()}_API_KEY", None)
API_SECRET = getattr(settings, f"{EXCHANGE_NAME.upper()}_API_SECRET", None)

BASE_URL = "https://api-testnet.bybit.com"

POSITION_MODE = "one_way"  # "one_way" or "hedge"

# userTrades aralığı için geriye bakış (ms)
USERTRADES_LOOKBACK_MS = 120_000  # 60_000 kısa kalabilir bu yüzden 120 önerilir.

if not API_KEY or not API_SECRET:
    raise RuntimeError(
        f"[{EXCHANGE_NAME}] API key/secret eksik. .env dosyasına "
        f"{EXCHANGE_NAME.upper()}_API_KEY ve {EXCHANGE_NAME.upper()}_API_SECRET ekleyin."
    )

# Bybit v5 'interval' değerleri: 1, 3, 5, 15, 60, 240, D ...
TF_MAP = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "1h": "60",
    "4h": "240",
    "1d": "D",
}

KLINES_LIMIT_MAX = 1000  # Bybit v5 limit üstü 1000 (daha fazlasını sayfa sayfa ister)


def build_klines_params(symbol: str, interval: str, limit: int) -> dict:
    """
    Router'ın generic çağrısına Bybit'e uygun paramları verir.
    """
    return {
        "category": "linear",
        "symbol": symbol.upper(),
        # Kısa ve net: tanıdık string geldiyse TF_MAP ile çevir, değilse olduğu gibi gönder.
        "interval": TF_MAP.get(str(interval).lower(), str(interval).upper()),
        "limit": min(int(limit), KLINES_LIMIT_MAX),
    }


def parse_klines(payload: dict):
    """
    Bybit v5 /v5/market/kline yanıtını UI'nin beklediği forma çevirir.
    Dönen: [{t, time, o, h, l, c}, ...] (artan zaman)
    """
    res = (payload or {}).get("result") or {}
    rows = res.get("list") or []
    out = []
    for row in rows:
        try:
            ts = int(row[0])
            o = float(row[1])
            h = float(row[2])
            lo = float(row[3])  # 'l' yerine 'lo' → PEP8/E741 fix
            c = float(row[4])
        except (ValueError, TypeError, IndexError):
            continue
        time_s = ts // 1000 if ts > 10**10 else ts
        out.append({"t": ts, "time": time_s, "o": o, "h": h, "l": lo, "c": c})
    out.sort(key=lambda x: x["t"])
    return out


# Tüm REST endpoint path'leri burada (sadece path, domain değil)
ENDPOINTS = {
    "TIME": "/v5/market/time",
    "SERVER_TIME": "/v5/market/time",
    "INSTRUMENTS": "/v5/market/instruments-info",
    # UI/contract uyarıları için alias'lar:
    "EXCHANGE_INFO": "/v5/market/instruments-info",
    "KLINES": "/v5/market/kline",
    "ORDER": "/v5/order/create",
    "ORDER_STATUS": "/v5/order/realtime",
    "POSITION_RISK": "/v5/position/list",
    "BALANCE": "/v5/account/wallet-balance",
    "SWITCH_MODE": "/v5/position/switch-mode",
    "SET_LEVERAGE": "/v5/position/set-leverage",
    # Opsiyonel sözleşme anahtarları için alias:
    "POSITION_MODE_SET": "/v5/position/switch-mode",
    "POSITION_MODE_GET": "/v5/position/list",
    "LEVERAGE": "/v5/position/set-leverage",
    "INCOME": "/v5/position/closed-pnl",
}
