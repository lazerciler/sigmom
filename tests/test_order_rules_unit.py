# tests/test_order_rules_unit.py
# Python 3.9

import app.exchanges.binance_futures_testnet.order_handler as oh

# noinspection PyPackageRequirements
import pytest


@pytest.mark.parametrize(
    "position_mode,mode,side,expect_reduce_only,expect_position_side,expect_api_side",
    [
        ("one_way", "open", "long", False, None, "BUY"),
        ("one_way", "close", "long", True, None, "SELL"),
        ("hedge", "open", "short", False, "SHORT", "SELL"),
        ("hedge", "close", "short", False, "SHORT", "BUY"),
        # case-insensitive varyasyonlar
        ("HEDGE", "Open", "Long", False, "LONG", "BUY"),
        ("ONE_WAY", "CLOSE", "SHORT", True, None, "BUY"),
    ],
)
def test_build_param_rules(
    position_mode, mode, side, expect_reduce_only, expect_position_side, expect_api_side
):
    ro, ps, api = oh._build_param_rules(position_mode, mode, side)
    assert ro == expect_reduce_only
    assert ps == expect_position_side
    assert api == expect_api_side
