# tests/test_entry_lines_helpers.py
# Python 3.9

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from app.services.entry_lines_helpers import calculate_entry_lines


def _row(symbol: str, side: str, price: float, *, dt: datetime) -> SimpleNamespace:
    return SimpleNamespace(symbol=symbol, side=side, entry_price=price, timestamp=dt)


def test_calculate_entry_lines_strips_symbol_whitespace():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = [
        _row("BTCUSDT", "long", 101.5, dt=base),
        _row("BTCUSDT", "short", 99.2, dt=base + timedelta(minutes=1)),
        _row("ETHUSDT", "long", 1500.0, dt=base),
    ]

    result = calculate_entry_lines(rows, symbol="  BTCUSDT  ")

    assert result["long"] == 101.5
    assert result["short"] == 99.2


def test_calculate_entry_lines_returns_null_keys_when_no_match():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = [
        _row("BTCUSDT", "long", 100.0, dt=base),
        _row("BTCUSDT", "short", 99.0, dt=base + timedelta(minutes=1)),
    ]
    result = calculate_entry_lines(rows, symbol="XRPUSDT")
    assert "long" in result and "short" in result
    assert result["long"] is None
    assert result["short"] is None


def test_calculate_entry_lines_handles_missing_side_as_null():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = [
        _row("ETHUSDT", "long", 1500.25, dt=base),
        _row("ETHUSDT", "long", 1501.00, dt=base + timedelta(minutes=1)),
    ]
    result = calculate_entry_lines(rows, symbol="ETHUSDT")
    assert result["long"] == 1501.00  # en güncel long
    assert result["short"] is None  # short yok → null


def test_calculate_entry_lines_uses_alternative_price_fields_and_latest():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    # avg_entry_price ve entry_avg gibi alternatif alanları simüle etmek için SimpleNamespace ile ek alanlar
    rows = [
        SimpleNamespace(
            symbol="BTCUSDT", side="long", avg_entry_price="100.5", timestamp=base
        ),
        SimpleNamespace(
            symbol="BTCUSDT",
            side="short",
            entry_avg=99.9,
            timestamp=base + timedelta(minutes=1),
        ),
        SimpleNamespace(
            symbol="BTCUSDT",
            side="long",
            entry_price=100.9,
            timestamp=base + timedelta(minutes=2),
        ),
    ]
    result = calculate_entry_lines(rows, symbol="BTCUSDT")
    # son long 100.9, short 99.9
    assert result["long"] == 100.9
    assert result["short"] == 99.9


# from datetime import datetime, timedelta, timezone
# from decimal import Decimal
# from types import SimpleNamespace
#
# # noinspection PyPackageRequirements
# import pytest
#
# from app.services.entry_lines_helpers import calculate_entry_lines
#
#
# def _row(**kwargs):
#     defaults = {
#         "symbol": "BTCUSDT",
#         "side": "long",
#         "entry_price": Decimal("0"),
#         "timestamp": datetime.now(timezone.utc),
#         "response_data": {},
#     }
#     defaults.update(kwargs)
#     return SimpleNamespace(**defaults)
#
#
# def test_calculate_entry_lines_uses_latest_per_side_and_epsilon():
#     base = datetime(2023, 1, 1, tzinfo=timezone.utc)
#     rows = [
#         _row(symbol="BTCUSDT", side="long", entry_price=Decimal("100"), timestamp=base),
#         _row(symbol="BTCUSDT", side="short", entry_price=Decimal("100"), timestamp=base + timedelta(minutes=1)),
#         _row(symbol="BTCUSDT", side="long", entry_price=Decimal("99"), timestamp=base - timedelta(minutes=5)),
#     ]
#
#     lines = calculate_entry_lines(rows, symbol="BTCUSDT")
#     assert lines["short"] == pytest.approx(100.0)
#     assert lines["long"] == pytest.approx(100.5)
#
#
# def test_calculate_entry_lines_prefers_response_payload_when_entry_missing():
#     base = datetime(2023, 1, 1, tzinfo=timezone.utc)
#     rows = [
#         _row(
#             symbol="ETHUSDT",
#             side="long",
#             entry_price=None,
#             timestamp=base + timedelta(minutes=10),
#             response_data={"avg_entry_price": "201.25"},
#         ),
#         _row(
#             symbol="ETHUSDT",
#             side="long",
#             entry_price=Decimal("199.4"),
#             timestamp=base,
#         ),
#         _row(
#             symbol="ETHUSDT",
#             side="short",
#             entry_price=Decimal("205"),
#             timestamp=base + timedelta(minutes=5),
#         ),
#     ]
#
#     lines = calculate_entry_lines(rows, symbol="ethusdt")
#     assert lines["long"] == pytest.approx(201.25)
#     assert lines["short"] == pytest.approx(205.0)
#
#
# def test_calculate_entry_lines_returns_none_when_no_matches():
#     rows = [_row(symbol="BTCUSDT", side="long", entry_price=Decimal("100"))]
#
#     lines = calculate_entry_lines(rows, symbol="XRPUSDT")
#     assert lines["long"] is None
#     assert lines["short"] is None
