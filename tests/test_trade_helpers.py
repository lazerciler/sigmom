# tests/test_trade_helpers.py
# Python 3.9

# noinspection PyPackageRequirements
import pytest
from decimal import Decimal
from crud.trade import pick_close_price, compute_pnl


class TestPickClosePrice:
    def test_prefers_avgclose(self):
        data = {"avgClosePrice": "101.5", "markPrice": "99.9"}
        assert pick_close_price(data) == Decimal("101.5")

    def test_falls_back_to_avgprice_then_price(self):
        assert pick_close_price({"avgPrice": "100.1"}) == Decimal("100.1")
        assert pick_close_price({"price": "100"}) == Decimal("100")

    def test_uses_last_close_mark_as_late_fallbacks(self):
        assert pick_close_price({"lastPrice": "99.8"}) == Decimal("99.8")
        assert pick_close_price({"closePrice": "99.7"}) == Decimal("99.7")
        assert pick_close_price({"markPrice": "99.6"}) == Decimal("99.6")

    @pytest.mark.parametrize("bad", [None, "", "0", 0, "0.0"])
    def test_rejects_none_or_non_positive(self, bad):
        with pytest.raises(ValueError):
            pick_close_price({"avgPrice": bad})


class TestComputePnL:
    def test_long_pnl(self):
        pnl = compute_pnl("long", Decimal("100"), Decimal("110"), Decimal("2"))
        assert pnl == Decimal("20")

    def test_short_pnl(self):
        pnl = compute_pnl("short", Decimal("100"), Decimal("90"), Decimal("3"))
        assert pnl == Decimal("30")

    def test_invalid_side(self):
        with pytest.raises(ValueError):
            compute_pnl("weird", Decimal("1"), Decimal("2"), Decimal("1"))
