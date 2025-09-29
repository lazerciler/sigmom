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

# # Projede borsaya özel API anahtarları .env'de olmayabilir; testlerde ağa çıkmıyoruz.
# API_KEY = getattr(settings, f"{EXCHANGE_NAME.upper()}_API_KEY", "") or ""
# API_SECRET = getattr(settings, f"{EXCHANGE_NAME.upper()}_API_SECRET", "") or ""
# BASE_URL = "https://api-testnet.bybit.com"

# Settings modelinde alan yoksa AttributeError atmaması için default=None veriyoruz
API_KEY = getattr(settings, f"{EXCHANGE_NAME.upper()}_API_KEY", None)
API_SECRET = getattr(settings, f"{EXCHANGE_NAME.upper()}_API_SECRET", None)
BASE_URL = "https://api-testnet.bybit.com"

# Fail fast: anahtar/secret yoksa anlaşılır mesajla uygulamayı durdur.
if not API_KEY or not API_SECRET:
    raise RuntimeError(
        f"[{EXCHANGE_NAME}] API key/secret eksik. .env dosyasına "
        f"{EXCHANGE_NAME.upper()}_API_KEY ve {EXCHANGE_NAME.upper()}_API_SECRET ekleyin."
    )

POSITION_MODE = "one_way"  # "one_way" or "hedge"

# Hesap tipi: UNIFIED, CONTRACT veya AUTO (önce UNIFIED dener, hata alırsa CONTRACT)
ACCOUNT_TYPE = (
    (
        getattr(settings, f"{EXCHANGE_NAME.upper()}_ACCOUNT_TYPE", None)
        or getattr(settings, "BYBIT_ACCOUNT_TYPE", None)
        or "AUTO"
    )
    .strip()
    .upper()
)

# userTrades aralığı için geriye bakış (ms)
USERTRADES_LOOKBACK_MS = 120_000  # 60_000 kısa kalabilir bu yüzden 120 önerilir.

# ---- KLINES (public) için UI/Router entegrasyonu ----
# Router (/api/market/klines) 'tf' paramını kullanır ve burada TF_MAP üzerinden
# Bybit V5 aralığına çevrilir. Destekli değerler: 1 3 5 15 30 60 120 240 360 720 D W M
TF_MAP = {
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "2h": "120",
    "4h": "240",
    "6h": "360",
    "12h": "720",
    "1d": "D",
    "1w": "W",
    "1M": "M",
}


# Bybit V5 limit üst sınırı
KLINES_LIMIT_MAX = 1000

# Generic fallback için param anahtarları
KLINES_PARAMS = {"symbol": "symbol", "interval": "interval", "limit": "limit"}


# Router generiği tarafından çağrılır: Bybit V5 paramlarını kur
def build_klines_params(symbol: str, interval: str, limit: int) -> dict:
    # GET /v5/market/kline?category=linear&symbol=BTCUSDT&interval=1&limit=200
    return {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": int(limit),
    }


# Router generiği tarafından çağrılır: Bybit V5 cevabını normalize et
def parse_klines(j):
    """
    Beklenen: {"retCode":0, "result":{"list":[ [start,open,high,low,close,volume,...], ...]}}
    UI ms epoch beklediğinden 'start' ms olarak bırakılır.
    Geri dönüş: list[list] → [ts_ms, o, h, l, c]
    """
    try:
        rows = (j or {}).get("result", {}).get("list", []) or []
    except Exception:
        return []
    out = []
    for r in rows:
        try:
            ts = int(r[0])
            op = float(r[1])
            hi = float(r[2])
            lo = float(r[3])
            cl = float(r[4])
            out.append([ts, op, hi, lo, cl])
        except Exception:
            continue
    # Bybit genelde yeni→eski verir; grafik için kronolojik sırala
    out.sort(key=lambda x: x[0])
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
    "POSITION_SIDE_DUAL": "/v5/position/switch-mode",  # sadece alias; Binance uyarısını susturur
}
