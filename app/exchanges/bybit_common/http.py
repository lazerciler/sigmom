#!/usr/bin/env python3
# app/exchanges/bybit_common/http.py
# Python 3.9

from typing import Dict, Tuple, Optional, Mapping, Callable
import time
import hmac
import hashlib
import json
from urllib.parse import quote


class BybitHttp:
    """
    Bybit V5 imzalı GET/POST üretimi için ortak çekirdek.
    BASE_URL, API_KEY, API_SECRET ve helper hook'ları dışarıdan verilir.
    İmza kuralı (V5):
      sign_target = f"{timestamp}{api_key}{recv_window}{payload}"
      - GET/DELETE payload: sıralı ve URL-encode edilmiş query string
      - POST payload: JSON string
    Header'lar:
      X-BAPI-API-KEY, X-BAPI-TIMESTAMP, X-BAPI-SIGN, X-BAPI-RECV-WINDOW
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
        self.api_key = api_key or ""
        self.api_secret = api_secret or ""
        self.get_server_time = get_server_time
        self.recv_short = int(recv_window_short_ms)
        self.recv_long = int(recv_window_long_ms)
        self.on_sign_params = on_sign_params
        self.extra_headers = extra_headers

    # ---- internals ----
    def _ts(self) -> int:
        try:
            ts = int(self.get_server_time())
            # saniye gelirse ms'e yükselt (Bybit V5 ms ister)
            if ts < 10**12:
                ts *= 1000
            return ts
        except Exception:
            return int(time.time() * 1000)

    @staticmethod
    def _sorted_query(params: Mapping) -> str:
        # None parametreleri tamamen dışarıda bırak; kalanları sıralı & URL-encode birleştir
        items = sorted((k, str(v)) for k, v in (params or {}).items() if v is not None)
        return "&".join(f"{k}={quote(v, safe='')}" for k, v in items)

    @staticmethod
    def _json_payload(params: Mapping) -> str:
        # KANONİK JSON: anahtarlar sıralı olmalı; imza bu string'e göre hesaplanır
        return json.dumps(
            dict(params or {}),
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=False,
        )

    def _sign(
        self, recv_ms: int, payload: str, ts: Optional[int] = None
    ) -> Tuple[str, int]:
        t = self._ts() if ts is None else int(ts)
        target = f"{t}{self.api_key}{int(recv_ms)}{payload}"
        sig = hmac.new(
            self.api_secret.encode("utf-8"), target.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return sig, t

    def _headers(self, ts: int, sig: str, recv_ms: int) -> Dict:
        hdr = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": str(ts),
            "X-BAPI-RECV-WINDOW": str(int(recv_ms)),
            "X-BAPI-SIGN": sig,
            "X-BAPI-SIGN-TYPE": "2",
            "Content-Type": "application/json",
        }
        if self.extra_headers:
            hdr.update(self.extra_headers())
        return hdr

    # ---- public builders ----
    def build_get(
        self, endpoint: str, params: Optional[Dict] = None, window: str = "short"
    ) -> Tuple[str, Dict]:
        payload: Dict = dict(params or {})
        if self.on_sign_params:
            payload = self.on_sign_params(payload)
        q = self._sorted_query(payload)
        sig, ts = self._sign(self.recv_long if window == "long" else self.recv_short, q)
        full_url = f"{self.base_url}{endpoint}" + (f"?{q}" if q else "")
        headers = self._headers(
            ts, sig, self.recv_long if window == "long" else self.recv_short
        )
        return full_url, headers

    # Yeni: POST için aynı anda (url, headers, body_bytes) döndür.
    # Var olan build_post'u bozmamak için ayrı bir yardımcı verdik.
    def build_post_with_body(
        self, endpoint: str, params: Optional[Dict] = None, window: str = "short"
    ) -> Tuple[str, Dict, bytes]:
        payload: Dict = dict(params or {})
        if self.on_sign_params:
            payload = self.on_sign_params(payload)
        body = self._json_payload(payload)  # KANONİK JSON (sort_keys)
        sig, ts = self._sign(
            self.recv_long if window == "long" else self.recv_short, body
        )
        full_url = f"{self.base_url}{endpoint}"
        headers = self._headers(
            ts, sig, self.recv_long if window == "long" else self.recv_short
        )
        return full_url, headers, body.encode("utf-8")

    def build_post(
        self, endpoint: str, params: Optional[Dict] = None, window: str = "short"
    ) -> Tuple[str, Dict]:
        payload: Dict = dict(params or {})
        if self.on_sign_params:
            payload = self.on_sign_params(payload)
        body = self._json_payload(payload)
        sig, ts = self._sign(
            self.recv_long if window == "long" else self.recv_short, body
        )
        full_url = f"{self.base_url}{endpoint}"
        headers = self._headers(
            ts, sig, self.recv_long if window == "long" else self.recv_short
        )
        return full_url, headers
