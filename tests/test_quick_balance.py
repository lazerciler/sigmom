# tests/test_quick_balance.py
# Python 3.9

import os
import sys
import types

# noinspection PyPackageRequirements
import pytest

from decimal import Decimal
from sqlalchemy.orm import declarative_base
from app.routers import panel_data

os.environ.setdefault("DB_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ACTIVE_EXCHANGES", "binance")
os.environ.setdefault("DEFAULT_EXCHANGE", "binance")
os.environ.setdefault("GOOGLE_CLIENT_ID", "dummy")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "dummy")
os.environ.setdefault("SESSION_SECRET", "dummy")

db_mod = types.ModuleType("app.database")
db_mod.Base = declarative_base()


async def _fake_get_db():
    yield None


db_mod.get_db = _fake_get_db
sys.modules.setdefault("app.database", db_mod)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self._rows)


@pytest.mark.asyncio
async def test_me_quick_balance_falls_back_to_db(monkeypatch):
    rows = [
        ("long", Decimal("12.5")),
        ("short", Decimal("-3.5")),
    ]

    async def fake_call_get_unrealized(*_, **__):
        return None

    monkeypatch.setattr(panel_data, "call_get_unrealized", fake_call_get_unrealized)

    session = _FakeSession(rows)

    result = await panel_data.me_quick_balance(
        symbol="BTCUSDT",
        exchange="binance",
        db=session,
    )

    breakdown = result["breakdown"]
    assert result["used_fallback"] is True
    assert pytest.approx(breakdown["long"], rel=1e-6) == 12.5
    assert pytest.approx(breakdown["short"], rel=1e-6) == -3.5
    assert pytest.approx(breakdown["total"], rel=1e-6) == 9.0
    assert breakdown["source"] == "db"
    assert breakdown["has_long"] is True
    assert breakdown["has_short"] is True
    assert "exchange_payload" not in result or result["exchange_payload"] is None
