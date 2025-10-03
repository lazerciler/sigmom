# tests/test_quick_balance_helpers.py
# Python 3.9

import types
from decimal import Decimal
from datetime import datetime, timezone

# noinspection PyPackageRequirements
import pytest

from app.services.quick_balance_helpers import (
    extract_unrealized_breakdown,
    build_last_trade_payload,
    to_decimal,
)


def _open(symbol: str, side: str):
    return types.SimpleNamespace(symbol=symbol, side=side)


def test_extract_unrealized_prefers_legs_breakdown():
    rows = [_open("BTCUSDT", "long"), _open("BTCUSDT", "short")]
    payload = {
        "legs": {"long": "3.5", "short": "-1.25"},
        "mode": "hedge",
        "unrealized": "2.0",
    }
    out = extract_unrealized_breakdown(
        payload, "BTCUSDT", rows, decimal_converter=to_decimal
    )
    assert out["source"] == "legs"
    assert out["mode"] == "hedge"
    assert out["has_long"] is True and out["has_short"] is True
    assert out["long"] == Decimal("3.5")
    assert out["short"] == Decimal("-1.25")


def test_extract_unrealized_handles_position_list():
    payload = [
        {"symbol": "BTCUSDT", "side": "short", "unrealizedPnl": "-7.0"},
        {"symbol": "BTCUSDT", "qty": "2", "entryPrice": "100", "markPrice": "105"},
    ]
    out = extract_unrealized_breakdown(
        payload, "BTCUSDT", [], decimal_converter=to_decimal
    )
    assert out["source"] == "positions"
    assert out["has_short"] is True and out["has_long"] is True
    assert out["short"] == Decimal("-7.0")
    assert out["long"] == Decimal("10")


def test_extract_unrealized_allocates_aggregate_to_open_side():
    rows = [_open("BTCUSDT", "long")]
    payload = {"unrealized": "12"}
    out = extract_unrealized_breakdown(
        payload, "BTCUSDT", rows, decimal_converter=to_decimal
    )
    assert out["source"] == "fallback"
    assert out["has_long"] is True and out["has_short"] is False
    assert out["long"] == Decimal("12")
    assert out["short"] == Decimal("0")


def test_build_last_trade_view_populates_flags():
    ts = datetime(2024, 5, 4, 12, 0, tzinfo=timezone.utc)
    row = types.SimpleNamespace(
        symbol="ETHUSDT", side="long", realized_pnl="4.2", timestamp=ts
    )
    payload = build_last_trade_payload(row, decimal_converter=to_decimal)
    assert payload is not None
    assert payload["symbol"] == "ETHUSDT"
    assert payload["side"] == "long"
    assert pytest.approx(payload["pnl"]) == 4.2
    assert payload["pnl_sign"] == "+"
    assert payload["pnl_positive"] is True and payload["pnl_negative"] is False
    assert payload["timestamp"] == ts


def test_build_last_trade_view_returns_none_when_missing():
    assert build_last_trade_payload(None) is None
