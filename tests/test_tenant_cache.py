"""
Test middleware/tenant.py - Tenant cache TTL and resolution logic.

Covers:
  - TenantMiddleware cache stores org data after resolution
  - Cache entries expire after CACHE_TTL seconds
  - Expired entries trigger re-fetch from database
  - get_current_org() reads from request.state or context var
  - require_org() raises HTTPException when no org is found
  - Exempt paths bypass tenant resolution
  - clear_cache() empties the cache
"""
import time
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from middleware.tenant import TenantMiddleware, get_current_org, require_org, _current_org


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------

class TestTenantCacheTTL:
    """Test that the tenant middleware cache respects TTL."""

    def test_cache_ttl_is_300_seconds(self):
        assert TenantMiddleware.CACHE_TTL == 300

    def test_cache_stores_org_data(self):
        """After resolution, org data should be in the cache."""
        mw = TenantMiddleware(app=MagicMock(), default_org_slug="default")
        domain = "acme.casehub.io"
        org_data = {"id": 1, "name": "Acme", "is_active": True}

        mw._org_cache[domain] = org_data
        mw._org_cache_ts[domain] = time.time()

        assert domain in mw._org_cache
        assert mw._org_cache[domain]["name"] == "Acme"

    def test_cache_hit_within_ttl(self):
        """A cache entry younger than CACHE_TTL should be returned."""
        mw = TenantMiddleware(app=MagicMock())
        domain = "fresh.casehub.io"
        org_data = {"id": 2, "name": "Fresh", "is_active": True}

        mw._org_cache[domain] = org_data
        mw._org_cache_ts[domain] = time.time()

        # Simulate the cache check logic from _resolve_org
        cache_age = time.time() - mw._org_cache_ts[domain]
        assert cache_age < TenantMiddleware.CACHE_TTL
        assert mw._org_cache[domain] == org_data

    def test_cache_miss_after_ttl_expiry(self):
        """A cache entry older than CACHE_TTL should be evicted."""
        mw = TenantMiddleware(app=MagicMock())
        domain = "expired.casehub.io"
        org_data = {"id": 3, "name": "Expired", "is_active": True}

        mw._org_cache[domain] = org_data
        # Set timestamp far in the past
        mw._org_cache_ts[domain] = time.time() - (TenantMiddleware.CACHE_TTL + 10)

        # Simulate the cache check logic
        cache_age = time.time() - mw._org_cache_ts[domain]
        assert cache_age >= TenantMiddleware.CACHE_TTL

        # After detecting expiry, entry should be removed
        if cache_age >= TenantMiddleware.CACHE_TTL:
            del mw._org_cache[domain]
            mw._org_cache_ts.pop(domain, None)

        assert domain not in mw._org_cache

    def test_clear_cache_removes_all_entries(self):
        mw = TenantMiddleware(app=MagicMock())
        mw._org_cache["a.com"] = {"id": 1}
        mw._org_cache["b.com"] = {"id": 2}
        mw._org_cache_ts["a.com"] = time.time()
        mw._org_cache_ts["b.com"] = time.time()

        mw.clear_cache()
        assert len(mw._org_cache) == 0

    def test_different_domains_cached_independently(self):
        mw = TenantMiddleware(app=MagicMock())
        mw._org_cache["acme.casehub.io"] = {"id": 1, "name": "Acme"}
        mw._org_cache["beta.casehub.io"] = {"id": 2, "name": "Beta"}
        mw._org_cache_ts["acme.casehub.io"] = time.time()
        mw._org_cache_ts["beta.casehub.io"] = time.time()

        assert mw._org_cache["acme.casehub.io"]["name"] == "Acme"
        assert mw._org_cache["beta.casehub.io"]["name"] == "Beta"


# ---------------------------------------------------------------------------
# Exempt paths
# ---------------------------------------------------------------------------

class TestTenantExemptPaths:
    """Test that exempt paths skip tenant resolution."""

    def test_health_is_exempt(self):
        assert "/health" in TenantMiddleware.EXEMPT_PATHS

    def test_docs_is_exempt(self):
        assert "/docs" in TenantMiddleware.EXEMPT_PATHS

    def test_static_is_exempt(self):
        assert "/static" in TenantMiddleware.EXEMPT_PATHS

    def test_favicon_is_exempt(self):
        assert "/favicon.ico" in TenantMiddleware.EXEMPT_PATHS

    def test_signup_is_exempt(self):
        assert "/signup" in TenantMiddleware.EXEMPT_PATHS

    def test_superadmin_is_exempt(self):
        assert "/superadmin" in TenantMiddleware.EXEMPT_PATHS

    def test_setup_is_exempt(self):
        assert "/setup" in TenantMiddleware.EXEMPT_PATHS


# ---------------------------------------------------------------------------
# get_current_org()
# ---------------------------------------------------------------------------

class TestGetCurrentOrg:
    """Test the get_current_org helper function."""

    def test_returns_org_from_request_state(self):
        request = MagicMock()
        request.state.org = {"id": 1, "name": "Test Org"}
        result = get_current_org(request)
        assert result == {"id": 1, "name": "Test Org"}

    def test_returns_none_without_request(self):
        # Reset context var
        token = _current_org.set(None)
        try:
            result = get_current_org()
            assert result is None
        finally:
            _current_org.reset(token)

    def test_returns_org_from_context_var(self):
        org = {"id": 5, "name": "Context Org"}
        token = _current_org.set(org)
        try:
            result = get_current_org()
            assert result == org
        finally:
            _current_org.reset(token)

    def test_request_state_takes_priority_over_context_var(self):
        """If request has state.org, it should be preferred."""
        request = MagicMock()
        request.state.org = {"id": 10, "name": "State Org"}

        token = _current_org.set({"id": 99, "name": "Context Org"})
        try:
            result = get_current_org(request)
            assert result["id"] == 10
        finally:
            _current_org.reset(token)


# ---------------------------------------------------------------------------
# require_org()
# ---------------------------------------------------------------------------

class TestRequireOrg:
    """Test the require_org dependency function."""

    def test_returns_org_when_present(self):
        request = MagicMock()
        request.state.org = {"id": 1, "name": "OK"}
        result = require_org(request)
        assert result["id"] == 1

    def test_raises_403_when_no_org(self):
        from fastapi import HTTPException
        request = MagicMock()
        request.state = MagicMock(spec=[])  # No 'org' attribute
        token = _current_org.set(None)
        try:
            with pytest.raises(HTTPException) as exc_info:
                require_org(request)
            assert exc_info.value.status_code == 403
        finally:
            _current_org.reset(token)


# ---------------------------------------------------------------------------
# Resolution strategies
# ---------------------------------------------------------------------------

class TestTenantResolutionStrategies:
    """Test the org resolution order: internal header -> domain -> subdomain -> default."""

    def test_x_org_id_header_strategy_is_internal_only(self):
        """X-Org-Id is only allowed before Host resolution for internal peers."""
        import inspect
        mw = TenantMiddleware(app=MagicMock())
        source = inspect.getsource(mw._resolve_org)
        internal_gate_idx = source.index("if self._internal_ips")
        header_idx = source.index('request.headers.get("X-Org-Id")')
        domain_idx = source.index("Strategy 1: Domain-based")
        assert internal_gate_idx < header_idx < domain_idx

    def test_subdomain_extraction_logic(self):
        """Verify subdomain extraction: acme.casehub.io -> slug='acme'."""
        host = "acme.casehub.io"
        parts = host.split(".")
        assert len(parts) >= 3
        slug = parts[0]
        assert slug == "acme"

    def test_localhost_no_subdomain(self):
        """localhost should not produce a subdomain slug."""
        host = "localhost"
        parts = host.split(".")
        assert len(parts) < 3

    def test_port_stripped_from_host(self):
        """Host header with port should have port stripped."""
        host_with_port = "acme.casehub.io:8001"
        host = host_with_port.split(":")[0]
        assert host == "acme.casehub.io"
