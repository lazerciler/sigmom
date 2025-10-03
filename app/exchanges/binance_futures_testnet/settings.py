#!/usr/bin/env python3
# app/exchanges/binance_futures_testnet/settings.py
# Python 3.9

from app.config import settings

EXCHANGE_NAME = "binance_futures_testnet"

HTTP_TIMEOUT_SYNC = (
    settings.BINANCE_FUTURES_TESTNET_HTTP_TIMEOUT_SYNC or settings.HTTP_TIMEOUT_SYNC
)
HTTP_TIMEOUT_SHORT = (
    settings.BINANCE_FUTURES_TESTNET_HTTP_TIMEOUT_SHORT or settings.HTTP_TIMEOUT_SHORT
)
HTTP_TIMEOUT_LONG = (
    settings.BINANCE_FUTURES_TESTNET_HTTP_TIMEOUT_LONG or settings.HTTP_TIMEOUT_LONG
)

# RECV_WINDOW_MS = settings.FUTURES_RECV_WINDOW_MS
# RECV_WINDOW_LONG_MS = settings.FUTURES_RECV_WINDOW_LONG_MS
RECV_WINDOW_MS = (
    settings.BINANCE_FUTURES_TESTNET_RECV_WINDOW_MS or settings.FUTURES_RECV_WINDOW_MS
)
RECV_WINDOW_LONG_MS = (
    settings.BINANCE_FUTURES_TESTNET_RECV_WINDOW_LONG_MS
    or settings.FUTURES_RECV_WINDOW_LONG_MS
)

# API_KEY = getattr(settings, f"{EXCHANGE_NAME.upper()}_API_KEY")
# API_SECRET = getattr(settings, f"{EXCHANGE_NAME.upper()}_API_SECRET")
# BASE_URL = "https://testnet.binancefuture.com"

# Settings modelinde alan yoksa AttributeError atmaması için default=None veriyoruz
API_KEY = getattr(settings, f"{EXCHANGE_NAME.upper()}_API_KEY", None)
API_SECRET = getattr(settings, f"{EXCHANGE_NAME.upper()}_API_SECRET", None)
BASE_URL = "https://testnet.binancefuture.com"

# Fail fast: anahtar/secret yoksa anlaşılır mesajla uygulamayı durdur.
if not API_KEY or not API_SECRET:
    raise RuntimeError(
        f"[{EXCHANGE_NAME}] API key/secret eksik. .env dosyasına "
        f"{EXCHANGE_NAME.upper()}_API_KEY ve {EXCHANGE_NAME.upper()}_API_SECRET ekleyin."
    )

POSITION_MODE = "one_way"  # "one_way" or "hedge"

# userTrades aralığı için geriye bakış (ms)
USERTRADES_LOOKBACK_MS = 120_000  # 60_000 kısa kalabilir bu yüzden 120 önerilir.

KLINES_PATH = "/fapi/v1/klines"

KLINES_PARAMS = {"symbol": "symbol", "interval": "interval", "limit": "limit"}

KLINES_LIMIT_MAX = 1500

TF_MAP = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "6h": "6h",
    "8h": "8h",
    "12h": "12h",
    "1d": "1d",
    "3d": "3d",
    "1w": "1w",
    "1M": "1M",
}

# Tüm REST endpoint path'leri burada (sadece path, domain değil)
ENDPOINTS = {
    "LEVERAGE": "/fapi/v1/leverage",
    "ORDER": "/fapi/v1/order",
    "POSITION_RISK": "/fapi/v2/positionRisk",
    "BALANCE": "/fapi/v2/balance",
    "TIME": "/fapi/v1/time",
    "EXCHANGE_INFO": "/fapi/v1/exchangeInfo",
    "POSITION_SIDE_DUAL": "/fapi/v1/positionSide/dual",  # GET/POST
    "INCOME": "/fapi/v1/income",
    "USER_TRADES": "/fapi/v1/userTrades",
}
