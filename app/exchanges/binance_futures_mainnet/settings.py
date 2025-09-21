#!/usr/bin/env python3
# app/exchanges/binance_futures_mainnet/settings.py
# Python 3.9
from app.config import settings

EXCHANGE_NAME = "binance_futures_mainnet"

API_KEY = getattr(settings, f"{EXCHANGE_NAME.upper()}_API_KEY")
API_SECRET = getattr(settings, f"{EXCHANGE_NAME.upper()}_API_SECRET")
BASE_URL = "https://fapi.binance.com"

POSITION_MODE = "one_way"  # "one_way" or "hedge"

# userTrades aralığı için geriye bakış (ms)
USERTRADES_LOOKBACK_MS = 120_000  # 60_000 kısa kalabilir bu yüzden 120_000 önerilir.
# Kısa açıklama: startTime tamponu, /fapi/v1/userTrades sorgusunda başlangıç zamanını açılış timestamp’ından
# bir miktar geriye çekmemiz.
# Neden? Exchange ile bizim kayıt saatimiz arasında küçük kaymalar olabilir
# (sistem saati farkı, ağ gecikmesi, order’ın borsada kayda geçme zamanı vs.).
# Tampon küçük ise kapanışı yapan fill’leri kaçırabiliriz; biraz büyük yapınca güvenli bölge oluştururuz.
#
# Etkisi:
#
# Küçük tampon (örn. 0–30 sn): Bazı senaryolarda kapanış fill’i sorgu aralığının dışında kalabilir → fiyat bulunamaz.
#
# Orta tampon (örn. 60–180 sn): Güvenlik alanı; kapanış fill’ini neredeyse her zaman yakalar. (Biz 60 sn ile yakaladık.)
#
# Çok büyük tampon (örn. dakikalarca): Sorgu daha fazla satır getirir → biraz daha yavaş,
# API kotasına (rate limit) yaklaşma riski artar.
# Gereksiz eski işlemler dönebilir ama biz zaten side / positionSide ile filtrelediğimiz için
# doğruluk bozulmaz; sadece gereksiz veri gelir.
#
# Öneri: 120 sn varsayılan gayet iyi. Çok yoğun/ping yüksek ortamlarda 180–300 sn düşünülebilir.

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
