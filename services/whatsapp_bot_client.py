"""Shared, pooled httpx client for the Python <-> WhatsApp Node-bot bridge.

Every bridge call in ``routes/whatsapp_chat.py`` used to open its own client
with ``async with httpx.AsyncClient(...)``. That pattern pays a fresh TCP
connection (and a fresh connection pool) on *every* call and reuses nothing:
status polling, conversation fetches and message sends each re-handshake the
bot. On a remote bot that is one extra round-trip per request.

This module holds one process-wide :class:`httpx.AsyncClient` with keep-alive
connection pooling, so repeated bridge calls reuse live connections. Callers
keep passing an explicit per-request ``timeout=`` so each call retains its own
bound (a send needs longer than a status check).

No new dependency and no new network surface: it is a plain pooled httpx
client talking to the same ``WHATSAPP_BOT_URL`` as before. The client is
created lazily on first use; :func:`aclose_bot_client` releases it on app
shutdown.
"""
from __future__ import annotations

from typing import Optional

import httpx

# Pool sized for bridge traffic: a handful of concurrent admin/chat requests,
# kept alive so repeated polling (status, conversations) reuses connections.
_BOT_CLIENT_LIMITS = httpx.Limits(max_keepalive_connections=10, max_connections=20)

# Fallback timeout for any caller that does not pass an explicit per-request
# timeout. Bridge calls should still pass their own ``timeout=`` — sends and
# pairing-code requests legitimately need longer than a status check.
_DEFAULT_TIMEOUT = httpx.Timeout(15.0)

_client: Optional[httpx.AsyncClient] = None


def get_bot_client() -> httpx.AsyncClient:
    """Return the process-wide pooled httpx client for the bot bridge.

    Created lazily on first call and reused afterwards, so connections are
    kept alive across requests. Safe to call from any async handler: the lazy
    init has no ``await``, so two coroutines on the event loop cannot race it.
    A previously closed client (after :func:`aclose_bot_client`) is replaced.
    """
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            limits=_BOT_CLIENT_LIMITS,
            timeout=_DEFAULT_TIMEOUT,
        )
    return _client


async def aclose_bot_client() -> None:
    """Close the shared client and its connection pool.

    Wired into the app shutdown hook so keep-alive connections are released
    cleanly. Idempotent: safe to call when no client was ever created.
    """
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
