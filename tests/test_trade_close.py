# tests/test_trade_close.py
# Python 3.9

import sys
import types
import asyncio
import logging
from types import SimpleNamespace
from decimal import Decimal

# noinspection PyPackageRequirements
import pytest
from unittest.mock import AsyncMock, MagicMock


# -- Stub minimal app.database and app.models for crud.trade import --
class _DummySession:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        pass


def _async_session():
    return _DummySession()


async def _get_db():
    yield None


db_mod = types.ModuleType("app.database")
db_mod.async_session = _async_session
db_mod.get_db = _get_db
db_mod.Base = object()
sys.modules.setdefault("app.database", db_mod)


class StrategyOpenTrade(SimpleNamespace):
    id = 0


class StrategyTrade(SimpleNamespace):
    pass


models_mod = types.ModuleType("app.models")
models_mod.StrategyOpenTrade = StrategyOpenTrade
models_mod.StrategyTrade = StrategyTrade
sys.modules.setdefault("app.models", models_mod)

from crud import trade as trade_module  # noqa: E402

# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patch_trade_sql(monkeypatch):
    """Patch SQLAlchemy helpers used inside close_open_trade_and_record."""

    class DummySelect:
        def where(self, *args, **kwargs):
            return self

        def with_for_update(self):
            return self

    class DummyColumn:
        def __init__(self, name):
            self.name = name

        # SQLAlchemy boolean expression benzeri davranışlar için operatörler
        def __eq__(self, other):
            return self

        def __ne__(self, other):
            return self

        def in_(self, iterable):
            return self

        def is_(self, other):
            return self

    class DummyUpdate:
        def where(self, *args, **kwargs):
            return self

        def values(self, *args, **kwargs):
            return self

    monkeypatch.setattr(trade_module, "select", lambda *a, **k: DummySelect())
    # SQLAlchemy and_(...) yerine no-op bir stub kullan
    monkeypatch.setattr(trade_module, "and_", lambda *a, **k: object())
    monkeypatch.setattr(trade_module, "text", lambda *a, **k: None)
    # close_open_trade_and_record içinde çağrılan sqlalchemy.update(...)’i de stub’la
    monkeypatch.setattr(trade_module, "update", lambda *a, **k: DummyUpdate())
    # Model sütunlarını da stub’la (filter'da erişiliyor)
    setattr(trade_module.StrategyOpenTrade, "status", DummyColumn("status"))
    setattr(trade_module.StrategyOpenTrade, "id", DummyColumn("id"))
    setattr(trade_module.StrategyOpenTrade, "public_id", DummyColumn("public_id"))
    return trade_module


class FakeResult:
    def __init__(self, trade):
        self._trade = trade
        self.rowcount = 1  # update(...) başarılı kabul edilsin

    def scalar_one(self):
        return self._trade

    def fetchone(self):
        return SimpleNamespace(
            id=1, symbol=self._trade.symbol, realized_pnl=Decimal("20")
        )


class FakeSession:
    def __init__(self, trade):
        self.add = MagicMock()
        self.flush = AsyncMock()
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self._result = FakeResult(trade)

    async def execute(self, *args, **kwargs):
        return self._result


# ---------------------------------------------------------------------------
# verify_close_after_signal commit test
# ---------------------------------------------------------------------------


# import pytest


@pytest.mark.asyncio
async def test_verify_close_after_signal_commits(monkeypatch):
    trade = StrategyOpenTrade(
        id=1,
        public_id="abc",
        status="open",
        symbol="BTCUSDT",
    )
    session = FakeSession(trade)

    # Patch select().scalar_one() to simulate "already closed trade exists"
    class DummyResult:
        def scalar_one(self):
            return 1

    async def fake_execute(*a, **k):
        return DummyResult()

    session.execute = fake_execute

    import crud.trade as trade_mod

    # DB'den open trade seçimi bu testin konusu değil: doğrudan trade döndür.
    async def fake_get_open_trade_for_close(
        db, public_id, symbol, exchange, fund_manager_id=None, side=None
    ):
        return trade

    monkeypatch.setattr(
        trade_mod, "get_open_trade_for_close", fake_get_open_trade_for_close
    )

    # .where(StrategyTrade.open_trade_public_id == ...) ifadesi için sütunu stub'la
    class _DummyCol:
        def __eq__(self, other):
            return self

    setattr(trade_mod.StrategyTrade, "open_trade_public_id", _DummyCol())

    # verify_close_after_signal içinde kullanılan select(func.count()).select_from(...)
    # zincirini kırmamak için no-op bir DummySelect verelim.
    class DummySelect:
        def where(self, *a, **k):
            return self

        def select_from(self, *a, **k):
            return self

    monkeypatch.setattr(trade_mod, "select", lambda *a, **k: DummySelect())

    result = await trade_mod.verify_close_after_signal(
        session,
        trade,
        public_id=trade.public_id,
        symbol=trade.symbol,
        exchange="binance",
    )

    assert result is True
    assert trade.status == "closed"
    session.flush.assert_awaited()
    session.commit.assert_awaited()


# ---------------------------------------------------------------------------
# close_open_trade_and_record tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_open_trade_success(patch_trade_sql, caplog):
    trade = StrategyOpenTrade(
        id=1,
        public_id="abc",
        raw_signal_id=1,
        symbol="BTCUSDT",
        side="long",
        entry_price="100",
        position_size="2",
        leverage=1,
        order_type="market",
        exchange="binance",
        fund_manager_id="fm",
        status="open",
        response_data={},
    )
    session = FakeSession(trade)
    position_data = {"avgClosePrice": "110"}
    caplog.set_level(logging.INFO, logger="verifier")
    ok = await trade_module.close_open_trade_and_record(session, trade, position_data)
    session.add.assert_called_once()
    session.commit.assert_awaited_once()
    session.rollback.assert_not_called()
    assert ok is True
    assert "[closed-recorded]" in caplog.text


@pytest.mark.asyncio
async def test_close_open_trade_error_rolls_back(patch_trade_sql, caplog):
    trade = StrategyOpenTrade(
        id=1,
        public_id="abc",
        raw_signal_id=1,
        symbol="BTCUSDT",
        side="long",
        entry_price="0",  # invalid
        position_size="2",
        leverage=1,
        order_type="market",
        exchange="binance",
        fund_manager_id="fm",
        status="open",
        response_data={},
    )
    session = FakeSession(trade)
    position_data = {"avgClosePrice": "110"}
    caplog.set_level(logging.ERROR, logger="verifier")
    ok = await trade_module.close_open_trade_and_record(session, trade, position_data)
    session.rollback.assert_awaited_once()
    session.commit.assert_not_called()
    assert trade.status == "open"
    assert ok is False
    assert "[close-fail]" in caplog.text


# ---------------------------------------------------------------------------
# Utilities for importing app.main with heavy dependencies stubbed
# ---------------------------------------------------------------------------

_cached_main = None


def _prepare_main(monkeypatch):
    global _cached_main
    if _cached_main is not None:
        return _cached_main

    env = {
        "DB_URL": "sqlite+aiosqlite://",
        "ACTIVE_EXCHANGES": "binance",
        "DEFAULT_EXCHANGE": "binance",
        "GOOGLE_CLIENT_ID": "x",
        "GOOGLE_CLIENT_SECRET": "x",
        "SESSION_SECRET": "x",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    from fastapi import APIRouter

    router_names = [
        "webhook_router",
        "panel",
        "panel_data",
        "referral",
        "auth_google",
        "admin_settings",
        "admin_referrals",
        "admin_test",
        "auth_logout",
        "market",
    ]
    for name in router_names:
        mod = types.ModuleType(f"app.routers.{name}")
        mod.router = APIRouter()
        sys.modules[f"app.routers.{name}"] = mod

    # Gerçek auth.py yerine hafif bir stub enjekte et (User/DB bağımlılığı yok)
    auth_stub = types.ModuleType("app.dependencies.auth")

    def _get_current_user(*args, **kwargs):
        return None

    auth_stub.get_current_user = _get_current_user
    sys.modules["app.dependencies.auth"] = auth_stub

    # Emniyet için app.models.User da mevcut olsun
    _models = sys.modules.get("app.models")
    if _models is None:
        _models = types.ModuleType("app.models")
        sys.modules["app.models"] = _models
    if not hasattr(_models, "User"):

        class _User(SimpleNamespace):
            id: int = 0
            email: str = "stub@example.com"

        _models.User = _User

    handler_mod = types.ModuleType("app.handlers.order_verification_handler")

    async def _vc(db, execution):
        pass

    handler_mod.verify_closed_trades_for_execution = _vc
    sys.modules["app.handlers.order_verification_handler"] = handler_mod

    service_mod = types.ModuleType("app.services.referral_maintenance")

    async def _cleanup(session):
        return 0

    service_mod.cleanup_expired_reserved = _cleanup
    sys.modules["app.services.referral_maintenance"] = service_mod

    sys.modules["crud.trade"] = trade_module

    import importlib

    _cached_main = importlib.import_module("app.main")
    return _cached_main


# ---------------------------------------------------------------------------
# verifier_iteration & verifier_loop tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verifier_iteration_logs_error(monkeypatch, caplog):
    main = _prepare_main(monkeypatch)

    async def boom(db, execution):
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "verify_pending_trades_for_execution", boom)
    monkeypatch.setattr(main, "verify_closed_trades_for_execution", AsyncMock())
    monkeypatch.setattr(main, "load_execution_module", lambda name: object())
    error_mock = MagicMock()
    monkeypatch.setattr(main.verifier_logger, "error", error_mock)
    await main.verifier_iteration("db", "dummy")
    error_mock.assert_called_once()


@pytest.mark.asyncio
async def test_verifier_loop_can_be_cancelled(monkeypatch):
    main = _prepare_main(monkeypatch)

    calls = []
    event = asyncio.Event()

    async def fake_iter(db, ex):
        calls.append(ex)
        event.set()
        await asyncio.sleep(0)

    monkeypatch.setattr(main, "verifier_iteration", fake_iter)
    monkeypatch.setattr(main.settings, "ACTIVE_EXCHANGES", "ex1,ex2")

    class CM:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            pass

    monkeypatch.setattr(main, "async_session", lambda: CM())
    monkeypatch.setattr(main, "cleanup_expired_reserved", AsyncMock(return_value=0))

    import asyncio as _asyncio

    original_sleep = _asyncio.sleep

    async def fast_sleep(_):
        await original_sleep(0)

    monkeypatch.setattr(main.asyncio, "sleep", fast_sleep)

    task = asyncio.create_task(
        main.verifier_loop(poll_interval=0, cleanup_interval_sec=3600)
    )
    await event.wait()
    task.cancel()
    # Döngü cancel'ı içeride yakalanıp temiz sonlandırılıyor; exception beklemiyoruz.
    await task
    assert task.done()
    assert calls  # at least one iteration executed
