"""Regression tests for IDOR C5 — X-Org-Id tenant impersonation.

Council ruling: agents/knowledge/council/rulings/2026-05-29-idor-c5-xorgid-root.json
Sentinela audit: agents/knowledge/sentinela/audits/2026-05-29-idor-cluster.md

Root cause (historical, SHA 99990d69): TenantMiddleware Strategy 1 resolved the
tenant from a caller-supplied ``X-Org-Id`` header BEFORE Host/JWT and with a raw
``int()`` (no try/except). Any authenticated cookie holder could set
``X-Org-Id: <other_org>`` and make ``request.state.org_id`` point at a tenant
they do not belong to, turning every route that trusts ``request.state.org_id``
into a cross-tenant IDOR.

The header strategy was removed from the general dispatch (commit 363efdbb,
"Sentinela T1 fix") and ``auth._enforce_tenant_binding`` now reconciles the
JWT-bound ``user.org_id`` with ``request.state.org_id``. These tests lock both
defenses in so the regression cannot silently come back.

Coverage:
  1. NEGATIVE  — org-A user with a resolved tenant of org B is rejected (403).
                 This is the spoof outcome: even if something set
                 request.state.org_id to the attacker's chosen org, the JWT
                 binding refuses it.
  2. DEPTH     — an unscoped account (user.org_id IS NULL) on a resolved tenant
                 is rejected (IDOR C5 defense-in-depth, condition 4).
  3. POSITIVE  — matching tenant passes; superadmin pivot passes; bootstrap
                 (no tenant context) passes.
  4. MIDDLEWARE— X-Org-Id is NOT honored in the general dispatch (no internal
                 IPs configured); tenant identity derives from Host/JWT.
  5. HARDENING — the (gated) internal X-Org-Id parser tolerates a non-numeric
                 value instead of raising ValueError (no 500 / DoS).

The WhatsApp server-to-server path (proxy overwrites X-Org-Id; inbound reads it
only after HMAC) is exercised separately in tests/test_whatsapp_multi_tenant.py.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _user(org_id, user_type="admin", role="admin", email="user@test.com"):
    """Lightweight stand-in for the User ORM object."""
    return SimpleNamespace(
        org_id=org_id,
        user_type=user_type,
        role=role,
        email=email,
    )


def _request(state_org_id, host="tenanta.casehub.legal", path="/cases"):
    """Mock Request carrying a resolved tenant in request.state.org_id."""
    req = MagicMock()
    req.state = SimpleNamespace(org_id=state_org_id)
    req.headers = {"host": host}
    req.url = SimpleNamespace(path=path)
    return req


# --------------------------------------------------------------------------- #
# 1. NEGATIVE — the IDOR primitive is dead
# --------------------------------------------------------------------------- #
class TestTenantMismatchRejected:
    def test_org_a_user_with_org_b_context_is_rejected(self):
        """Org-A user, resolved tenant = org B -> 403 Tenant mismatch.

        This is the exact spoof outcome the C5 fix must block.
        """
        from auth import _enforce_tenant_binding

        user = _user(org_id=1)  # belongs to org A (id=1)
        req = _request(state_org_id=2)  # resolved/spoofed tenant = org B (id=2)
        payload = {"sub": user.email, "org_id": 1}

        with pytest.raises(HTTPException) as exc:
            _enforce_tenant_binding(req, user, payload)
        assert exc.value.status_code == 403
        assert "mismatch" in exc.value.detail.lower()

    def test_org_b_user_with_org_a_context_is_rejected(self):
        """Symmetric case — direction does not matter."""
        from auth import _enforce_tenant_binding

        user = _user(org_id=2)
        req = _request(state_org_id=1)
        payload = {"sub": user.email, "org_id": 2}

        with pytest.raises(HTTPException) as exc:
            _enforce_tenant_binding(req, user, payload)
        assert exc.value.status_code == 403


# --------------------------------------------------------------------------- #
# 2. DEPTH — unscoped admin cannot inherit a resolved tenant
# --------------------------------------------------------------------------- #
class TestUnscopedAdminRejected:
    def test_null_org_user_on_resolved_tenant_is_rejected(self):
        """user.org_id IS NULL + a concrete resolved tenant -> 403.

        Generalises routes/improvement_tasks.py:209-211 to the auth chokepoint
        (council ruling condition 4). The legacy startup/migration admin must
        not become a cross-tenant view.
        """
        from auth import _enforce_tenant_binding

        user = _user(org_id=None)  # legacy admin, not scoped to any org
        req = _request(state_org_id=2)  # request resolved to a real tenant
        payload = {"sub": user.email, "org_id": None}

        with pytest.raises(HTTPException) as exc:
            _enforce_tenant_binding(req, user, payload)
        assert exc.value.status_code == 403
        assert "organization" in exc.value.detail.lower()

    def test_null_org_user_without_tenant_context_is_allowed(self):
        """Bootstrap safety: no resolved tenant (single-tenant / setup) ->
        the unscoped guard must NOT fire, or a fresh install can't be set up."""
        from auth import _enforce_tenant_binding

        user = _user(org_id=None)
        req = _request(state_org_id=None)  # nothing resolved yet
        payload = {"sub": user.email, "org_id": None}

        # Must not raise.
        assert _enforce_tenant_binding(req, user, payload) is user


# --------------------------------------------------------------------------- #
# 3. POSITIVE — legitimate sessions keep working
# --------------------------------------------------------------------------- #
class TestLegitimateSessionsPass:
    def test_matching_tenant_passes(self):
        from auth import _enforce_tenant_binding

        user = _user(org_id=4)
        req = _request(state_org_id=4)
        payload = {"sub": user.email, "org_id": 4}

        assert _enforce_tenant_binding(req, user, payload) is user

    def test_superadmin_can_pivot_across_tenants(self):
        """Superadmins intentionally cross tenants (impersonation) -> allowed."""
        from auth import _enforce_tenant_binding

        user = _user(org_id=1, user_type="superadmin", role="superadmin")
        req = _request(state_org_id=2)
        payload = {"sub": user.email, "org_id": 1}

        assert _enforce_tenant_binding(req, user, payload) is user

    def test_none_user_returns_none(self):
        from auth import _enforce_tenant_binding

        req = _request(state_org_id=1)
        assert _enforce_tenant_binding(req, None, {"org_id": 1}) is None


# --------------------------------------------------------------------------- #
# 4. MIDDLEWARE — X-Org-Id is not honored in the general dispatch
# --------------------------------------------------------------------------- #
class TestMiddlewareIgnoresClientHeader:
    def test_no_xorgid_strategy_in_general_dispatch(self):
        """The middleware source must not resolve tenant from a client X-Org-Id
        in the general (non-internal-IP) path. Strategy 0 is gated behind
        CASEHUB_INTERNAL_IPS; identity derives from Host then JWT."""
        import inspect
        from middleware.tenant import TenantMiddleware

        src = inspect.getsource(TenantMiddleware._resolve_org)
        # X-Org-Id may only be read inside the internal-IP guarded block.
        assert "self._internal_ips" in src, (
            "X-Org-Id handling must be gated by the internal-IP allowlist"
        )
        # Host/subdomain and JWT must remain the authoritative strategies.
        assert "get('host'" in src or 'get("host"' in src
        assert "casehub_token" in src

    def test_xorgid_disabled_by_default(self):
        """With no CASEHUB_INTERNAL_IPS configured, the internal X-Org-Id branch
        is inert — a client header can never resolve a tenant."""
        mw = _build_middleware(internal_ips="")
        assert mw._internal_ips == set()

    def test_client_xorgid_ignored_resolves_via_host(self, monkeypatch):
        """End-to-end on _resolve_org: a spoofed X-Org-Id is ignored and the
        tenant resolves from the Host header instead."""
        mw = _build_middleware(internal_ips="")

        # Host tenanta -> org 4; the spoofed header points at org 99.
        def fake_by_domain(domain):
            return None

        def fake_by_slug(slug):
            return {"id": 4, "slug": "tenanta", "is_active": True} if slug == "tenanta" else None

        monkeypatch.setattr(mw, "_get_org_by_domain", fake_by_domain)
        monkeypatch.setattr(mw, "_get_org_by_slug", fake_by_slug)

        req = MagicMock()
        req.headers = {"host": "tenanta.casehub.legal", "X-Org-Id": "99"}
        req.client = SimpleNamespace(host="203.0.113.7")  # external IP
        req.cookies = {}

        org = _run_async(mw._resolve_org(req))
        assert org["id"] == 4, "tenant must come from Host, never the X-Org-Id header"


# --------------------------------------------------------------------------- #
# 5. HARDENING — internal X-Org-Id parser never raises on bad input
# --------------------------------------------------------------------------- #
class TestParserHardening:
    def test_internal_xorgid_non_numeric_does_not_raise(self, monkeypatch):
        """Even on the (gated) internal path, a non-numeric X-Org-Id must be
        swallowed (logged) — never propagate ValueError -> HTTP 500 / DoS."""
        mw = _build_middleware(internal_ips="10.0.0.5")

        # Fall through after the bad header so _resolve_org still completes.
        monkeypatch.setattr(mw, "_get_org_by_domain", lambda d: None)
        monkeypatch.setattr(mw, "_get_org_by_slug", lambda s: {"id": 1, "slug": s, "is_active": True})

        req = MagicMock()
        req.headers = {"host": "default.casehub.legal", "X-Org-Id": "not-an-int"}
        req.client = SimpleNamespace(host="10.0.0.5")  # internal peer
        req.cookies = {}

        # Must not raise; resolution continues to the next strategy.
        org = _run_async(mw._resolve_org(req))
        assert org is not None


# --------------------------------------------------------------------------- #
# Local async/middleware helpers (kept at module end for readability)
# --------------------------------------------------------------------------- #
def _build_middleware(internal_ips: str):
    import os
    from unittest.mock import patch
    from middleware.tenant import TenantMiddleware

    with patch.dict(os.environ, {"CASEHUB_INTERNAL_IPS": internal_ips}, clear=False):
        return TenantMiddleware(app=MagicMock())


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)
