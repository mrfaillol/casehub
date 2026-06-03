"""Regression test for messaging_hub_service.get_channel_status — non-blocking.

get_channel_status calls the WhatsApp bot over HTTP. It used a synchronous
httpx.get(timeout=2.0) while being invoked from async route handlers
(messaging_hub, view_thread, api_get_status), so a slow/down bot blocked the
whole event loop for up to 2s per call. It is now an async method using
httpx.AsyncClient + await; concurrent invocations overlap instead of
serializing on the loop.

Run: pytest tests/test_messaging_hub_channel_status.py
"""
import asyncio
import time

import httpx
import pytest
from sqlalchemy import text

from services.messaging_hub_service import MessagingHubService

_DELAY = 0.3
_N = 4


class _FakeResponse:
    status_code = 200

    def json(self):
        return {"connected": True}


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient whose .get() awaits _DELAY on the loop."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, *args, **kwargs):
        await asyncio.sleep(_DELAY)
        return _FakeResponse()


@pytest.fixture
def email_accounts_table(db):
    """email_accounts is a raw-migration table, not an ORM model."""
    db.execute(text("DROP TABLE IF EXISTS email_accounts"))
    db.execute(text("CREATE TABLE email_accounts (id INTEGER PRIMARY KEY, enabled BOOLEAN)"))
    db.commit()
    yield db
    db.rollback()
    db.execute(text("DROP TABLE IF EXISTS email_accounts"))
    db.commit()


def test_get_channel_status_does_not_block_event_loop(email_accounts_table, monkeypatch):
    """N concurrent get_channel_status() calls, each awaiting _DELAY on the bot
    HTTP call, must overlap on the event loop (~_DELAY total) rather than
    serialize (~N*_DELAY) as the old blocking httpx.get() did."""
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    svc = MessagingHubService(email_accounts_table, org_id=1)

    async def _run():
        t0 = time.perf_counter()
        results = await asyncio.gather(*(svc.get_channel_status() for _ in range(_N)))
        return time.perf_counter() - t0, results

    elapsed, results = asyncio.run(_run())

    serialized = _N * _DELAY
    assert elapsed < serialized / 2, (
        f"{elapsed:.2f}s for {_N} concurrent calls — expected overlap near "
        f"{_DELAY}s, not serialized {serialized:.2f}s (event loop blocked)"
    )
    assert all(r["whatsapp"] == "connected" for r in results)
    assert all("email" in r for r in results)


def test_get_channel_status_handles_bot_failure(email_accounts_table, monkeypatch):
    """A failing bot HTTP call degrades to 'offline', it does not raise."""

    class _BoomClient(_FakeAsyncClient):
        async def get(self, url, *args, **kwargs):
            raise httpx.ConnectError("bot unreachable")

    monkeypatch.setattr(httpx, "AsyncClient", _BoomClient)
    svc = MessagingHubService(email_accounts_table, org_id=1)

    status = asyncio.run(svc.get_channel_status())

    assert status["whatsapp"] == "offline"
    assert "email" in status
