"""Default-off orchestration for the integrations gateway.

:class:`GatewayService` wires policy -> credential resolution -> adapter ->
audit summary. With the default synthetic adapter and null credential store it
makes no network calls and writes nothing to any provider system. Promoting it
to live provider calls is a separate, Council-gated slice.
"""
from __future__ import annotations

from typing import Callable, Optional

from services.mcp_client import redact_payload

from .adapters import GatewayAdapter, SyntheticAdapter
from .credentials import CredentialStore, NullCredentialStore
from .policy import GatewayPolicy, GatewayPolicyDecision
from .types import GatewayProviderConfig, GatewayRequest, GatewayResult

AdapterFactory = Callable[[GatewayProviderConfig], GatewayAdapter]


def _default_adapter_factory(provider: GatewayProviderConfig) -> GatewayAdapter:
    return SyntheticAdapter(provider.name)


class GatewayService:
    """Policy-gated execution path for gateway operations.

    Defaults keep the gateway inert: a :class:`NullCredentialStore` resolves no
    secrets and a :class:`SyntheticAdapter` performs no I/O. Tests and a future
    live slice can inject their own policy, store, or adapter factory.
    """

    def __init__(
        self,
        *,
        policy: Optional[GatewayPolicy] = None,
        credential_store: Optional[CredentialStore] = None,
        adapter_factory: Optional[AdapterFactory] = None,
    ):
        self.policy = policy or GatewayPolicy()
        self.credential_store = credential_store or NullCredentialStore()
        self._adapter_factory = adapter_factory or _default_adapter_factory

    def execute(
        self, provider: GatewayProviderConfig, request: GatewayRequest
    ) -> tuple[GatewayResult, GatewayPolicyDecision]:
        """Evaluate policy, then run the adapter.

        A denied policy decision short-circuits before any adapter is built or
        any credential is resolved.
        """
        decision = self.policy.evaluate(provider, request)
        if not decision.allowed:
            return (
                GatewayResult(
                    ok=False,
                    provider_name=provider.name,
                    operation=request.operation,
                    synthetic=True,
                    error=decision.reason,
                ),
                decision,
            )
        credential = self.credential_store.resolve(provider.credential_ref)
        if not credential.present:
            return (
                GatewayResult(
                    ok=False,
                    provider_name=provider.name,
                    operation=request.operation,
                    synthetic=True,
                    error="credential_missing",
                ),
                decision,
            )
        adapter = self._adapter_factory(provider)
        return adapter.execute(request), decision

    def audit_summary(
        self,
        provider: GatewayProviderConfig,
        request: GatewayRequest,
        result: GatewayResult,
        decision: GatewayPolicyDecision,
    ) -> dict:
        """Body-free, redacted summary safe to store in ``audit_log.details``.

        Deliberately omits operation payloads, provider responses, and
        credential refs. The remaining fields are passed through
        :func:`redact_payload` as defense-in-depth.
        """
        return redact_payload(
            {
                "provider": provider.name,
                "operation": request.operation,
                "allowed": decision.allowed,
                "reason": decision.reason,
                "approval_required": decision.approval_required,
                "synthetic": result.synthetic,
                "ok": result.ok,
                "error": result.error,
                "idempotency_key_present": bool(request.idempotency_key),
                "org_id": request.org_id,
            }
        )
