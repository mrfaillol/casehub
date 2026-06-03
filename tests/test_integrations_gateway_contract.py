from services.integrations_gateway import (
    GatewayPolicy,
    GatewayProviderConfig,
    GatewayRequest,
    build_provider_status,
    get_default_provider_configs,
)


def _request(
    operation="events.create",
    *,
    provider_name="google-calendar",
    requester_is_admin=False,
    idempotency_key="casehub-test-001",
):
    return GatewayRequest(
        org_id=1,
        user_id=1,
        provider_name=provider_name,
        operation=operation,
        payload={"title": "Hearing"},
        idempotency_key=idempotency_key,
        requester_is_admin=requester_is_admin,
    )


def test_gateway_defaults_are_disabled():
    providers = get_default_provider_configs()

    assert {provider.name for provider in providers} == {
        "google-calendar",
        "gmail",
        "google-drive",
    }
    assert all(provider.enabled is False for provider in providers)


def test_gateway_policy_denies_disabled_provider():
    provider = GatewayProviderConfig(
        name="google-calendar",
        allowed_operations=("events.create",),
        mutating_operations=("events.create",),
    )

    decision = GatewayPolicy().evaluate(
        provider,
        _request(requester_is_admin=True),
    )

    assert decision.allowed is False
    assert decision.reason == "provider_disabled"


def test_gateway_policy_requires_admin_for_enabled_provider():
    provider = GatewayProviderConfig(
        name="google-calendar",
        enabled=True,
        allowed_operations=("events.create",),
        mutating_operations=("events.create",),
    )

    decision = GatewayPolicy().evaluate(provider, _request())

    assert decision.allowed is False
    assert decision.reason == "admin_required"


def test_gateway_policy_allows_only_allowlisted_operations():
    provider = GatewayProviderConfig(
        name="google-calendar",
        enabled=True,
        allowed_operations=("events.create",),
        mutating_operations=("events.create",),
    )

    allowed = GatewayPolicy().evaluate(
        provider,
        _request(requester_is_admin=True),
    )
    blocked = GatewayPolicy().evaluate(
        provider,
        _request(operation="gmail.threads.search", requester_is_admin=True),
    )

    assert allowed.allowed is True
    assert allowed.approval_required is True
    assert blocked.allowed is False
    assert blocked.reason == "operation_not_allowlisted"


def test_gateway_policy_requires_idempotency_for_mutating_operations():
    provider = GatewayProviderConfig(
        name="google-calendar",
        enabled=True,
        allowed_operations=("events.create",),
        mutating_operations=("events.create",),
    )

    missing = GatewayPolicy().evaluate(
        provider,
        _request(requester_is_admin=True, idempotency_key=""),
    )
    invalid = GatewayPolicy().evaluate(
        provider,
        _request(requester_is_admin=True, idempotency_key="bad key"),
    )

    assert missing.reason == "idempotency_required"
    assert invalid.reason == "invalid_idempotency_key"


def test_gateway_policy_does_not_require_idempotency_for_read_operations():
    provider = GatewayProviderConfig(
        name="gmail",
        enabled=True,
        allowed_operations=("threads.search",),
        mutating_operations=(),
    )

    decision = GatewayPolicy().evaluate(
        provider,
        _request(
            provider_name="gmail",
            operation="threads.search",
            requester_is_admin=True,
            idempotency_key="",
        ),
    )

    assert decision.allowed is True


def test_provider_status_is_sanitized_and_hides_credential_ref():
    token_value = "sample-token-value"
    credential_value = "sample-credential-value"
    provider = GatewayProviderConfig(
        name="google-drive",
        enabled=True,
        credential_ref="runtime/google-drive/oauth",
        allowed_operations=("files.search",),
    )

    status = build_provider_status(
        provider,
        last_error={
            "message": "Authorization: " + "Bearer " + token_value,
            "nested": {"client_" + "secret": credential_value},
        },
    )
    rendered = str(status)

    assert status["configured"] is True
    assert "credential_ref" not in status
    assert "runtime/google-drive/oauth" not in rendered
    assert token_value not in rendered
    assert credential_value not in rendered
    assert "<redacted>" in rendered
