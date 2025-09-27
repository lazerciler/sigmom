#!/usr/bin/env python3
# app/exchanges/binance_common/http.py
# Python 3.9

from typing import Dict, Tuple, Optional, Mapping, Callable
from urllib.parse import urlencode
import time
import hmac
import hashlib


class BinanceHttp:
    """Binance imzalı GET/POST üretimi için ortak çekirdek.
    BASE_URL, API_KEY, API_SECRET ve helper hook'ları dışarıdan verilir.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        api_secret: str,
        get_server_time: Callable[[], int],
        recv_window_short_ms: int,
        recv_window_long_ms: int,
        # opsiyonel hook'lar
        on_sign_params: Optional[Callable[[Dict], Dict]] = None,
        extra_headers: Optional[Callable[[], Dict]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.get_server_time = get_server_time
        self.recv_short = int(recv_window_short_ms)
        self.recv_long = int(recv_window_long_ms)
        self.on_sign_params = on_sign_params
        self.extra_headers = extra_headers

    def _headers(self) -> Dict:
        hdr = {"X-MBX-APIKEY": self.api_key}
        if self.extra_headers:
            hdr.update(self.extra_headers())
        return hdr

    def _ts(self) -> int:
        try:
            return self.get_server_time()
        except (
            Exception
        ):  # noqa: BLE001  # get_server_time wrapper'ı farklı istisnalar atabilir
            return int(time.time() * 1000)

    def _sign(self, params: Mapping) -> Tuple[str, str]:
        query = urlencode(sorted((k, str(v)) for k, v in params.items()))
        return (
            hmac.new(
                self.api_secret.encode("utf-8"),
                query.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest(),
            query,
        )

    def _prep(
        self, endpoint: str, params: Optional[Dict], window: str
    ) -> Tuple[str, Dict]:
        payload: Dict = dict(params or {})
        payload.setdefault("timestamp", self._ts())
        payload.setdefault(
            "recvWindow", self.recv_long if window == "long" else self.recv_short
        )
        if self.on_sign_params:
            payload = self.on_sign_params(payload)  # son dokunuş
        sig, query = self._sign(payload)
        full_url = f"{self.base_url}{endpoint}?{query}&signature={sig}"
        return full_url, self._headers()

    def build_get(
        self, endpoint: str, params: Optional[Dict] = None, window: str = "short"
    ) -> Tuple[str, Dict]:
        return self._prep(endpoint, params, window)

    def build_post(
        self, endpoint: str, params: Optional[Dict] = None, window: str = "short"
    ) -> Tuple[str, Dict]:
        return self._prep(endpoint, params, window)
