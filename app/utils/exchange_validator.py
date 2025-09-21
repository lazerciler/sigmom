#!/usr/bin/env python3
# app/utils/exchange_validator.py
# Python 3.9

import importlib
import logging
from typing import List, Tuple
from app.exchanges.contract import (
    REQUIRED_SETTINGS_VARS,
    REQUIRED_ENDPOINT_KEYS,
    OPTIONAL_ENDPOINT_KEYS,
    REQUIRED_UTIL_FUNCS,
    OPTIONAL_UTIL_FUNCS,
)

logger = logging.getLogger("contract")


def validate_exchange(name: str) -> List[str]:
    errs: List[str] = []
    try:
        S = importlib.import_module(f"app.exchanges.{name}.settings")
        U = importlib.import_module(f"app.exchanges.{name}.utils")
    except Exception as e:
        return [f"[{name}] import failed: {e}"]

    # settings alanları
    for var in REQUIRED_SETTINGS_VARS:
        if not hasattr(S, var):
            errs.append(f"[{name}] settings.{var} missing")

    # ENDPOINTS anahtarları (çekirdek)
    endpoints = getattr(S, "ENDPOINTS", {})
    missing = [k for k in REQUIRED_ENDPOINT_KEYS if k not in endpoints]
    if missing:
        errs.append(f"[{name}] ENDPOINTS missing keys: {', '.join(missing)}")
    # Opsiyoneller: eksikse hata değil, uyarı
    opt_missing = [k for k in OPTIONAL_ENDPOINT_KEYS if k not in endpoints]
    if opt_missing:
        logger.warning(
            "[%s] optional ENDPOINTS missing keys: %s", name, ", ".join(opt_missing)
        )

    # utils fonksiyonları (çekirdek)
    for fn in REQUIRED_UTIL_FUNCS:
        if not hasattr(U, fn):
            errs.append(f"[{name}] utils.{fn} missing")
    # Opsiyonel util fonksiyonları
    for fn in OPTIONAL_UTIL_FUNCS:
        if not hasattr(U, fn):
            logger.warning("[%s] optional utils.%s missing", name, fn)

    return errs


def validate_all(exchanges: List[str]) -> List[Tuple[str, List[str]]]:
    report: List[Tuple[str, List[str]]] = []
    for ex in exchanges:
        ex = ex.strip()
        if not ex:
            continue
        errs = validate_exchange(ex)
        if errs:
            report.append((ex, errs))
    return report
