"""CaseHub.md — Maestro AI bridge (Fatia 7).

Proxy enxuto do CaseHub para o Maestro backend (worktree
`casehub-maestro-backend`). O Maestro ainda está em desenvolvimento, então
aceitamos respostas com shape variável (`suggestion` / `text` / `output` /
`response`) e logamos warning quando precisamos heurística.

URL configurável via env `MAESTRO_BASE_URL` (default `http://localhost:8005`).
Timeout 15s — LLM upstream pode demorar.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = os.getenv("MAESTRO_BASE_URL", "http://localhost:8005")
DEFAULT_TIMEOUT = 15.0
DEFAULT_KIND = "suggest_continuation"
MAX_PARAGRAPH_BYTES = 16 * 1024  # 16 KB — um parágrafo realista


class MaestroUnavailable(RuntimeError):
    """Maestro backend not reachable (connection refused, DNS, etc.)."""


class MaestroTimeout(RuntimeError):
    pass


class ParagraphTooLarge(ValueError):
    pass


@dataclass(frozen=True)
class MaestroResult:
    suggestion: str
    model: str
    took_ms: int


def _coerce_suggestion(payload: Any) -> str:
    """Be permissive about Maestro response shape during early development."""
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return ""
    for key in ("suggestion", "text", "output", "response", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    # Some agent backends nest {"data": {"suggestion": "..."}} or {"choices": [{"text": ...}]}.
    nested = payload.get("data")
    if isinstance(nested, dict):
        deep = _coerce_suggestion(nested)
        if deep:
            return deep
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            for key in ("text", "content", "message"):
                value = first.get(key)
                if isinstance(value, str) and value.strip():
                    return value
                if isinstance(value, dict):
                    deep = _coerce_suggestion(value)
                    if deep:
                        return deep
    return ""


async def suggest(
    paragraph: str,
    *,
    case_id: str | None = None,
    kind: str = DEFAULT_KIND,
    base_url: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> MaestroResult:
    """POST {base_url}/suggest and return the model's suggestion.

    Raises:
        ParagraphTooLarge: paragraph exceeds MAX_PARAGRAPH_BYTES.
        MaestroTimeout: upstream did not respond within `timeout`.
        MaestroUnavailable: connection error / non-2xx (with status in message).
    """
    encoded = paragraph.encode("utf-8")
    if len(encoded) > MAX_PARAGRAPH_BYTES:
        raise ParagraphTooLarge(
            f"paragraph is {len(encoded)} bytes; limit is {MAX_PARAGRAPH_BYTES}"
        )

    try:
        import httpx
    except ImportError as e:
        raise MaestroUnavailable(f"httpx not installed: {e}")

    url = (base_url or DEFAULT_BASE_URL).rstrip("/") + "/suggest"
    body: dict[str, Any] = {
        "paragraph": paragraph,
        "kind": kind,
    }
    if case_id:
        body["case_id"] = case_id

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=body)
    except httpx.TimeoutException as e:
        raise MaestroTimeout(f"maestro timeout after {timeout}s: {e}") from e
    except (httpx.RequestError, OSError) as e:
        raise MaestroUnavailable(f"maestro unreachable at {url}: {e}") from e

    took_ms = int((time.monotonic() - start) * 1000)
    if response.status_code >= 400:
        raise MaestroUnavailable(
            f"maestro returned {response.status_code}: {response.text[:200]}"
        )

    try:
        payload = response.json()
    except ValueError:
        payload = response.text

    suggestion = _coerce_suggestion(payload)
    if not suggestion:
        logger.warning(
            "maestro returned unrecognized shape (status %s): %s",
            response.status_code,
            (response.text or "")[:300],
        )
    model = ""
    if isinstance(payload, dict):
        model = str(payload.get("model") or payload.get("engine") or "")

    return MaestroResult(suggestion=suggestion, model=model, took_ms=took_ms)
