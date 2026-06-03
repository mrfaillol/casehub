"""Unit tests for the shared, pooled PDPJ / ComunicaAPI httpx client.

These exercise only the lifecycle and security contract of the shared client
-- they make no network call and need no app stack:

    python -m pytest tests/test_pdpj_client.py --noconftest
"""
import httpx
import pytest

from services.pdpj_client import aclose_pdpj_client, get_pdpj_client


@pytest.fixture(autouse=True)
async def _isolate_shared_client():
    """Reset the process-wide client around every test for isolation."""
    await aclose_pdpj_client()
    yield
    await aclose_pdpj_client()


async def test_get_pdpj_client_returns_async_client():
    assert isinstance(get_pdpj_client(), httpx.AsyncClient)


async def test_get_pdpj_client_is_singleton():
    # the whole point: the same pooled client is reused across calls
    assert get_pdpj_client() is get_pdpj_client()


async def test_get_pdpj_client_is_open():
    assert get_pdpj_client().is_closed is False


async def test_get_pdpj_client_carries_no_credential_state():
    # council ruling 2026-05-22-pool-comunicaapi-httpx-client: the pooled
    # client must hold NO credential -- no headers, no auth, no cookies.
    # Authorization Bearer stays 100% per-request at the call sites.
    client = get_pdpj_client()
    assert "authorization" not in {k.lower() for k in client.headers}
    assert client.auth is None
    assert len(client.cookies) == 0


async def test_aclose_closes_and_resets():
    client = get_pdpj_client()
    await aclose_pdpj_client()
    assert client.is_closed is True
    # the next call builds a fresh, open client
    new_client = get_pdpj_client()
    assert new_client is not client
    assert new_client.is_closed is False


async def test_get_pdpj_client_recreates_when_closed():
    client = get_pdpj_client()
    await client.aclose()
    # a closed client is never handed back out
    assert get_pdpj_client() is not client


async def test_aclose_is_idempotent():
    await aclose_pdpj_client()
    await aclose_pdpj_client()  # must not raise when no client exists
