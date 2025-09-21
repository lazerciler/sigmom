#!/usr/bin/env python3
# app/exchanges/contract.py
# Python 3.9

REQUIRED_SETTINGS_VARS = ("EXCHANGE_NAME", "POSITION_MODE", "BASE_URL", "ENDPOINTS")

REQUIRED_ENDPOINT_KEYS = {"TIME", "POSITION_RISK", "POSITION_SIDE_DUAL"}

# Opsiyonel endpoint anahtarları (varsa doğrulanır, yoksa sadece uyarı verilir):
OPTIONAL_ENDPOINT_KEYS = {
    "ORDER",
    "LEVERAGE",
    "KLINES",
    "EXCHANGE_INFO",
    "BALANCE",
    "INCOME",
}

# Zorunlu util fonksiyonları:
REQUIRED_UTIL_FUNCS = ("get_position_mode", "set_position_mode")

# Opsiyonel util fonksiyonları:
OPTIONAL_UTIL_FUNCS = ("get_klines",)
