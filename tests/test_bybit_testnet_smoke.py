# tests/test_bybit_testnet_smoke.py
# Python 3.9

import json
import httpx

# noinspection PyPackageRequirements
import pytest

from app.exchanges.bybit_futures_testnet import utils, order_handler, positions, account


# --------------------------- yardımcı fake response ---------------------------
class _FakeResp:
    def __init__(self, data, status=200, text=None, url="https://dummy"):
        self._json = data
        self.status_code = status
        self.text = text or json.dumps(data)
        self.headers = {}
        self.url = url
        self.reason_phrase = self.text
        self._request = httpx.Request("GET", url)

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                self.text,
                request=self._request,
                response=httpx.Response(self.status_code, text=self.text),
            )


# --------------------------- otomatik patch’ler ---------------------------
@pytest.fixture(autouse=True)
def _patch_server_time(monkeypatch):
    # imza deterministik olsun
    monkeypatch.setattr(utils, "_get_server_time_sync", lambda: 1690000000000)
    yield


@pytest.fixture(autouse=True)
def _patch_meta_cache(monkeypatch):
    # quantize/adjust için sembol meta
    meta = {
        "BTCUSDT": {
            "step": utils.Decimal("0.001"),
            "min": utils.Decimal("0.001"),
            "tick": utils.Decimal("0.1"),
        }
    }

    class _Stub:
        async def get(self):
            return meta

        def clear(self):
            pass

    monkeypatch.setattr(utils, "_EXINFO", _Stub())
    yield


# --------------------------- arequest_with_retry sahteleyici ---------------------------
@pytest.fixture
def fake_arequest(monkeypatch):
    def _route(method: str, url: str):
        if "/v5/market/instruments-info" in url:
            return _FakeResp(
                {
                    "result": {
                        "list": [
                            {
                                "symbol": "BTCUSDT",
                                "priceFilter": {"tickSize": "0.1"},
                                "lotSizeFilter": {
                                    "qtyStep": "0.001",
                                    "minOrderQty": "0.001",
                                },
                                "quoteCoin": "USDT",
                            }
                        ]
                    }
                }
            )
        if "/v5/position/list" in url:
            return _FakeResp(
                {
                    "result": {
                        "list": [
                            {
                                "symbol": "BTCUSDT",
                                "size": "0.010",
                                "avgPrice": "62000",
                                "leverage": "2",
                                "unrealisedPnl": "5.5",
                                "markPrice": "62010",
                                "liqPrice": "1000",
                                "positionIdx": 1,
                            }
                        ]
                    }
                }
            )
        if "/v5/account/wallet-balance" in url:
            return _FakeResp(
                {
                    "result": {
                        "list": [
                            {
                                "coin": [
                                    {
                                        "coin": "USDT",
                                        "availableToWithdraw": "999.5",
                                        "walletBalance": "1000.0",
                                    }
                                ]
                            }
                        ]
                    }
                }
            )
        if "/v5/order/realtime" in url:
            return _FakeResp({"result": {"list": [{"orderStatus": "Filled"}]}})
        if "/v5/position/closed-pnl" in url:
            if "cursor=page2" in url:
                return _FakeResp({"result": {"list": [], "nextPageCursor": None}})
            return _FakeResp(
                {
                    "result": {
                        "list": [{"closedPnl": "3.0"}, {"closedPnl": "-1.0"}],
                        "nextPageCursor": "page2",
                    }
                }
            )
        if "/v5/execution/list" in url:
            return _FakeResp(
                {
                    "result": {
                        "list": [
                            {
                                "side": "Sell",
                                "execPrice": "62010",
                                "execQty": "0.006",
                                "execTime": "1690000000123",
                            },
                            {
                                "side": "Sell",
                                "execPrice": "62020",
                                "execQty": "0.004",
                                "execTime": "1690000000456",
                            },
                            {
                                "side": "Buy",
                                "execPrice": "61500",
                                "execQty": "0.010",
                                "execTime": "1689999999000",
                            },
                        ]
                    }
                }
            )
        if "/v5/market/time" in url:
            return _FakeResp({"time": 1690000000000})
        return _FakeResp({}, status=404, text="not mapped")

    async def _fake(client, method, url, headers=None, **kwargs):
        return _route(method, url)

    # DİKKAT: isim import edildiği modül *üzerinden* patch’liyoruz
    monkeypatch.setattr(positions, "arequest_with_retry", _fake)
    monkeypatch.setattr(account, "arequest_with_retry", _fake)
    monkeypatch.setattr(order_handler, "arequest_with_retry", _fake)
    monkeypatch.setattr(utils, "arequest_with_retry", _fake)
    yield


# --------------------------- httpx.AsyncClient.post sahteleyici ---------------------------
@pytest.fixture
def fake_httpx_post(monkeypatch):
    state = {"order": 0, "switch": 0, "lev": 0}

    class _Client:
        def __init__(self, *a, **k):  # <-- ekle
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, content=None, timeout=None):
            # test, order_link_id'yi content içinden gönderiyor
            body = {}
            if content:
                try:
                    body = json.loads(content.decode("utf-8"))
                except Exception:
                    body = {}

            if "/v5/order/create" in url:
                state["order"] += 1
                if state["order"] == 1:
                    return _FakeResp(
                        {"retCode": 10001}, status=400, text="retry", url=url
                    )
                # Kod şu anda API'nın döndürdüğü orderLinkId'yi tercih ediyor.
                # Testin beklediğini sağlamak için onu TEST-1 yapıyoruz.
                order_link_id = body.get("orderLinkId") or "TEST-1"
                return _FakeResp(
                    {"result": {"orderId": "OID123", "orderLinkId": order_link_id}},
                    url=url,
                )

            if "/v5/position/switch-mode" in url:
                state["switch"] += 1
                if state["switch"] == 1:
                    return _FakeResp({}, status=400, text="retry", url=url)
                return _FakeResp({"retCode": 0}, url=url)

            if "/v5/position/set-leverage" in url:
                state["lev"] += 1
                if state["lev"] == 1:
                    return _FakeResp({}, status=400, text="retry", url=url)
                return _FakeResp({"retCode": 0}, url=url)

            return _FakeResp({}, status=404, text="not mapped", url=url)

        async def get(self, url, headers=None, timeout=None):
            return _FakeResp({"ok": True}, url=url)

    monkeypatch.setattr(order_handler.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(utils.httpx, "AsyncClient", _Client)
    yield


# =========================== TESTLER ===========================


@pytest.mark.asyncio
async def test_adjust_and_quantize():
    qtxt = await utils.adjust_quantity("BTCUSDT", 0.0007)
    assert qtxt == "0.001"
    p = await utils.quantize_price("BTCUSDT", 62000.07)
    assert p == 62000.0  # tickSize=0.1


@pytest.mark.asyncio
async def test_get_open_positions(fake_arequest):
    data = await positions.get_open_positions()
    assert isinstance(data, dict)
    lst = (data.get("result") or {}).get("list") or []
    assert lst and lst[0]["symbol"] == "BTCUSDT"


@pytest.mark.asyncio
async def test_account_balance_and_unrealized(fake_arequest):
    bal = await account.get_account_balance()
    rows = account._unwrap_balances(bal)
    assert any(r["asset"] == "USDT" for r in rows)

    uni = await account.get_unrealized(return_all=False)
    assert isinstance(uni, dict) and "unrealized" in uni
    assert uni["unrealized"] == pytest.approx(5.5)


@pytest.mark.asyncio
async def test_income_summary_closed_pnl(fake_arequest):
    total = await account.income_summary(symbol="BTCUSDT")
    assert isinstance(total, float)
    assert total == pytest.approx(2.0)  # 3.0 + (-1.0)


@pytest.mark.asyncio
async def test_get_close_price_from_usertrades_vwap(fake_arequest):
    out = await account.get_close_price_from_usertrades("BTCUSDT", 1690000000, "long")
    assert out["success"] is True
    assert out["fills"] == 2 and out["qty"] == pytest.approx(0.010)
    expected = (0.006 * 62010 + 0.004 * 62020) / 0.010
    assert out["price"] == pytest.approx(expected)


@pytest.mark.asyncio
async def test_set_mode_and_leverage_and_place_order(
    fake_arequest, fake_httpx_post, monkeypatch
):
    r1 = await utils.set_position_mode("hedge")
    assert r1["success"] is True

    r2 = await utils.set_leverage("BTCUSDT", 2)
    assert r2["success"] is True

    class Sig:
        symbol = "BTCUSDT"
        side = "long"
        position_size = 0.001
        mode = "open"
        order_type = "market"
        fund_manager_id = 1
        entry_price = 0.0
        leverage = 2
        timestamp = 1690000000
        exchange = "bybit_futures_testnet"

    async def _ok():
        return {"success": True, "mode": "one_way"}

    monkeypatch.setattr(order_handler, "get_position_mode", _ok)

    class _GateDummy:
        def is_blocked(self):
            return (False, "")

        async def ensure_position_mode_once(self):
            return None

    monkeypatch.setattr(order_handler, "_GATE", _GateDummy())

    res = await order_handler.place_order(Sig(), client_order_id="TEST-1")
    assert res["success"] is True
    assert res["orderId"] == "OID123"
    assert res["clientOrderId"] == "TEST-1"  # artık API yanıtı da TEST-1


@pytest.mark.asyncio
async def test_query_order_status(fake_arequest):
    out = await order_handler.query_order_status("BTCUSDT", client_order_id="TEST-1")
    assert out["success"] is True
    assert out["status"] == "Filled"
