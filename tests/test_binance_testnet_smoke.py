# tests/test_binance_testnet_smoke.py
# Python 3.9

import os
import time
import httpx

# noinspection PyPackageRequirements
import pytest

from app.exchanges.binance_futures_testnet.positions import get_open_positions
from app.exchanges.binance_futures_testnet.utils import (
    build_signed_get,
    get_position_mode,
    set_position_mode,
    set_leverage,
)
from app.exchanges.binance_futures_testnet.settings import (
    BASE_URL,
    ENDPOINTS,
    HTTP_TIMEOUT_SHORT,
    HTTP_TIMEOUT_LONG,
)

pytestmark = pytest.mark.asyncio


async def test_time_endpoint():
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SHORT) as c:
        r = await c.get(f"{BASE_URL}{ENDPOINTS['TIME']}")
        r.raise_for_status()
        server_ms = int(r.json()["serverTime"])
        now_ms = int(time.time() * 1000)
        assert abs(server_ms - now_ms) < 120_000


async def test_exchange_info():
    full_url, headers = await build_signed_get(
        f"{BASE_URL}{ENDPOINTS['EXCHANGE_INFO']}", {}
    )
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_LONG) as c:
        r = await c.get(full_url, headers=headers)
        r.raise_for_status()
        j = r.json()
        assert "symbols" in j


async def test_position_mode_roundtrip():
    # first = await get_position_mode(); assert first["success"]
    # Binance kuralı: açık pozisyon varken position mode değişmez (-4068).
    # Açık pozisyon varsa bu testi atla (skip).
    try:
        pos = await get_open_positions()
    except (httpx.HTTPError, ValueError, TypeError):
        pos = []
    has_open = False
    for p in pos or []:
        try:
            amt = float(p.get("positionAmt", "0") or 0)
        except (ValueError, TypeError):
            amt = 0.0
        if abs(amt) > 0:
            has_open = True
            break
    if has_open:
        pytest.skip("Open positions exist; position mode cannot be changed (-4068).")

    first = await get_position_mode()
    assert first["success"]
    cur = first["mode"]
    flip = "one_way" if cur == "hedge" else "hedge"
    ok = await set_position_mode(flip)
    if not ok.get("success"):
        # Güvence: Borsa yine -4068 verdiyse testi atla
        if "cannot be changed" in (ok.get("message") or ""):
            pytest.skip("Position mode change blocked by exchange (-4068).")
            assert False, f"set_position_mode failed: {ok}"
        chk = await get_position_mode()
        assert chk["mode"] == flip
        _ = await set_position_mode(cur)
        final = await get_position_mode()
        assert final["mode"] == cur


async def test_set_leverage_smoke():
    sym = os.getenv("SMOKE_SYMBOL", "BTCUSDT")
    res = await set_leverage(sym, 7)
    assert res["success"]
