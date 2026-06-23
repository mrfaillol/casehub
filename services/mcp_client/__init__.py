"""Default-off internal MCP client facade for CaseHub.

This package intentionally contains no production activation code. It provides
policy and redaction primitives that can be tested before any real MCP server is
connected.
"""

from .client import MCPAdapterUnavailable, MCPClient
from .policy import MCPPolicy, PolicyDecision
from .redaction import redact_payload, redact_text
from .types import MCPInvocationRequest, MCPInvocationResult, MCPServerConfig

__all__ = [
    "MCPAdapterUnavailable",
    "MCPClient",
    "MCPInvocationRequest",
    "MCPInvocationResult",
    "MCPPolicy",
    "MCPServerConfig",
    "PolicyDecision",
    "redact_payload",
    "redact_text",
]
