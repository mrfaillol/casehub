"""Async circuit breaker + bulkhead for slow external upstreams.

Context (incident 2026-06-16, prod VS 504): the Maestro/Ollama client waits
up to 300s on a CPU-bound model. Ollama serialises generation, so under
concurrent load every uvicorn worker piles up waiting on the same upstream
and the whole app stops answering — nginx returns 504 on *every* route, not
just the slow one. The app never crashed; it saturated.

This primitive bounds that blast radius with two complementary guards:

1. **Bulkhead** (``max_concurrency``): at most N calls are ever in-flight to
   the upstream at once. Because the model serialises anyway, extra callers
   gain nothing by waiting — so the (N+1)th call fails fast with
   :class:`CircuitOpenError` instead of holding a worker hostage. This is the
   guard that actually prevents total worker exhaustion.
2. **Circuit breaker** (``failure_threshold`` / ``reset_timeout``): after N
   consecutive failures (timeouts, connection errors, non-2xx) the breaker
   trips OPEN and every call fails fast for ``reset_timeout`` seconds. One
   HALF_OPEN probe is then allowed; success closes it, failure re-opens.

Design notes:
- Pure stdlib + asyncio. No new dependency (council token-economy: surgical).
- The breaker NEVER reaches out to the upstream itself; callers turn a
  :class:`CircuitOpenError` into their own fast degraded response.
- ``time_func`` is injectable so tests drive state transitions with a fake
  clock instead of sleeping.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    """Raised when a call is rejected without touching the upstream.

    Two reasons: the breaker is OPEN (too many recent failures) or the
    bulkhead is saturated (too many calls already in-flight). Callers should
    catch this and return a fast degraded response — never a 5xx or a hang.
    """


class AsyncCircuitBreaker:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 3,
        reset_timeout: float = 30.0,
        max_concurrency: int = 2,
        time_func: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.max_concurrency = max_concurrency
        self._time = time_func
        self._state = self.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._inflight = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        return self._state

    @property
    def inflight(self) -> int:
        return self._inflight

    async def _acquire(self) -> None:
        """Admission control. Raises CircuitOpenError to reject fast."""
        async with self._lock:
            if self._state == self.OPEN:
                if self._time() - self._opened_at >= self.reset_timeout:
                    # Cooldown elapsed — allow a single probe through.
                    self._state = self.HALF_OPEN
                    logger.info("circuit %s: OPEN -> HALF_OPEN (probe)", self.name)
                else:
                    raise CircuitOpenError(f"{self.name}: circuit OPEN")
            if self._state == self.HALF_OPEN and self._inflight >= 1:
                # Only one probe at a time while half-open.
                raise CircuitOpenError(f"{self.name}: HALF_OPEN probe already running")
            if self._inflight >= self.max_concurrency:
                raise CircuitOpenError(
                    f"{self.name}: bulkhead saturated ({self._inflight}/{self.max_concurrency})"
                )
            self._inflight += 1

    async def _release(self, *, success: bool) -> None:
        async with self._lock:
            self._inflight = max(0, self._inflight - 1)
            if success:
                if self._state != self.CLOSED:
                    logger.info("circuit %s: -> CLOSED", self.name)
                self._state = self.CLOSED
                self._failures = 0
            else:
                self._failures += 1
                if self._state == self.HALF_OPEN or self._failures >= self.failure_threshold:
                    if self._state != self.OPEN:
                        logger.warning(
                            "circuit %s: -> OPEN after %d failure(s)", self.name, self._failures
                        )
                    self._state = self.OPEN
                    self._opened_at = self._time()

    async def call(self, factory: Callable[[], Awaitable[T]]) -> T:
        """Run ``factory()`` under the breaker + bulkhead.

        ``factory`` is a zero-arg callable returning an awaitable (so the
        coroutine is only created once admission is granted). Re-raises
        :class:`CircuitOpenError` on rejection and the original exception on
        upstream failure (after recording it).
        """
        await self._acquire()
        try:
            result = await factory()
        except BaseException:
            await self._release(success=False)
            raise
        await self._release(success=True)
        return result
