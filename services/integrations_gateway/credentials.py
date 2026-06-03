"""Runtime credential-reference resolution for the integrations gateway.

A ``credential_ref`` is a non-secret pointer of the form ``<backend>:<name>``
(e.g. ``env:GATEWAY_GCAL_TOKEN``). The ref is safe to commit and to show in
admin diagnostics; the resolved secret value is not, and must never be logged,
serialized into audit rows, or returned over HTTP.

v0 ships only the env-var and null backends. Both keep secrets out of Git and
reuse CaseHub's existing env-based configuration, so they add no new secret
topology. Any richer backend (OS keychain, file mount at a new path, external
secret manager) changes where secrets physically live and is a Council-gated
decision before it is wired to a real credential.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ResolvedCredential:
    """Result of resolving a credential_ref.

    `value` is excluded from ``repr`` so the secret never leaks into logs,
    tracebacks, or audit rows. `present` is the safe boolean to expose.
    """

    ref: str
    backend: str
    present: bool
    value: Optional[str] = field(default=None, repr=False, compare=False)


class CredentialStore:
    """Base contract for credential stores.

    `resolve` maps a credential_ref to a :class:`ResolvedCredential` and never
    raises for an unknown or missing ref — it returns ``present=False``.
    """

    def resolve(self, credential_ref: str) -> ResolvedCredential:
        raise NotImplementedError


def _split_ref(credential_ref: str) -> tuple[str, str]:
    ref = (credential_ref or "").strip()
    backend, _, name = ref.partition(":")
    return backend.strip().lower(), name.strip()


class NullCredentialStore(CredentialStore):
    """Resolves nothing. Default store while every provider is disabled."""

    def resolve(self, credential_ref: str) -> ResolvedCredential:
        backend, _ = _split_ref(credential_ref)
        return ResolvedCredential(ref=credential_ref or "", backend=backend, present=False)


class EnvCredentialStore(CredentialStore):
    """Resolves ``env:NAME`` refs against process environment variables.

    Reuses CaseHub's existing env-based secret pattern, so it introduces no new
    secret-storage topology. Non-``env:`` refs (and empty refs) resolve to
    ``present=False`` rather than raising.
    """

    def __init__(self, environ: Optional[dict] = None):
        self._environ = environ if environ is not None else os.environ

    def resolve(self, credential_ref: str) -> ResolvedCredential:
        backend, name = _split_ref(credential_ref)
        if backend != "env" or not name:
            return ResolvedCredential(
                ref=credential_ref or "", backend=backend, present=False
            )
        value = self._environ.get(name)
        return ResolvedCredential(
            ref=credential_ref,
            backend="env",
            present=bool(value),
            value=value or None,
        )
