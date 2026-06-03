import socket

from services.mcp_client import MCPInvocationRequest, MCPPolicy, MCPServerConfig, redact_payload


def _request(kind="tool", name="calendar.create_event", requester_is_admin=False):
    return MCPInvocationRequest(
        org_id=1,
        user_id=1,
        server_name="office-gateway",
        capability_kind=kind,
        capability_name=name,
        requester_is_admin=requester_is_admin,
        arguments={"title": "Test"},
    )


def test_mcp_policy_is_default_deny():
    server = MCPServerConfig(
        name="office-gateway",
        url="https://integrations.example.invalid/mcp",
        allowed_tools=("calendar.create_event",),
    )

    decision = MCPPolicy().evaluate(server, _request())

    assert decision.allowed is False
    assert decision.reason == "server_disabled"


def test_mcp_policy_allows_only_allowlisted_capability():
    server = MCPServerConfig(
        name="office-gateway",
        url="https://integrations.example.invalid/mcp",
        enabled=True,
        allowed_tools=("calendar.create_event",),
    )

    allowed = MCPPolicy().evaluate(server, _request(requester_is_admin=True))
    blocked = MCPPolicy().evaluate(server, _request(name="gmail.search", requester_is_admin=True))

    assert allowed.allowed is True
    assert allowed.approval_required is True
    assert blocked.allowed is False
    assert blocked.reason == "capability_not_allowlisted"


def test_mcp_policy_requires_admin_for_enabled_servers():
    server = MCPServerConfig(
        name="office-gateway",
        url="https://integrations.example.invalid/mcp",
        enabled=True,
        allowed_tools=("calendar.create_event",),
    )

    decision = MCPPolicy().evaluate(server, _request())

    assert decision.allowed is False
    assert decision.reason == "admin_required"


def test_mcp_policy_blocks_private_network_targets():
    server = MCPServerConfig(
        name="office-gateway",
        url="http://127.0.0.1:8000/mcp",
        enabled=True,
        allowed_tools=("calendar.create_event",),
    )

    decision = MCPPolicy().evaluate(server, _request(requester_is_admin=True))

    assert decision.allowed is False
    assert decision.reason == "blocked_private_address"


def test_mcp_policy_blocks_non_global_literal_ip_targets():
    server = MCPServerConfig(
        name="office-gateway",
        url="http://0.0.0.0:8000/mcp",
        enabled=True,
        allowed_tools=("calendar.create_event",),
    )

    decision = MCPPolicy().evaluate(server, _request(requester_is_admin=True))

    assert decision.allowed is False
    assert decision.reason == "blocked_private_address"


def test_mcp_policy_blocks_hostname_when_dns_resolves_to_private_ip(monkeypatch):
    def _fake_getaddrinfo(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.20", 443))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    server = MCPServerConfig(
        name="office-gateway",
        url="https://integrations.example.invalid/mcp",
        enabled=True,
        allowed_tools=("calendar.create_event",),
    )

    decision = MCPPolicy().evaluate(server, _request(requester_is_admin=True))

    assert decision.allowed is False
    assert decision.reason == "blocked_private_address"


def test_mcp_policy_allows_hostname_when_dns_resolution_fails(monkeypatch):
    def _fake_getaddrinfo(*_args, **_kwargs):
        raise socket.gaierror("resolution failed")

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    server = MCPServerConfig(
        name="office-gateway",
        url="https://integrations.example.invalid/mcp",
        enabled=True,
        allowed_tools=("calendar.create_event",),
    )

    decision = MCPPolicy().evaluate(server, _request(requester_is_admin=True))

    assert decision.allowed is True
    assert decision.reason == "allowed"


def test_mcp_policy_blocks_known_metadata_hosts_and_file_scheme():
    policy = MCPPolicy()

    metadata = MCPServerConfig(
        name="office-gateway",
        url="https://metadata.aws.internal/latest/meta-data",
        enabled=True,
        allowed_tools=("calendar.create_event",),
    )
    file_url = MCPServerConfig(
        name="office-gateway",
        url="file:///etc/passwd",
        enabled=True,
        allowed_tools=("calendar.create_event",),
    )

    assert policy.evaluate(metadata, _request(requester_is_admin=True)).reason == "blocked_host"
    assert policy.evaluate(file_url, _request(requester_is_admin=True)).reason == "blocked_scheme"


def test_mcp_redaction_removes_secrets_recursively():
    payload = {
        "Authorization": "Bearer abc.def.ghi",
        "nested": {
            "client_secret": "super-secret",
            "error": "client_secret=s3c access_token=tok",
        },
        "items": [{"api_key": "raw-key"}, "Bearer another-token"],
    }

    redacted = redact_payload(payload)
    serialized = str(redacted)

    assert "super-secret" not in serialized
    assert "s3c" not in serialized
    assert "access_token=tok" not in serialized
    assert "another-token" not in serialized
    assert "raw-key" not in serialized
    assert "<redacted>" in serialized


def test_mcp_redaction_handles_group_and_group_free_token_patterns():
    text = (
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789== "
        "Authorization: Basic dXNlcjpwYXNz "
        "Authorization: Token raw-django-token "
        "Authorization: ApiKey user:raw-api-secret "
        "Authorization: Digest raw-digest-secret "
        "jwt=eyJabc.eyJdef.sig "
        "cpf 123.456.789-10 cnpj 12.345.678/0001-99 oab OAB/SP 123456 "
        "https://example.invalid/callback?access_token=raw-token==&client_secret=raw-secret"
    )

    redacted = redact_payload({"error": text})
    serialized = str(redacted)

    assert "abcdefghijklmnopqrstuvwxyz0123456789" not in serialized
    assert "dXNlcjpwYXNz" not in serialized
    assert "raw-django-token" not in serialized
    assert "raw-api-secret" not in serialized
    assert "raw-digest-secret" not in serialized
    assert "123.456.789-10" not in serialized
    assert "12.345.678/0001-99" not in serialized
    assert "OAB/SP 123456" not in serialized
    assert "raw-token" not in serialized
    assert "raw-secret" not in serialized
    assert "access_token=<redacted>" in serialized
    assert "client_secret=<redacted>" in serialized


def test_mcp_redaction_preserves_mapping_keys_and_tuple_sequences():
    payload = {
        99: ("visible", "Bearer abcdefghijklmnopqrstuvwxyz0123456789=="),
        "nested": {"api_key": "raw-key"},
    }

    redacted = redact_payload(payload)

    assert 99 in redacted
    assert isinstance(redacted[99], tuple)
    assert redacted[99] == ("visible", "<redacted>")
    assert redacted["nested"]["api_key"] == "<redacted>"


def test_mcp_redaction_preserves_set_and_frozenset_sequences():
    payload = {
        "set_values": {"Bearer abcdefghijklmnopqrstuvwxyz0123456789==", "visible"},
        "frozen_values": frozenset({"ApiKey raw-key", "visible"}),
    }

    redacted = redact_payload(payload)

    assert isinstance(redacted["set_values"], set)
    assert isinstance(redacted["frozen_values"], frozenset)
    assert "<redacted>" in redacted["set_values"]
    assert "<redacted>" in redacted["frozen_values"]
    assert all("raw-key" not in item for item in redacted["frozen_values"])


def test_mcp_invocation_repr_does_not_expose_arguments():
    request = _request(requester_is_admin=True)

    rendered = repr(request)

    assert "arguments" not in rendered
    assert "Test" not in rendered
