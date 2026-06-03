from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MCPServerConfig:
    """Organization-scoped MCP server definition.

    `secret_ref` is a pointer to a runtime secret store. It must never contain
    the raw secret value.
    """

    name: str
    url: str
    enabled: bool = False
    auth_mode: str = "none"
    secret_ref: str = ""
    allowed_tools: tuple[str, ...] = field(default_factory=tuple)
    allowed_resources: tuple[str, ...] = field(default_factory=tuple)
    allowed_prompts: tuple[str, ...] = field(default_factory=tuple)
    timeout_seconds: float = 8.0
    rate_limit_per_minute: int = 30
    approval_required: bool = True
    admin_only: bool = True


@dataclass(frozen=True)
class MCPInvocationRequest:
    org_id: int
    user_id: int
    server_name: str
    capability_kind: str
    capability_name: str
    arguments: dict[str, Any] = field(default_factory=dict, repr=False)
    requester_is_admin: bool = False
