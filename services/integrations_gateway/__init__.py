"""Default-off CaseHub-owned integrations gateway primitives.

This package is a local contract layer plus a synthetic execution path. It
does not connect to Google Workspace, Gmail, Drive, or any MCP server by
itself: the only adapter shipped is :class:`SyntheticAdapter`, the default
credential store is :class:`NullCredentialStore`, and every registry provider
is disabled. Promoting any provider to a live call is a Council-gated slice.
"""

from .adapters import GatewayAdapter, SyntheticAdapter
from .credentials import (
    CredentialStore,
    EnvCredentialStore,
    NullCredentialStore,
    ResolvedCredential,
)
from .policy import GatewayPolicy, GatewayPolicyDecision, build_provider_status
from .registry import DEFAULT_PROVIDER_CONFIGS, get_default_provider_configs
from .service import GatewayService
from .types import (
    GatewayProviderConfig,
    GatewayProviderStatus,
    GatewayRequest,
    GatewayResult,
)

__all__ = [
    "DEFAULT_PROVIDER_CONFIGS",
    "CredentialStore",
    "EnvCredentialStore",
    "GatewayAdapter",
    "GatewayPolicy",
    "GatewayPolicyDecision",
    "GatewayProviderConfig",
    "GatewayProviderStatus",
    "GatewayRequest",
    "GatewayResult",
    "GatewayService",
    "NullCredentialStore",
    "ResolvedCredential",
    "SyntheticAdapter",
    "build_provider_status",
    "get_default_provider_configs",
]
