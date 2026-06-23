"""Tests for services.circuit_breaker.AsyncCircuitBreaker.

Locks in the guards added after the 2026-06-16 prod 504 (worker exhaustion
on the Ollama upstream): the breaker trips OPEN after N failures and fast-
fails, recovers via a single HALF_OPEN probe, and the bulkhead rejects calls
beyond max_concurrency so a slow upstream can never park every worker.

Run: pytest tests/test_circuit_breaker.py
"""
from __future__ import annotations

import asyncio

import pytest

from services.circuit_breaker import AsyncCircuitBreaker, CircuitOpenError


class _Clock:
    """Injectable monotonic clock so tests drive timeouts without sleeping."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


async def _ok():
    return "ok"


async def _boom():
    raise RuntimeError("upstream failure")


async def test_opens_after_threshold_then_fast_fails():
    clock = _Clock()
    cb = AsyncCircuitBreaker("t", failure_threshold=3, reset_timeout=30, time_func=clock)

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await cb.call(_boom)
    assert cb.state == AsyncCircuitBreaker.OPEN

    # While OPEN the upstream is never touched: a call that *would* succeed is
    # rejected fast with CircuitOpenError instead.
    with pytest.raises(CircuitOpenError):
        await cb.call(_ok)
    assert cb.inflight == 0  # rejected calls never occupy a slot


async def test_half_open_probe_success_closes():
    clock = _Clock()
    cb = AsyncCircuitBreaker("t", failure_threshold=2, reset_timeout=30, time_func=clock)

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await cb.call(_boom)
    assert cb.state == AsyncCircuitBreaker.OPEN

    clock.advance(31)  # cooldown elapsed -> next call is the HALF_OPEN probe
    assert await cb.call(_ok) == "ok"
    assert cb.state == AsyncCircuitBreaker.CLOSED


async def test_half_open_probe_failure_reopens():
    clock = _Clock()
    cb = AsyncCircuitBreaker("t", failure_threshold=2, reset_timeout=30, time_func=clock)

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await cb.call(_boom)
    clock.advance(31)
    with pytest.raises(RuntimeError):
        await cb.call(_boom)  # probe fails
    assert cb.state == AsyncCircuitBreaker.OPEN
    # Still within the fresh cooldown -> fast fail again.
    with pytest.raises(CircuitOpenError):
        await cb.call(_ok)


async def test_bulkhead_rejects_beyond_max_concurrency():
    cb = AsyncCircuitBreaker("t", failure_threshold=99, max_concurrency=2)
    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow():
        started.set()
        await release.wait()
        return "done"

    # Park two calls in-flight (fills the bulkhead).
    t1 = asyncio.create_task(cb.call(_slow))
    t2 = asyncio.create_task(cb.call(_slow))
    await asyncio.sleep(0.01)
    assert cb.inflight == 2

    # The third caller is rejected immediately rather than waiting/holding.
    with pytest.raises(CircuitOpenError):
        await cb.call(_ok)

    release.set()
    assert await t1 == "done"
    assert await t2 == "done"
    assert cb.inflight == 0


async def test_success_resets_failure_count():
    cb = AsyncCircuitBreaker("t", failure_threshold=3)
    with pytest.raises(RuntimeError):
        await cb.call(_boom)
    with pytest.raises(RuntimeError):
        await cb.call(_boom)
    await cb.call(_ok)  # success clears the streak
    with pytest.raises(RuntimeError):
        await cb.call(_boom)
    # Only one failure since the reset -> still CLOSED.
    assert cb.state == AsyncCircuitBreaker.CLOSED


def test_constructor_validates_args():
    with pytest.raises(ValueError):
        AsyncCircuitBreaker("t", failure_threshold=0)
    with pytest.raises(ValueError):
        AsyncCircuitBreaker("t", max_concurrency=0)
