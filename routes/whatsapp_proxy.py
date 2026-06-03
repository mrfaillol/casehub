"""
CaseHub - WhatsApp Bot Proxy

A generic transparent reverse-proxy mounted at /whatsapp-api. Forwards EVERY
method + path to the Node WhatsApp bot (WHATSAPP_BOT_URL).

Why this exists: static/js/chat.js calls /whatsapp-api/api/qr, /whatsapp-api/api/status,
/whatsapp-api/api/send, /whatsapp-api/api/conversations, ... Before this router
nothing answered those paths (404) — so the QR never rendered. This proxy is the
fix that unblocks the QR.

Security:
  * Auth-gated with the same get_current_user dependency every other route uses.
    An unauthenticated request gets 401 — the bot is never exposed unauthenticated.
  * Streaming responses (SSE: /api/events/*) are passed through with their
    text/event-stream content-type so real-time messages keep flowing.
  * The bot URL comes from config (no secrets in code). Falls back to localhost
    for dev when the Docker service name does not resolve.
"""
from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from auth import get_current_user
from config import settings
from models import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp-api", tags=["whatsapp-proxy"])


# Primary bot URL from config; localhost fallback for local dev where the
# docker-compose service name "whatsapp-bot" does not resolve.
_PRIMARY_BOT_URL = (getattr(settings, "WHATSAPP_BOT_URL", "") or "http://whatsapp-bot:3001").rstrip("/")
_FALLBACK_BOT_URL = (os.getenv("WHATSAPP_BOT_FALLBACK_URL", "http://localhost:3001")).rstrip("/")

# Hop-by-hop headers must not be forwarded (RFC 7230 §6.1).
_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
    "authorization", "cookie", "set-cookie",
}

# Paths that are Server-Sent Event streams — must be streamed, not buffered.
_SSE_HINTS = ("/events/", "/stream")


def _filter_headers(headers) -> dict:
    return {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP}


def _is_stream_path(path: str) -> bool:
    return any(hint in path for hint in _SSE_HINTS)


def _resolve_request_org_id(request: Request) -> int | None:
    """Resolve the tenant org_id for the current request.

    Multi-session per-tenant (F29, 2026-05-27): every proxy call to the
    WhatsApp bot must carry X-Org-Id so the bot dispatches to the right
    tenant's session. The browser does NOT set this header — TenantMiddleware
    resolved the tenant from the Host header (cliente.example.com),
    set `request.state.org_id`, and we surface that to the bot here.

    Falls back to None when the request has no tenant context (the bot then
    uses its CASEHUB_DEFAULT_ORG_ID — the previous single-tenant behaviour).
    """
    return getattr(getattr(request, "state", None), "org_id", None)


async def _forward(request: Request, path: str) -> Response:
    """Forward one request to the bot, trying primary then fallback URL."""
    body = await request.body()
    fwd_headers = _filter_headers(request.headers)
    # Multi-tenant dispatch — overwrite (or set) X-Org-Id from the resolved
    # tenant context. The browser cannot spoof it because we always set our
    # own value, never trusting an incoming header.
    org_id = _resolve_request_org_id(request)
    if org_id is not None:
        fwd_headers["X-Org-Id"] = str(org_id)
    else:
        # If TenantMiddleware did not resolve a tenant, scrub any header the
        # caller may have sent — we never trust client-supplied org ids.
        fwd_headers.pop("x-org-id", None)
        fwd_headers.pop("X-Org-Id", None)
    query = request.url.query
    suffix = f"/{path}" if path else ""
    if query:
        suffix = f"{suffix}?{query}"

    streaming = _is_stream_path(path)
    last_error: Exception | None = None

    # Deduplicated, ordered list of bot URLs to try (primary, then fallback).
    bases = [_PRIMARY_BOT_URL]
    if _FALLBACK_BOT_URL and _FALLBACK_BOT_URL != _PRIMARY_BOT_URL:
        bases.append(_FALLBACK_BOT_URL)

    for base in bases:
        target = f"{base}{suffix}"
        try:
            if streaming:
                return await _stream_response(request, base, suffix, body, fwd_headers)

            timeout = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.request(
                    request.method,
                    target,
                    content=body if body else None,
                    headers=fwd_headers,
                    follow_redirects=False,
                )
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=_filter_headers(resp.headers),
                media_type=resp.headers.get("content-type"),
            )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.HTTPStatusError) as exc:
            last_error = exc
            logger.warning("[whatsapp-proxy] %s unreachable (%s) — trying next", base, exc)
            continue
        except Exception as exc:  # noqa: BLE001 — proxy must never 500 the page
            last_error = exc
            logger.error("[whatsapp-proxy] error forwarding to %s: %s", target, exc)
            break

    return JSONResponse(
        {"error": "whatsapp bot unavailable", "detail": str(last_error) if last_error else None},
        status_code=502,
    )


async def _stream_response(request: Request, base: str, suffix: str, body: bytes, headers: dict) -> StreamingResponse:
    """Stream an SSE response from the bot (real-time messages / conversations).

    Headers passed in already include X-Org-Id (set by _forward) so the SSE
    upstream subscribes to the correct tenant's event channel.
    """
    timeout = httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)
    client = httpx.AsyncClient(timeout=timeout)
    stream_cm = client.stream(
        request.method, f"{base}{suffix}",
        content=body if body else None, headers=headers,
    )
    try:
        resp = await stream_cm.__aenter__()
        if resp.status_code != 200:
            await resp.aread()
            raise httpx.HTTPStatusError(
                f"SSE upstream returned HTTP {resp.status_code}",
                request=resp.request,
                response=resp,
            )
    except Exception:
        await stream_cm.__aexit__(None, None, None)
        await client.aclose()
        raise

    async def event_stream():
        try:
            async for chunk in resp.aiter_raw():
                if await request.is_disconnected():
                    break
                yield chunk
        except httpx.ReadTimeout:
            yield b'data: {"type": "reconnect"}\n\n'
        except Exception as exc:  # noqa: BLE001
            logger.warning("[whatsapp-proxy] SSE stream error: %s", exc)
            yield b'data: {"type": "error"}\n\n'
        finally:
            await stream_cm.__aexit__(None, None, None)
            await client.aclose()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def proxy(request: Request, path: str, db: Session = Depends(get_db)):
    """Transparent proxy to the WhatsApp bot for any /whatsapp-api/* request."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    # Release the DB connection before forwarding — the proxy itself needs no DB,
    # and SSE paths hold the request open indefinitely.
    db.close()
    return await _forward(request, path)
