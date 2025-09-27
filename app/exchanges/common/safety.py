#!/usr/bin/env python3
# app/exchanges/common/safety.py
# Python 3.9

import asyncio
import time
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict

logger = logging.getLogger(__name__)


@dataclass
class SafetyGate:
    """
    Borsa pozisyon modunu bir kez doğrulayıp/ayarlayıp
    belirsizlikte 'hold' açan ortak bekçi.
    """

    position_mode_expected: str
    get_mode: Callable[[], Awaitable[Dict]]
    set_mode: Callable[[str], Awaitable[Dict]]
    hold_seconds: int = 300
    mode_read_retry: int = 3
    mode_read_delay: float = 1.0

    _until: float = 0.0
    _reason: str = ""
    _checked_event: asyncio.Event = field(default_factory=asyncio.Event)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def is_blocked(self) -> tuple[bool, str]:
        return (time.monotonic() < self._until), self._reason

    def start_hold(self, reason: str) -> None:
        self._until = time.monotonic() + self.hold_seconds
        self._reason = reason
        logger.error("SAFETY HOLD %ss: %s", self.hold_seconds, reason)

    async def ensure_position_mode_once(self) -> None:
        if self._checked_event.is_set():
            return
        async with self._lock:
            if self._checked_event.is_set():
                return
            last_err = ""
            chk = None
            for _ in range(self.mode_read_retry):
                chk = await self.get_mode()
                if chk.get("success"):
                    break
                last_err = str(chk.get("message") or "mode_read_failed")
                await asyncio.sleep(self.mode_read_delay)
            if not (chk and chk.get("success")):
                logger.warning(
                    "Position mode read failed (retry exhausted): %s", last_err
                )
                self.start_hold(
                    "Uncertain trading mode: unable to read mode information from exchange"
                )
                self._checked_event.set()
                return
            actual = chk.get("mode")
            logger.info(
                "Position mode check → exchange=%s, expected=%s",
                actual,
                self.position_mode_expected,
            )
            if actual != self.position_mode_expected:
                logger.warning("Position mode mismatch → trying autoswitch.")
                sw = await self.set_mode(self.position_mode_expected)
                if not sw.get("success"):
                    logger.warning(
                        "Position mode autoswitch failed: %s", sw.get("message")
                    )
                    self.start_hold(
                        "Belirsiz işlem modu: borsa modu config ile uyumsuz"
                    )
                    self._checked_event.set()
                    return
                logger.info("Position mode switched to %s", self.position_mode_expected)
            self._checked_event.set()

    def reset(self) -> None:
        """Testlerde kullanışlı."""
        self._until = 0.0
        self._reason = ""
        self._checked_event.clear()
