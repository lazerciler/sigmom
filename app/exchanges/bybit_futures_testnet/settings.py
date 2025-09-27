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
RECV_WINDOW_MS = FUTURES_RECV_WINDOW_MS
RECV_WINDOW_LONG_MS = FUTURES_RECV_WINDOW_LONG_MS

# Projede borsaya özel API anahtarları .env'de olmayabilir; testlerde ağa çıkmıyoruz.
API_KEY = getattr(settings, f"{EXCHANGE_NAME.upper()}_API_KEY", "") or ""
API_SECRET = getattr(settings, f"{EXCHANGE_NAME.upper()}_API_SECRET", "") or ""
BASE_URL = "https://api-testnet.bybit.com"

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
