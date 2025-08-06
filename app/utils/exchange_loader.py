#!/usr/bin/env python3
# app/utils/exchange_loader.py

import importlib


def load_execution_module(exchange: str):

    """Diğer modüller henüz yazılmadığından sadece öntanımlı borsa kullanılıyor"""

    if exchange == "binance_futures_testnet":
        from app.exchanges.binance_futures_testnet import sync, order_handler
    else:
        raise ValueError(f"Exchange not supported: {exchange}")

    """ Diğer modüller yazıldığığında aşaığıdaki yorumlanan kodlar devreye alınmalı"""

    # if exchange == "binance_futures_testnet":
    #     from app.exchanges.binance_futures_testnet import sync, order_handler
    # elif exchange == "binance_futures_mainnet":
    #     from app.exchanges.binance_futures_mainnet import sync, order_handler
    # elif exchange == "mexc_futures_mainnet":
    #     from app.exchanges.mexc_futures_mainnet import sync, order_handler
    # else:
    #     raise ValueError(f"Exchange not supported: {exchange}")

    return type("ExecutionModule", (), {"sync": sync, "order_handler": order_handler})()


def load_utils_module(exchange: str):
    try:
        return importlib.import_module(f"app.exchanges.{exchange}.utils")
    except ImportError as e:
        raise ImportError(f"{exchange} için utils modülü yüklenemedi: {e}")
