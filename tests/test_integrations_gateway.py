"""Unit tests for the default-off CaseHub integrations gateway.

Covers policy, credential resolution, synthetic adapters, and the service
orchestration. These touch no network, no database, and no live provider, so
they run without the app stack:

    python -m pytest tests/test_integrations_gateway.py --noconftest
"""
from services.integrations_gateway import (
    DEFAULT_PROVIDER_CONFIGS,
    EnvCredentialStore,
    GatewayPolicy,
    GatewayProviderConfig,
    GatewayRequest,
    GatewayService,
    NullCredentialStore,
    SyntheticAdapter,
    build_provider_status,
    get_default_provider_configs,
)


def _provider(**kw):
    base = dict(
        name="google-calendar",
        enabled=True,
        allowed_operations=("status.read", "events.create"),
        mutating_operations=("events.create",),
    )
    base.update(kw)
    return GatewayProviderConfig(**base)


def _request(**kw):
    base = dict(
        org_id=1,
        user_id=1,
        provider_name="google-calendar",
        operation="status.read",
        requester_is_admin=True,
    )
    base.update(kw)
    return GatewayRequest(**base)


# --- policy ---------------------------------------------------------------

def test_policy_denies_disabled_provider():
    decision = GatewayPolicy().evaluate(_provider(enabled=False), _request())
    assert decision.allowed is False
    assert decision.reason == "provider_disabled"


def test_policy_denies_provider_mismatch():
    decision = GatewayPolicy().evaluate(_provider(), _request(provider_name="gmail"))
    assert decision.allowed is False
    assert decision.reason == "provider_mismatch"


def test_policy_requires_admin():
    decision = GatewayPolicy().evaluate(_provider(), _request(requester_is_admin=False))
    assert decision.allowed is False
    assert decision.reason == "admin_required"


def test_policy_denies_non_allowlisted_operation():
    decision = GatewayPolicy().evaluate(_provider(), _request(operation="events.delete"))
    assert decision.allowed is False
    assert decision.reason == "operation_not_allowlisted"


def test_policy_requires_idempotency_key_for_mutations():
    decision = GatewayPolicy().evaluate(_provider(), _request(operation="events.create"))
    assert decision.allowed is False
    assert decision.reason == "idempotency_required"


def test_policy_rejects_malformed_idempotency_key():
    decision = GatewayPolicy().evaluate(
        _provider(), _request(operation="events.create", idempotency_key="short")
    )
    assert decision.allowed is False
    assert decision.reason == "invalid_idempotency_key"


def test_policy_allows_mutation_with_valid_idempotency_key():
    decision = GatewayPolicy().evaluate(
        _provider(),
        _request(operation="events.create", idempotency_key="evt-create-20260521-0001"),
    )
    assert decision.allowed is True
    assert decision.approval_required is True


def test_policy_allows_allowlisted_read():
    decision = GatewayPolicy().evaluate(_provider(), _request())
    assert decision.allowed is True
    assert decision.reason == "allowed"


# --- build_provider_status ------------------------------------------------

def test_build_provider_status_hides_credential_ref():
    provider = _provider(credential_ref="env:GATEWAY_SUPER_SECRET_NAME")
    status = build_provider_status(provider)
    assert "credential_ref" not in status
    assert "GATEWAY_SUPER_SECRET_NAME" not in str(status)
    assert status["configured"] is True


def test_build_provider_status_redacts_last_error():
    status = build_provider_status(
        _provider(),
        last_error="token refresh failed: access_token=raw-leaked-token",
    )
    assert "raw-leaked-token" not in str(status)
    assert "<redacted>" in str(status["last_error"])


def test_default_registry_is_all_disabled():
    for provider in get_default_provider_configs():
        assert provider.enabled is False
        assert provider.credential_ref == ""
        status = build_provider_status(provider)
        assert status["status"] == "disabled"
        assert status["configured"] is False
    assert len(DEFAULT_PROVIDER_CONFIGS) == 3


# --- credential store -----------------------------------------------------

def test_null_store_resolves_nothing():
    resolved = NullCredentialStore().resolve("env:ANYTHING")
    assert resolved.present is False
    assert resolved.value is None


def test_env_store_resolves_present_ref():
    store = EnvCredentialStore(environ={"GATEWAY_TOKEN": "s3cr3t-value"})
    resolved = store.resolve("env:GATEWAY_TOKEN")
    assert resolved.present is True
    assert resolved.value == "s3cr3t-value"


def test_env_store_missing_ref_is_absent_not_error():
    resolved = EnvCredentialStore(environ={}).resolve("env:NOT_SET")
    assert resolved.present is False
    assert resolved.value is None


def test_env_store_ignores_non_env_backend():
    resolved = EnvCredentialStore(environ={"X": "y"}).resolve("vault:something")
    assert resolved.present is False


def test_env_store_empty_ref_is_absent():
    resolved = EnvCredentialStore(environ={}).resolve("")
    assert resolved.present is False


def test_resolved_credential_value_not_in_repr():
    store = EnvCredentialStore(environ={"GATEWAY_TOKEN": "top-secret-do-not-log"})
    resolved = store.resolve("env:GATEWAY_TOKEN")
    assert "top-secret-do-not-log" not in repr(resolved)
    assert "top-secret-do-not-log" not in str(resolved)


# --- synthetic adapter ----------------------------------------------------

def test_synthetic_adapter_returns_fixture():
    result = SyntheticAdapter("google-calendar").execute(_request(operation="events.read"))
    assert result.ok is True
    assert result.synthetic is True
    assert "events" in result.data


def test_synthetic_adapter_returns_deep_copied_fixture():
    first = SyntheticAdapter("google-calendar").execute(_request(operation="events.read"))
    second = SyntheticAdapter("google-calendar").execute(_request(operation="events.read"))
    first.data["events"].append({"id": "mutated"})
    assert second.data == {"events": [{"id": "synthetic-evt-1", "title": "Fixture event"}]}


def test_synthetic_adapter_unknown_operation():
    result = SyntheticAdapter("google-calendar").execute(_request(operation="events.purge"))
    assert result.ok is False
    assert result.error == "no_synthetic_fixture"


# --- service orchestration ------------------------------------------------

def test_service_blocks_on_policy_denial():
    result, decision = GatewayService().execute(_provider(enabled=False), _request())
    assert decision.allowed is False
    assert result.ok is False
    assert result.error == "provider_disabled"


def test_service_blocks_missing_credentials_before_adapter():
    result, decision = GatewayService().execute(_provider(), _request())
    assert decision.allowed is True
    assert result.ok is False
    assert result.error == "credential_missing"


def test_service_runs_synthetic_adapter_when_allowed():
    service = GatewayService(
        credential_store=EnvCredentialStore(environ={"GATEWAY_TOKEN": "synthetic-token"})
    )
    result, decision = service.execute(
        _provider(credential_ref="env:GATEWAY_TOKEN"), _request()
    )
    assert decision.allowed is True
    assert result.ok is True
    assert result.synthetic is True


def test_service_uses_null_credential_store_by_default():
    assert isinstance(GatewayService().credential_store, NullCredentialStore)


def test_audit_summary_is_body_free_and_redacted():
    service = GatewayService(
        credential_store=EnvCredentialStore(environ={"GATEWAY_TOKEN": "synthetic-token"})
    )
    request = _request(
        operation="events.create",
        idempotency_key="evt-create-20260521-0002",
        payload={"authorization": "Bearer raw-secret-token", "title": "Client meeting"},
    )
    provider = _provider(credential_ref="env:GATEWAY_TOKEN")
    result, decision = service.execute(provider, request)
    summary = service.audit_summary(provider, request, result, decision)
    serialized = str(summary)
    # operation payload bodies must never reach the audit summary
    assert "raw-secret-token" not in serialized
    assert "Client meeting" not in serialized
    assert summary["provider"] == "google-calendar"
    assert summary["operation"] == "events.create"
    assert summary["idempotency_key_present"] is True
    assert "payload" not in summary
