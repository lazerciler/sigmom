# tests/test_bybit_server_time.py
# Python 3.9

import contextlib
import os

# noinspection PyPackageRequirements
import pytest

os.environ.setdefault("DB_URL", "sqlite:///test.db")
os.environ.setdefault("ACTIVE_EXCHANGES", "BYBIT_FUTURES_TESTNET")
os.environ.setdefault("DEFAULT_EXCHANGE", "BYBIT_FUTURES_TESTNET")
os.environ.setdefault("GOOGLE_CLIENT_ID", "dummy")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "dummy")
os.environ.setdefault("SESSION_SECRET", "dummysecret")

from app.exchanges.bybit_futures_testnet import utils


class _DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


@contextlib.contextmanager
def _client_with_payload(payload):
    class _DummyClient:
        def get(self, url):
            return _DummyResponse(payload)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    yield _DummyClient()


@pytest.mark.parametrize(
    "payload, expected",
    [
        ({"time": "1690000000123"}, 1690000000123),
        (
            {"result": {"timeNano": "1690000000123456789"}},
            1690000000123,
        ),
        (
            {"result": {"timeSecond": "1690000000"}},
            1690000000000,
        ),
    ],
)
def test_get_server_time_prefers_time_and_converts(monkeypatch, payload, expected):
    def _fake_client(*args, **kwargs):
        return _client_with_payload(payload)

    monkeypatch.setattr(utils.httpx, "Client", _fake_client)

    assert utils._get_server_time_sync() == expected


def test_get_server_time_falls_back_to_local(monkeypatch):
    sentinel = 1234.5

    def _fake_client(*args, **kwargs):
        return _client_with_payload({})

    monkeypatch.setattr(utils.httpx, "Client", _fake_client)
    monkeypatch.setattr(utils, "_time", lambda: sentinel)

    assert utils._get_server_time_sync() == int(sentinel * 1000)
