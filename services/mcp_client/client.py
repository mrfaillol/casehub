from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Callable, Protocol

from .policy import MCPPolicy
from .redaction import redact_payload
from .types import MCPInvocationRequest, MCPInvocationResult, MCPServerConfig

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONTENT_CHARS = 4000


class MCPAdapter(Protocol):
    """Small adapter boundary for a CaseHub-owned MCP runtime facade."""

    def call(self, request: MCPInvocationRequest) -> Any:
        ...


class MCPAdapterUnavailable(RuntimeError):
    """Raised when no product-owned MCP adapter has been configured."""


class _UnavailableAdapter:
    def call(self, request: MCPInvocationRequest) -> Any:
        raise MCPAdapterUnavailable("adapter_unconfigured")


class MCPClient:
    """Default-off, policy-gated MCP invocation facade.

    This class deliberately does not bind production to a local Claude/Codex
    stdio session. Runtime transport lives behind an injected adapter or
    adapter_factory owned by CaseHub deployment code.
    """

    def __init__(
        self,
        *,
        policy: MCPPolicy | None = None,
        adapter: MCPAdapter | None = None,
        adapter_factory: Callable[[MCPServerConfig], MCPAdapter] | None = None,
        max_content_chars: int = DEFAULT_MAX_CONTENT_CHARS,
    ) -> None:
        self.policy = policy or MCPPolicy()
        self._adapter = adapter
        self._adapter_factory = adapter_factory
        self.max_content_chars = max(256, int(max_content_chars or DEFAULT_MAX_CONTENT_CHARS))

    def invoke(
        self,
        config: MCPServerConfig,
        request: MCPInvocationRequest,
    ) -> MCPInvocationResult:
        """Evaluate policy, invoke the adapter, and return a redacted result."""
        started = time.monotonic()
        audit_id = self._audit_id(config, request)
        decision = self.policy.evaluate(config, request)
        base_audit = self._base_audit(config, request, audit_id)
        base_audit["policy"] = {
            "allowed": decision.allowed,
            "reason": decision.reason,
            "approval_required": decision.approval_required,
        }

        if not decision.allowed:
            return self._result(
                ok=False,
                is_error=True,
                content=None,
                redacted_audit=base_audit,
                audit_id=audit_id,
                started=started,
            )

        try:
            adapter = self._adapter or (
                self._adapter_factory(config) if self._adapter_factory else _UnavailableAdapter()
            )
            raw_content = adapter.call(request)
            safe_content = self._cap_content(redact_payload(raw_content))
            base_audit["content_preview"] = self._cap_content(
                redact_payload(raw_content),
                limit=min(1000, self.max_content_chars),
            )
            return self._result(
                ok=True,
                is_error=False,
                content=safe_content,
                redacted_audit=base_audit,
                audit_id=audit_id,
                started=started,
            )
        except MCPAdapterUnavailable as exc:
            base_audit["error"] = type(exc).__name__
            base_audit["reason"] = str(exc)
            return self._result(
                ok=False,
                is_error=True,
                content=None,
                redacted_audit=base_audit,
                audit_id=audit_id,
                started=started,
            )
        except Exception as exc:  # noqa: BLE001 - MCP must never take chat down
            logger.warning(
                "MCP invocation failed: server=%s capability=%s error=%s",
                config.name,
                request.capability_name,
                type(exc).__name__,
            )
            base_audit["error"] = type(exc).__name__
            return self._result(
                ok=False,
                is_error=True,
                content=None,
                redacted_audit=base_audit,
                audit_id=audit_id,
                started=started,
            )

    def _result(
        self,
        *,
        ok: bool,
        is_error: bool,
        content: Any,
        redacted_audit: dict[str, Any],
        audit_id: str,
        started: float,
    ) -> MCPInvocationResult:
        latency_ms = round((time.monotonic() - started) * 1000, 3)
        redacted_audit["latency_ms"] = latency_ms
        return MCPInvocationResult(
            ok=ok,
            content=content,
            redacted_audit=redacted_audit,
            is_error=is_error,
            latency_ms=latency_ms,
            audit_id=audit_id,
        )

    def _base_audit(
        self,
        config: MCPServerConfig,
        request: MCPInvocationRequest,
        audit_id: str,
    ) -> dict[str, Any]:
        return {
            "audit_id": audit_id,
            "org_id": request.org_id,
            "user_id": request.user_id,
            "server": config.name,
            "capability_kind": request.capability_kind,
            "capability_name": request.capability_name,
            "arguments": redact_payload(request.arguments),
        }

    def _cap_content(self, value: Any, *, limit: int | None = None) -> str:
        cap = max(256, int(limit or self.max_content_chars))
        if isinstance(value, str):
            rendered = value
        else:
            rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        if len(rendered) <= cap:
            return rendered
        marker = "\n...[truncated by MCP cap]"
        return rendered[: cap - len(marker)] + marker

    @staticmethod
    def _audit_id(config: MCPServerConfig, request: MCPInvocationRequest) -> str:
        seed = "|".join(
            [
                str(time.time_ns()),
                config.name,
                request.server_name,
                request.capability_kind,
                request.capability_name,
                str(request.org_id),
                str(request.user_id),
            ]
        )
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
