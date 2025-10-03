#!/usr/bin/env python3
# app/exchanges/mexc_common/http.py
# Python 3.9

from __future__ import annotations
from typing import Dict, Tuple, Optional

from app.exchanges.mexc_futures.utils import build_signed_get, build_signed_post
from app.exchanges.mexc_futures.settings import BASE_URL


class MexcHttp:
    """MEXC için imzalı URL+header üretimi. Ağ çağrılarını üst katman yapar."""

    def __init__(self, *, base_url: str | None = None):
        self.base_url = (base_url or BASE_URL).rstrip("/")

    async def build_get(
        self, endpoint: str, params: Optional[Dict] = None
    ) -> Tuple[str, Dict]:
        """
        İMZA **async** üretildiği için bu metod da async.
        Dönüş: (full_url: str, headers: dict)
        """
        url = f"{self.base_url}{endpoint}"
        return await build_signed_get(url, params or {})

    async def build_post(
        self, endpoint: str, params: Optional[Dict] = None
    ) -> Tuple[str, Dict]:
        """
        İMZA **async** üretildiği için bu metod da async.
        Dönüş: (full_url: str, headers: dict)
        """
        url = f"{self.base_url}{endpoint}"
        return await build_signed_post(url, params or {})
