from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GatewayProviderConfig:
    """Tenant-scoped provider definition for the future gateway.

    `credential_ref` is a pointer to a runtime store, never a raw credential.
    """

    name: str
    enabled: bool = False
    credential_ref: str = ""
    allowed_operations: tuple[str, ...] = field(default_factory=tuple)
    mutating_operations: tuple[str, ...] = field(default_factory=tuple)
    timeout_seconds: float = 8.0
    rate_limit_per_minute: int = 30
    approval_required: bool = True
    admin_only: bool = True


@dataclass(frozen=True)
class GatewayRequest:
    org_id: int
    user_id: int
    provider_name: str
    operation: str
    payload: dict[str, Any] = field(default_factory=dict, repr=False)
    idempotency_key: str = ""
    requester_is_admin: bool = False


@dataclass(frozen=True)
class GatewayProviderStatus:
    provider_name: str
    enabled: bool
    configured: bool
    allowed_operations: tuple[str, ...]
    approval_required: bool
    status: str
    last_error: Any = None


@dataclass(frozen=True)
class GatewayResult:
    """Outcome of a gateway operation.

    v0 only ever produces synthetic results. `data` carries already-sanitized
    synthetic fixture content; `error` is a short machine code, never a raw
    provider response body.
    """

    ok: bool
    provider_name: str
    operation: str
    synthetic: bool = True
    data: Any = None
    error: str = ""
