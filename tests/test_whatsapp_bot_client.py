"""Unit tests for the shared, pooled WhatsApp bot-bridge httpx client.

These exercise only the lifecycle contract of the shared client — they make
no network call and need no app stack:

    python -m pytest tests/test_whatsapp_bot_client.py --noconftest
"""
import httpx
import pytest

from services.whatsapp_bot_client import aclose_bot_client, get_bot_client


@pytest.fixture(autouse=True)
async def _isolate_shared_client():
    """Reset the process-wide client around every test for isolation."""
    await aclose_bot_client()
    yield
    await aclose_bot_client()


async def test_get_bot_client_returns_async_client():
    assert isinstance(get_bot_client(), httpx.AsyncClient)


async def test_get_bot_client_is_singleton():
    # the whole point: the same pooled client is reused across calls
    assert get_bot_client() is get_bot_client()


async def test_get_bot_client_is_open():
    assert get_bot_client().is_closed is False


async def test_aclose_closes_and_resets():
    client = get_bot_client()
    await aclose_bot_client()
    assert client.is_closed is True
    # the next call builds a fresh, open client
    new_client = get_bot_client()
    assert new_client is not client
    assert new_client.is_closed is False


async def test_get_bot_client_recreates_when_closed():
    client = get_bot_client()
    await client.aclose()
    # a closed client is never handed back out
    assert get_bot_client() is not client


async def test_aclose_is_idempotent():
    await aclose_bot_client()
    await aclose_bot_client()  # must not raise when no client exists
