#!/usr/bin/env python3
# app/services/entry_lines_helpers.py
# Python 3.9

"""Helpers for preparing panel data payloads."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence

SymbolLike = Optional[str]
RowLike = Any


def _normalize_symbol(value: SymbolLike) -> str:
    """Return an upper-case, trimmed symbol representation."""
    return str(value or "").strip().upper()


def _get_value(row: RowLike, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key, None)


def _filter_by_symbol(rows: Sequence[RowLike], target: SymbolLike) -> List[RowLike]:
    """Return rows whose symbol matches ``target``.

    Symbols are normalised by stripping leading/trailing whitespace and converting to
    upper-case before comparison.  This mirrors how symbols are presented elsewhere in
    the application and guards against subtle mismatches that might be introduced by
    user input or external APIs.
    """

    if target is None:
        return list(rows)

    normalized = _normalize_symbol(target)
    if not normalized:
        return []

    matched: List[RowLike] = []
    for row in rows:
        row_symbol = _normalize_symbol(_get_value(row, "symbol"))
        if row_symbol and row_symbol == normalized:
            matched.append(row)
    return matched


_ENTRY_KEYS = (
    "avg_entry_price",
    "avg_price",
    "entry_avg",
    "entry_price",
    "price",
)


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_entry_price(row: RowLike) -> Optional[float]:
    for key in _ENTRY_KEYS:
        price = _get_value(row, key)
        numeric = _to_float(price)
        if numeric is not None:
            return numeric
    return None


def _normalize_side(value: Any) -> Optional[str]:
    side = str(value or "").strip().lower()
    if not side:
        return None
    if side in {"long", "buy", "l"}:
        return "long"
    if side in {"short", "sell", "s"}:
        return "short"
    return None


def _extract_side(row: RowLike) -> Optional[str]:
    for key in ("side", "position_side", "positionSide", "pos_side", "posSide", "ps"):
        value = _get_value(row, key)
        normalised = _normalize_side(value)
        if normalised:
            return normalised
    return None


def _timestamp_value(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, str):
        try:
            return float(value)
        except (TypeError, ValueError):
            try:
                text = value.strip()
                if text.endswith("Z"):
                    text = text[:-1] + "+00:00"
                return datetime.fromisoformat(text).timestamp()
            except ValueError:
                return 0.0
    return 0.0


def _extract_timestamp(row: RowLike) -> float:
    for key in ("timestamp", "opened_at", "created_at", "updated_at"):
        value = _get_value(row, key)
        if value is not None:
            return _timestamp_value(value)
    return 0.0


def calculate_entry_lines(
    rows: Sequence[RowLike],
    symbol: SymbolLike = None,
) -> Dict[str, Optional[float]]:
    """Calculate representative entry prices per side for ``symbol``.

    Parameters
    ----------
    rows:
        Iterable of database rows or dictionary-like objects describing open trades.
    symbol:
        Optional symbol used to filter ``rows``.  Comparison is performed using a
        trimmed, upper-case representation so that values such as ``" BTCUSDT "`` map to
        the canonical symbol ``"BTCUSDT"``.

    Returns
    -------
    dict
        Always returns a mapping with **both** keys: ``{"long": <float|None>, "short": <float|None>}``.
        Each value is either a ``float`` (most recent entry per side) or ``None`` if not available.
    """

    relevant_rows = _filter_by_symbol(rows, symbol)
    if not relevant_rows:
        return {"long": None, "short": None}

    result = {"long": None, "short": None}

    # En eski → en yeni sırala; her side için "en son" değeri saklayacağız
    for row in sorted(relevant_rows, key=_extract_timestamp):
        side = _extract_side(row)
        price = _extract_entry_price(row)
        if price is None:
            continue
        # Her zaman float (tip güvenliği)
        price = float(price)
        if side == "short":
            result["short"] = price
        elif side == "long":
            result["long"] = price
        else:
            if result["long"] is None:
                result["long"] = price
            elif result["short"] is None:
                result["short"] = price
    return result


__all__ = ["calculate_entry_lines"]
