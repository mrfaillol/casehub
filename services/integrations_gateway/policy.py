import re
from dataclasses import asdict, dataclass
from typing import Any

from services.mcp_client import redact_payload

from .types import GatewayProviderConfig, GatewayProviderStatus, GatewayRequest


IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


@dataclass(frozen=True)
class GatewayPolicyDecision:
    allowed: bool
    reason: str
    approval_required: bool = False


class GatewayPolicy:
    """Default-deny policy for future CaseHub-owned gateway calls."""

    def evaluate(
        self,
        provider: GatewayProviderConfig,
        request: GatewayRequest,
    ) -> GatewayPolicyDecision:
        if not provider.enabled:
            return GatewayPolicyDecision(False, "provider_disabled")
        if request.provider_name != provider.name:
            return GatewayPolicyDecision(False, "provider_mismatch")
        if provider.admin_only and not request.requester_is_admin:
            return GatewayPolicyDecision(False, "admin_required")
        if request.operation not in provider.allowed_operations:
            return GatewayPolicyDecision(False, "operation_not_allowlisted")
        if request.operation in provider.mutating_operations:
            if not request.idempotency_key:
                return GatewayPolicyDecision(False, "idempotency_required")
            if not IDEMPOTENCY_KEY_RE.match(request.idempotency_key):
                return GatewayPolicyDecision(False, "invalid_idempotency_key")
        return GatewayPolicyDecision(
            True,
            "allowed",
            approval_required=provider.approval_required,
        )


def build_provider_status(
    provider: GatewayProviderConfig,
    *,
    last_error: Any = None,
) -> dict[str, Any]:
    """Return sanitized status suitable for admin diagnostics."""

    status = GatewayProviderStatus(
        provider_name=provider.name,
        enabled=provider.enabled,
        configured=bool(provider.credential_ref),
        allowed_operations=provider.allowed_operations,
        approval_required=provider.approval_required,
        status="enabled" if provider.enabled else "disabled",
        last_error=redact_payload(str(last_error) if last_error and not isinstance(last_error, (str, dict, list, tuple)) else last_error),
    )
    return asdict(status)
