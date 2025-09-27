#!/usr/bin/env python3
# app/exchanges/common/meta_cache.py
# Python 3.9

import asyncio
import time
import logging
from typing import Optional, Callable, Awaitable, TypeVar, Generic

T = TypeVar("T")
logger = logging.getLogger(__name__)


class AsyncTTLCache(Generic[T]):
    """
    Async/TTL önbellek; değeri dışarıdan verilen loader ile getirir.
    Çok basit ve testte kolay resetlenir.
    """

    def __init__(self, ttl: float, loader: Callable[[], Awaitable[T]]):
        self._ttl = ttl
        self._loader = loader
        self._val: Optional[T] = None  # T | None yerine Optional[T] (Py 3.9)
        self._at = 0.0
        self._lock = asyncio.Lock()

    def clear(self) -> None:
        self._val = None
        self._at = 0.0

    async def get(self) -> T:
        now = time.time()
        if self._val is not None and (now - self._at) < self._ttl:
            return self._val
        async with self._lock:
            now = time.time()
            if self._val is not None and (now - self._at) < self._ttl:
                return self._val
            try:
                val = await self._loader()
            except Exception as e:
                # Geçici ağ hatalarında UI'yı "son iyi veri" ile ayakta tut.
                logger.warning("AsyncTTLCache loader failed: %s", e, exc_info=True)
                if self._val is not None:
                    return self._val
                raise
            else:
                self._val = val
                self._at = now
                return self._val
