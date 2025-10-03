#!/usr/bin/env python3
# app/utils/exchange_loader.py
# Python 3.9+

import importlib
from functools import lru_cache
from typing import Optional, Dict, Any

try:
    # Projede genelde böyle kullanılıyor
    from app.config import settings as app_settings  # type: ignore
except Exception:

    class _Dummy:
        DEFAULT_EXCHANGE = "binance_futures_mainnet"

    app_settings = _Dummy()  # type: ignore

# ---- Tanımlar ---------------------------------------------------------------

# Tüm modül klasör adlarını "gerçek" isim olarak tutuyoruz.
ALLOWED_EXCHANGES = {
    "binance_futures_mainnet",
    "binance_futures_testnet",
    "bybit_futures_testnet",
    "mexc_futures",
}

# Kullanıcıdan/UI'dan gelen serbest metni normalize etmek için kısa yollar.
ALIASES = {
    # Binance
    "binance": "binance_futures_mainnet",
    "binance_futures": "binance_futures_mainnet",
    "binance_mainnet": "binance_futures_mainnet",
    "binance_futures_mainnet": "binance_futures_mainnet",
    "binance_testnet": "binance_futures_testnet",
    "binance_futures_testnet": "binance_futures_testnet",
    # Bybit
    "bybit": "bybit_futures_testnet",
    "bybit_futures_testnet": "bybit_futures_testnet",
    # MEXC (şimdilik tek varyant)
    "mexc": "mexc_futures",
    "mexc_futures": "mexc_futures",
}


# ---- Yardımcılar ------------------------------------------------------------


def _clean(s: str) -> str:
    return s.replace("-", "_").replace(" ", "_").strip().lower()


def normalize_exchange(name: Optional[str]) -> str:
    """
    Serbest metin bir borsa değerini kesin klasör adına dönüştürür.
    Hata: desteklenmeyen isim → ValueError (asla testnet'e sessizce düşmez).
    """
    if not name or not str(name).strip():
        # settings.DEFAULT_EXCHANGE zorunlu kaynaktır
        name = getattr(app_settings, "DEFAULT_EXCHANGE", "binance_futures_mainnet")

    key = _clean(str(name))
    # Önce doğrudan ALLOWED kontrolü
    if key in ALLOWED_EXCHANGES:
        return key
    # Sonra alias tablosu
    if key in ALIASES:
        real = ALIASES[key]
        if real in ALLOWED_EXCHANGES:
            return real

    raise ValueError(f"Unsupported exchange: {name!r}")


def _import(path: str):
    return importlib.import_module(path)


# ---- Yükleyiciler (LRU cache ile hızlı) -------------------------------------


@lru_cache(maxsize=64)
def load_modules(exchange: str) -> Dict[str, Any]:
    """
    Bir borsa için temel modülleri yükler ve döndürür.
    Hata: modül eksikse ValueError yükseltir (fallback yok).
    """
    ex = normalize_exchange(exchange)
    base = f"app.exchanges.{ex}"

    try:
        return {
            "name": ex,
            "account": _import(f"{base}.account"),
            "positions": _import(f"{base}.positions"),
            "order_handler": _import(f"{base}.order_handler"),
            "settings": _import(f"{base}.settings"),
            "sync": _import(f"{base}.sync"),
            "utils": _import(f"{base}.utils"),
        }
    except ModuleNotFoundError as e:
        # Kısmi yüklemelerde de açık biçimde patlayalım
        raise ValueError(f"Exchange modules missing for '{ex}': {e}") from e


# ---- İnce taneli yükleyiciler (kullanım kolaylığı) --------------------------


def load_utils(exchange: str):
    return load_modules(exchange)["utils"]


def load_settings(exchange: str):
    return load_modules(exchange)["settings"]


def load_order_handler(exchange: str):
    return load_modules(exchange)["order_handler"]


def load_positions(exchange: str):
    return load_modules(exchange)["positions"]


def load_account(exchange: str):
    return load_modules(exchange)["account"]


def load_sync(exchange: str):
    return load_modules(exchange)["sync"]


# ---- Geriyedönük uyumluluk katmanı -----------------------------------------


def resolve_exchange(name: Optional[str] = None) -> str:
    """
    ESKİ DAVRANIŞI DÜZELTMİŞ sürüm:
    - name verilirse normalize edilir ve DOĞRUDAN o kullanılır.
    - name None ise settings.DEFAULT_EXCHANGE kullanılır.
    - Hiçbir durumda sessizce testnet'e fallback YOK.
    """
    return normalize_exchange(name)


def load_utils_module(exchange: str):
    """
    Eski adlandırma: utils modülünü döndür.
    Yeni sistemle aynı garantileri verir (fallback yok).
    """
    return load_utils(exchange)


def load_execution_module(exchange: str):
    """
    Eski kullanım için: sadece sync ve order_handler dönen küçük bir obje.
    """
    mods = load_modules(exchange)
    return type(
        "ExecutionModule",
        (),
        {
            "name": mods["name"],
            "sync": mods["sync"],
            "order_handler": mods["order_handler"],
        },
    )()
