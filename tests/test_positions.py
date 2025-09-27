# tests/test_positions.py
# noinspection PyPackageRequirements
import pytest

# Projenizdeki gerçek yola göre bu import'u ayarlayın:
# Örn: from app.exchanges.binance_futures_testnet import positions
import importlib

positions = importlib.import_module("app.exchanges.binance_futures_testnet.positions")


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        # Hata fırlatmak istemiyorsak boş geçiyoruz
        if not (200 <= self.status_code < 300):
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.mark.asyncio
async def test_get_open_positions_calls_rebuild_async_on_retry(monkeypatch):
    """
    Senaryo: arequest_with_retry "retry" edeceğini varsayıp rebuild_async'ı çağırıyor.
    Amacımız: positions.get_open_positions() içindeki rebuild_async doğru şekilde
    build_signed_get'i tekrar çağırıyor mu ve sonuç dönebiliyor mu kontrol etmek.
    """

    build_calls = []

    # build_signed_get'i sayılabilir hale getiriyoruz
    async def fake_build_signed_get(url, params=None, recv_window=None):
        build_calls.append(
            {"url": url, "params": params or {}, "recv_window": recv_window}
        )
        # İmza sonucu gibi dönelim
        return f"signed://{len(build_calls)}", {"X-MBX-APIKEY": "k"}

    monkeypatch.setattr(positions, "build_signed_get", fake_build_signed_get)

    # Gerçek httpx.AsyncClient'ı by-pass etmek için bir no-op client döndürelim
    class FakeAsyncClient:
        def __init__(self, *_, **__):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(positions.httpx, "AsyncClient", FakeAsyncClient)

    rebuild_invocations = []

    # arequest_with_retry'i sahteleyelim: İçinden rebuild_async'ı özellikle çağıralım
    async def fake_arequest_with_retry(
        _client, _method, _full_url, _headers=None, **_kwargs
    ):
        # Retry öncesi rebuild_async'ı çağırıyormuş gibi simüle ediyoruz
        rebuilt = _kwargs.get("rebuild_async")
        assert callable(rebuilt), "rebuild_async callable olmalı"
        new_url, new_headers = (
            await rebuilt()
        )  # rebuilt awaitable döner; await etmeliyiz
        rebuild_invocations.append({"new_url": new_url, "new_headers": new_headers})
        # Ardından final response dönüyormuş gibi yapalım
        return FakeResponse({"positions": []})

    monkeypatch.setattr(positions, "arequest_with_retry", fake_arequest_with_retry)

    # ÇAĞRI
    data = await positions.get_open_positions()

    # BEKLENTİLER
    assert data == {"positions": []}
    # build_signed_get: 1) ilk imza, 2) retry sırasında rebuild imzası => toplam 2
    assert (
        len(build_calls) == 2
    ), f"build_signed_get çağrı sayısı beklenenden farklı: {build_calls}"
    # rebuild_async gerçekte çağrılmış olmalı ve yeni imza objeleri dönmüş olmalı
    assert len(rebuild_invocations) == 1
    assert rebuild_invocations[0]["new_url"].startswith("signed://")
    assert "X-MBX-APIKEY" in rebuild_invocations[0]["new_headers"]


@pytest.mark.asyncio
async def test_get_open_positions_no_retry_path(monkeypatch):
    """
    Senaryo: Retry YOK. arequest_with_retry rebuild_async'ı hiç çağırmadan tek seferde yanıt döner.
    Amacımız: İlk imzada çalışıp temizce JSON dönüldüğünü doğrulamak.
    """

    build_calls = []

    async def fake_build_signed_get(url, params=None, recv_window=None):
        build_calls.append(
            {"url": url, "params": params or {}, "recv_window": recv_window}
        )
        return "signed://first", {"X-MBX-APIKEY": "k"}

    monkeypatch.setattr(positions, "build_signed_get", fake_build_signed_get)

    class FakeAsyncClient:
        def __init__(self, *_, **__):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(positions.httpx, "AsyncClient", FakeAsyncClient)

    async def fake_arequest_with_retry(
        _client, _method, _full_url, _headers=None, **_kwargs
    ):
        # Retry yok, rebuild_async'ı KESİNLİKLE çağırmıyoruz
        return FakeResponse({"positions": [{"symbol": "BTCUSDT", "positionAmt": "0"}]})

    monkeypatch.setattr(positions, "arequest_with_retry", fake_arequest_with_retry)

    data = await positions.get_open_positions()

    assert data["positions"][0]["symbol"] == "BTCUSDT"
    # Retry olmadığı için ikinci bir imza beklemiyoruz
    assert (
        len(build_calls) == 1
    ), f"build_signed_get sadece bir kez çağrılmalı: {build_calls}"
