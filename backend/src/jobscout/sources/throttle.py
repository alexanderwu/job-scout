"""Minimal client-side rate limiting for source adapters.

hiring.cafe's API is unofficial and undocumented, so we self-impose a
conservative request rate instead of discovering the real limit by
getting blocked. A fixed minimum interval between requests is the
simplest scheme that does this; a token bucket (bursts allowed, refill
over time) would let multi-page fetches start faster, but burstiness is
exactly what we don't want against an API tolerating us informally.

``clock`` and ``sleep`` are injectable so tests can verify timing
behavior instantly instead of actually sleeping.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable


class RateLimiter:
    """Enforce a minimum interval between successive operations."""

    def __init__(
        self,
        min_interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if min_interval < 0:
            raise ValueError("min_interval must be >= 0")
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._next_allowed: float | None = None

    async def wait(self) -> None:
        """Sleep just long enough to honor the interval, then proceed."""
        now = self._clock()
        if self._next_allowed is not None and now < self._next_allowed:
            await self._sleep(self._next_allowed - now)
            now = self._next_allowed
        self._next_allowed = now + self.min_interval
