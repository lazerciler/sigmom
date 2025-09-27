# tests/test_order_params.py

import urllib.parse as _up
from types import SimpleNamespace
from typing import Any, cast, Dict, List, Optional

# noinspection PyPackageRequirements
import pytest

# Test subject
import app.exchanges.binance_futures_testnet.order_handler as oh


def _mk_signal(
    *,
    symbol="BTCUSDT",
    side="long",
    mode="open",
    position_size="0.001",
    order_type="market",
    fund_manager_id=1,
    leverage=5,
    entry_price=None,
    exchange="binance_futures_testnet",
    timestamp=1700000000000,
):
    """WebhookSignal benzeri yalın bir obje (schema import etmeden)."""
    return SimpleNamespace(
        symbol=symbol,
        side=side,
        mode=mode,
        position_size=position_size,
        order_type=order_type,
        fund_manager_id=fund_manager_id,
        leverage=leverage,
        entry_price=entry_price,
        exchange=exchange,
        timestamp=timestamp,
    )


@pytest.fixture(autouse=True)
def _patch_misc(monkeypatch):
    """
    - SafetyGate: hold devre dışı (blocked=False) + ensure() no-op
    - adjust_quantity: sabit dön
    - get_binance_server_time: sabit epoch ms
    """
    # SafetyGate: blocked=False, ensure no-op
    # noinspection PyProtectedMember
    monkeypatch.setattr(oh._GATE, "is_blocked", lambda: (False, ""), raising=True)

    async def _noop():
        return None

    # noinspection PyProtectedMember
    monkeypatch.setattr(oh._GATE, "ensure_position_mode_once", _noop, raising=True)

    # Quantity sabit olsun ki deterministic olsun
    async def _adj(*_a, **_k):
        return "0.001"

    monkeypatch.setattr(oh, "adjust_quantity", _adj, raising=True)

    # İmza/headers patch'ine gerek yok; sadece query parametrelerini kontrol ediyoruz.


class _PostCapture:
    """httpx.AsyncClient.post patch'lenirken çağrı paramlarını yakalar."""

    def __init__(self) -> None:
        self.last_url: Optional[str] = None

    async def post(self, url: str, _headers=None, *_args, **_kwargs):
        self.last_url = url
        # Minimal başarılı yanıt şeklinde dön

        class _Resp:
            status_code = 200

            @staticmethod
            def raise_for_status() -> None:  # noqa: D401
                return None

            @staticmethod
            def json() -> dict:
                return {"ok": True}

        return _Resp()


@pytest.mark.parametrize(
    "position_mode,mode,side,expect_reduce_only,expect_position_side,expect_api_side",
    [
        ("one_way", "open", "long", False, None, "BUY"),
        ("one_way", "close", "long", True, None, "SELL"),
        ("hedge", "open", "short", False, "SHORT", "SELL"),
        ("hedge", "close", "short", False, "SHORT", "BUY"),
    ],
)
@pytest.mark.asyncio
async def test_order_param_rules(
    monkeypatch,
    position_mode,
    mode,
    side,
    expect_reduce_only,
    expect_position_side,
    expect_api_side,
):
    # POSITION_MODE'u test edilen değere çek
    monkeypatch.setattr(oh, "POSITION_MODE", position_mode, raising=True)

    # httpx.AsyncClient.post'u yakala
    cap = _PostCapture()

    class _Client:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def __aenter__(self) -> _PostCapture:
            return cap

        async def __aexit__(self, *_exc) -> bool:
            return False

    monkeypatch.setattr(oh.httpx, "AsyncClient", _Client, raising=True)

    # Sinyal hazırla ve çağır
    sig = _mk_signal(mode=mode, side=side)
    # Testte SimpleNamespace kullandığımız için tip uyarısını bastır.
    res = await oh.place_order(cast(Any, sig))  # type: ignore[arg-type]
    assert res.get("success") is True

    # URL'i çöz ve query paramlarını al
    # Beklenen format: f"{url}?{query}&signature=deadbeef"
    assert cap.last_url is not None
    parsed = _up.urlparse(cap.last_url)
    qs = cast(Dict[str, List[str]], _up.parse_qs(parsed.query))

    # side/api_side kontrol (BUY/SELL)
    assert qs.get("side", [""])[0] == expect_api_side

    # reduceOnly kontrol
    if expect_reduce_only:
        # reduceOnly=true olmalı
        assert qs.get("reduceOnly", [""])[0] == "true"
    else:
        # hiç olmamalı
        assert "reduceOnly" not in qs

    # positionSide kontrol
    if expect_position_side is None:
        assert "positionSide" not in qs
    else:
        assert qs.get("positionSide", [""])[0] == expect_position_side
