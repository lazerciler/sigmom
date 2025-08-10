#!/usr/bin/env python3
# app/exchanges/binance_futures_testnet/settings.py
# Python 3.9
from app.config import settings

EXCHANGE_NAME = "binance_futures_testnet"

API_KEY = getattr(settings, f"{EXCHANGE_NAME.upper()}_API_KEY")
API_SECRET = getattr(settings, f"{EXCHANGE_NAME.upper()}_API_SECRET")
BASE_URL = "https://testnet.binancefuture.com"
