"""Shared, pooled httpx client for the CaseHub <-> PDPJ / ComunicaAPI calls.

The PDPJ integration in ``services/comunicaapi.py`` made each outbound call --
the OAuth token request to Keycloak and the ComunicaAPI search -- inside its
own ``async with httpx.AsyncClient(...)``, building and tearing down a
connection pool every time and reusing no connection.

This module holds one process-wide :class:`httpx.AsyncClient` with keep-alive
connection pooling. httpx pools per host internally, so one shared client
cleanly serves both the token endpoint (``sso.cloud.pje.jus.br``) and the
ComunicaAPI host (``comunicaapi.pje.jus.br``).

Security contract (council ruling ``2026-05-22-pool-comunicaapi-httpx-client``):
the client is created with ONLY :class:`httpx.Limits` + a fallback
:class:`httpx.Timeout` -- never ``headers=``, ``auth=``, ``cookies=`` or a
credential-bearing ``base_url``. The Authorization Bearer header and the
token-request body stay 100% per-request at the call sites, so no credential
is ever held at client level or shared between requests.

Mirrors ``services/whatsapp_bot_client.py``. Created lazily;
:func:`aclose_pdpj_client` releases it on app shutdown.
"""
from __future__ import annotations

from typing import Optional

import httpx

# Pool sized for PDPJ traffic: low-frequency (OAuth token is cached ~5min, the
# OAB search runs on a daily cron), so a small keep-alive pool is plenty.
_PDPJ_CLIENT_LIMITS = httpx.Limits(max_keepalive_connections=5, max_connections=10)

# Fallback timeout only. Each call site MUST pass its own explicit per-request
# timeout (token request 15s, ComunicaAPI search 30s); this default never
# silently overrides them.
_DEFAULT_TIMEOUT = httpx.Timeout(15.0)

_client: Optional[httpx.AsyncClient] = None


def get_pdpj_client() -> httpx.AsyncClient:
    """Return the process-wide pooled httpx client for PDPJ / ComunicaAPI.

    Created lazily on first call and reused afterwards, so connections are
    kept alive across calls. The lazy init has no ``await``, so two coroutines
    on the event loop cannot race it. A previously closed client (after
    :func:`aclose_pdpj_client`) is replaced.

    The client carries NO credential state -- no ``headers``, ``auth`` or
    ``cookies``. Callers pass Authorization and Content-Type per request.
    """
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            limits=_PDPJ_CLIENT_LIMITS,
            timeout=_DEFAULT_TIMEOUT,
        )
    return _client


async def aclose_pdpj_client() -> None:
    """Close the shared client and its connection pool.

    Wired into the app shutdown hook. Idempotent: safe to call when no client
    was ever created.
    """
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
