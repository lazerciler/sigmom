#!/usr/bin/env python3
# tests/test_quick_balance_helpers.py
# Python 3.9

from __future__ import annotations

import inspect
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Sequence

DEFAULT_BALANCE_FALLBACK = Decimal("1000")


def to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _safe_upper(val: Optional[str]) -> str:
    return str(val or "").upper()


def extract_mode(payload: Any) -> Optional[str]:
    if isinstance(payload, dict):
        raw_mode = str(
            payload.get("mode")
            or payload.get("position_mode")
            or payload.get("positionMode")
            or ""
        ).lower()
        if raw_mode in {"hedge", "one_way"}:
            return raw_mode
    return None


def has_open_side(open_rows: Sequence[Any], side: str) -> bool:
    target = side.lower()
    for row in open_rows:
        row_side = str(getattr(row, "side", "") or "").lower()
        if row_side == target:
            return True
    return False


def extract_unrealized_breakdown(
    payload: Any,
    symbol: str,
    open_rows: Sequence[Any],
    decimal_converter=to_decimal,
) -> Dict[str, Any]:
    sym = _safe_upper(symbol)
    has_long_open = has_open_side(open_rows, "long")
    has_short_open = has_open_side(open_rows, "short")

    out: Dict[str, Any] = {
        "long": Decimal("0"),
        "short": Decimal("0"),
        "has_long": has_long_open,
        "has_short": has_short_open,
        "mode": extract_mode(payload),
        "source": "none",
    }

    if isinstance(payload, dict) and isinstance(payload.get("legs"), dict):
        legs = payload.get("legs") or {}
        out["long"] = decimal_converter(legs.get("long"))
        out["short"] = decimal_converter(legs.get("short"))
        out["has_long"] = has_long_open or (out["long"] != 0)
        out["has_short"] = has_short_open or (out["short"] != 0)
        if out["long"] == 0 and out["short"] == 0:
            total = decimal_converter(payload.get("unrealized") or payload.get("upnl"))
            if total != 0:
                if has_long_open:
                    out["long"] = total
                    out["has_long"] = True
                if has_short_open:
                    out["short"] = total
                    out["has_short"] = True
        out["source"] = "legs"
        return out

    arr: Optional[Sequence[Any]] = None
    if isinstance(payload, list):
        arr = payload
    elif isinstance(payload, dict):
        for key in ("items", "positions", "list", "data"):
            maybe = payload.get(key)
            if isinstance(maybe, list):
                arr = maybe
                break

    if arr is not None:
        total_long = Decimal("0")
        total_short = Decimal("0")
        has_long = has_long_open
        has_short = has_short_open
        for item in arr:
            if isinstance(item, dict):
                psym = _safe_upper(item.get("symbol") or item.get("s"))
                if sym and psym and psym != sym:
                    continue
                raw_unreal = (
                    item.get("unrealized")
                    or item.get("unRealizedProfit")
                    or item.get("unrealizedPnl")
                    or item.get("upnl")
                    or item.get("pnl")
                )
                unreal = decimal_converter(raw_unreal)
                if unreal == 0:
                    qty = decimal_converter(
                        item.get("positionAmt")
                        or item.get("qty")
                        or item.get("size")
                        or item.get("position_size")
                    )
                    entry = decimal_converter(
                        item.get("entryPrice")
                        or item.get("avgPrice")
                        or item.get("entry")
                    )
                    mark = decimal_converter(
                        item.get("markPrice") or item.get("price") or item.get("mark")
                    )
                    if qty != 0 and entry != 0 and mark != 0:
                        abs_qty = abs(qty)
                        unreal = (
                            (mark - entry) * abs_qty
                            if qty > 0
                            else (entry - mark) * abs_qty
                        )
                side = str(item.get("side") or "").lower()
                if not side:
                    qty = decimal_converter(
                        item.get("positionAmt")
                        or item.get("qty")
                        or item.get("size")
                        or item.get("position_size")
                    )
                    if qty < 0:
                        side = "short"
                    elif qty > 0:
                        side = "long"
                if side == "short":
                    total_short += unreal
                    has_short = True
                else:
                    total_long += unreal
                    has_long = True
        out["long"] = total_long
        out["short"] = total_short
        out["has_long"] = has_long
        out["has_short"] = has_short
        out["source"] = "positions"
        return out

    agg_candidate: Any = None
    if isinstance(payload, dict):
        agg_candidate = (
            payload.get("unrealized")
            or payload.get("upnl")
            or payload.get("unrealizedPnl")
        )
    else:
        agg_candidate = payload
    total = decimal_converter(agg_candidate)
    if total != 0:
        if has_long_open and not has_short_open:
            out["long"] = total
            out["has_long"] = True
            out["source"] = "fallback"
        elif has_short_open and not has_long_open:
            out["short"] = total
            out["has_short"] = True
            out["source"] = "fallback"
        else:
            out["long"] = total
            out["has_long"] = has_long_open or (total != 0)
            out["source"] = "aggregate"
    return out


async def call_get_unrealized(
    account_mod: Any, symbol: str, return_all: Optional[bool]
) -> Any:
    if not account_mod:
        return None
    fn = getattr(account_mod, "get_unrealized", None)
    if not callable(fn):
        return None
    kwargs = {"symbol": symbol}
    if return_all is not None:
        kwargs["return_all"] = return_all
    try:
        res = fn(**kwargs)
    except TypeError:
        kwargs.pop("return_all", None)
        try:
            res = fn(**kwargs)
        except Exception:
            return None
    except Exception:
        return None
    if inspect.isawaitable(res):
        return await res
    return res


def build_last_trade_payload(
    row: Any, decimal_converter=to_decimal
) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    pnl_dec = decimal_converter(getattr(row, "realized_pnl", 0))
    pnl_abs = float(abs(pnl_dec))
    pnl_sign = "+" if pnl_dec > 0 else ("-" if pnl_dec < 0 else "")
    return {
        "symbol": str(getattr(row, "symbol", "") or "") or None,
        "side": str(getattr(row, "side", "") or "").lower() or None,
        "pnl": float(pnl_dec),
        "pnl_abs": pnl_abs,
        "pnl_sign": pnl_sign,
        "pnl_positive": pnl_dec > 0,
        "pnl_negative": pnl_dec < 0,
        "timestamp": getattr(row, "timestamp", None),
    }
