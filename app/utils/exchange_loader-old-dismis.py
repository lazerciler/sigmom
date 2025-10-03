#!/usr/bin/env python3
# app/utils/exchange_loader.py
# Python 3.9

import importlib
from app.config import settings as app_settings


def load_execution_module(exchange: str):
    """
    Eski kullanım için geriye dönük uyumluluk.
    exchange == "<module_name>" bekler ve o modülün sync/order_handler'ını döner.
    """
    if exchange == "binance_futures_testnet":
        from app.exchanges.binance_futures_testnet import sync, order_handler
    elif exchange == "binance_futures_mainnet":
        from app.exchanges.binance_futures_mainnet import sync, order_handler
    elif exchange == "bybit_futures_testnet":
        from app.exchanges.bybit_futures_testnet import sync, order_handler
    elif exchange == "mexc_futures":
        from app.exchanges.mexc_futures import sync, order_handler
    else:
        raise ValueError(f"Exchange not supported: {exchange}")

    # Diğer modüller yazıldığında aynı kalıbı çoğalt
    # elif exchange == "binance_futures_mainnet":
    #     from app.exchanges.binance_futures_mainnet import sync, order_handler
    # elif exchange == "mexc_futures_mainnet":
    #     from app.exchanges.mexc_futures_mainnet import sync, order_handler
    # else:
    #     raise ValueError(f"Exchange not supported: {exchange}")

    # return type("ExecutionModule", (), {"sync": sync, "order_handler": order_handler})()
    return type(
        "ExecutionModule",
        (),
        {"name": exchange, "sync": sync, "order_handler": order_handler},
    )()


def load_utils_module(exchange: str):
    """
    Eski ad: utils modülünü dinamik yükler.
    """
    try:
        return importlib.import_module(f"app.exchanges.{exchange}.utils")
    except ImportError as e:
        raise ImportError(f"{exchange} için utils modülü yüklenemedi: {e}")


# --- Yeni yardımcılar: DEFAULT_EXCHANGE kullanımı ve sade importlar ---------


def resolve_exchange(name: str = None) -> str:
    """
    URL parametresi veya None → settings.DEFAULT_EXCHANGE'e düş.
    Modül yüklenemezse yine DEFAULT'a düşer.
    """
    default_ex = getattr(app_settings, "DEFAULT_EXCHANGE", "binance_futures_testnet")
    ex = (name or default_ex).strip()
    try:
        importlib.import_module(f"app.exchanges.{ex}.utils")
        return ex
    except Exception:
        # Seçilen borsa yüklenemediyse, güvenli düşüş
        return default_ex


def load_utils(ex: str):
    """app.exchanges.<ex>.utils modülünü döndürür."""
    return importlib.import_module(f"app.exchanges.{ex}.utils")


def load_settings(ex: str):
    """app.exchanges.<ex>.settings modülünü döndürür."""
    return importlib.import_module(f"app.exchanges.{ex}.settings")


def load_order_handler(ex: str):
    """app.exchanges.<ex>.order_handler modülünü döndürür."""
    return importlib.import_module(f"app.exchanges.{ex}.order_handler")
