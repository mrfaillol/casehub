from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

from .types import MCPInvocationRequest, MCPServerConfig


BLOCKED_HOSTS = {
    "localhost",
    "metadata.google.internal",
    "metadata.aws.internal",
    "169.254.169.254",
    "kubernetes.default.svc",
}
BLOCKED_SCHEMES = {"file", "ftp", "gopher", "ssh", "sftp"}
ALLOWED_KINDS = {"tool", "resource", "prompt"}


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    approval_required: bool = False


class MCPPolicy:
    """Default-deny policy for future MCP client calls."""

    def evaluate(self, server: MCPServerConfig, request: MCPInvocationRequest) -> PolicyDecision:
        if not server.enabled:
            return PolicyDecision(False, "server_disabled")
        if request.server_name != server.name:
            return PolicyDecision(False, "server_mismatch")
        if server.admin_only and not request.requester_is_admin:
            return PolicyDecision(False, "admin_required")
        if request.capability_kind not in ALLOWED_KINDS:
            return PolicyDecision(False, "unknown_capability_kind")

        network_decision = self._network_allowed(server.url)
        if not network_decision.allowed:
            return network_decision

        allowed = {
            "tool": server.allowed_tools,
            "resource": server.allowed_resources,
            "prompt": server.allowed_prompts,
        }[request.capability_kind]
        if request.capability_name not in allowed:
            return PolicyDecision(False, "capability_not_allowlisted")

        return PolicyDecision(True, "allowed", approval_required=server.approval_required)

    def _network_allowed(self, url: str) -> PolicyDecision:
        parsed = urlparse(url)
        if parsed.scheme in BLOCKED_SCHEMES:
            return PolicyDecision(False, "blocked_scheme")
        if parsed.scheme not in {"http", "https"}:
            return PolicyDecision(False, "unsupported_scheme")
        host = (parsed.hostname or "").lower()
        if not host:
            return PolicyDecision(False, "missing_host")
        if host in BLOCKED_HOSTS or host.endswith(".local"):
            return PolicyDecision(False, "blocked_host")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            resolved_addresses = self._resolve_host_addresses(host)
            if resolved_addresses is not None:
                for resolved in resolved_addresses:
                    if not resolved.is_global:
                        return PolicyDecision(False, "blocked_private_address")
            return PolicyDecision(True, "network_allowed")
        if not address.is_global:
            return PolicyDecision(False, "blocked_private_address")
        return PolicyDecision(True, "network_allowed")

    @staticmethod
    def _resolve_host_addresses(host: str) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address] | None:
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except OSError:
            return None

        addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
        for _family, _socktype, _proto, _canonname, sockaddr in infos:
            if not sockaddr:
                continue
            ip_value = sockaddr[0]
            try:
                addresses.add(ipaddress.ip_address(ip_value))
            except ValueError:
                continue
        return addresses
