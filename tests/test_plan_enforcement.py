"""
Test CaseHub Plan Enforcement Middleware (middleware/plan_enforcement.py).

Validates:
  - Starter/Professional/Enterprise plan limits are enforced
  - Non-POST requests bypass enforcement
  - Non-enforced paths bypass enforcement
  - Missing org_id bypasses gracefully
  - DB errors fail open (don't block)
"""
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


def _make_request(method="POST", path="/clients/new", org=None):
    """Create a mock Starlette Request object."""
    request = MagicMock()
    request.method = method
    url_mock = MagicMock()
    url_mock.path = path
    request.url = url_mock
    # Set org in request.state
    state = MagicMock()
    state.org = org
    request.state = state
    return request


def _run_dispatch(request, call_next_response=None):
    """Run PlanEnforcementMiddleware.dispatch synchronously."""
    from middleware.plan_enforcement import PlanEnforcementMiddleware

    if call_next_response is None:
        call_next_response = MagicMock()
        call_next_response.status_code = 200

    async def mock_call_next(req):
        return call_next_response

    app = MagicMock()
    middleware = PlanEnforcementMiddleware(app)

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(middleware.dispatch(request, mock_call_next))
    finally:
        loop.close()
    return result


class TestUsersUnlimited:
    """Spec (Equipe CaseHub, 28/05/2026): usuários ILIMITADOS por enquanto em todos os
    planos. /admin/users/new não é mais enforced — nunca bloqueia, mesmo com
    valores legados de max_users gravados na org."""

    def test_users_always_allowed_even_at_legacy_limit(self):
        """POST /admin/users/new must pass through even when count >= legacy max_users."""
        # No tenant_count patch needed: the rule is gone, so it never counts.
        org = {"id": 1, "max_users": 5, "plan": "office"}
        request = _make_request(method="POST", path="/admin/users/new", org=org)
        passthrough = MagicMock()
        passthrough.status_code = 200
        result = _run_dispatch(request, call_next_response=passthrough)
        assert result.status_code == 200

    def test_users_allowed_with_legacy_plan_value(self):
        """Even orgs still stored as a legacy plan must allow user creation."""
        org = {"id": 2, "max_users": 25, "plan": "professional"}
        request = _make_request(method="POST", path="/admin/users/new", org=org)
        passthrough = MagicMock()
        passthrough.status_code = 200
        result = _run_dispatch(request, call_next_response=passthrough)
        assert result.status_code == 200


class TestPlanLimitsClients:
    """Client limits are still enforced (unchanged by the users-unlimited spec)."""

    @patch("middleware.plan_enforcement.tenant_count", return_value=100)
    @patch("middleware.plan_enforcement.SessionLocal")
    def test_at_max_clients_blocks(self, mock_session_cls, mock_count):
        """POST to /clients/new at max_clients=100 with count=100 should return 403."""
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        org = {"id": 1, "max_clients": 100, "plan": "office"}
        request = _make_request(method="POST", path="/clients/new", org=org)
        result = _run_dispatch(request)
        assert result.status_code == 403


class TestPlanLimitsEnterprise:
    """Test enforcement for enterprise plan (unlimited)."""

    def test_enterprise_unlimited_users_allows(self):
        """Enterprise plan with max_users=-1 should allow any count."""
        org = {"id": 3, "max_users": -1, "plan": "enterprise"}
        request = _make_request(method="POST", path="/admin/users/new", org=org)
        passthrough = MagicMock()
        passthrough.status_code = 200
        result = _run_dispatch(request, call_next_response=passthrough)
        # -1 means unlimited, should pass through without even counting
        assert result.status_code == 200

    def test_enterprise_unlimited_none_allows(self):
        """Enterprise plan with max_users=None should also allow."""
        org = {"id": 3, "max_users": None, "plan": "enterprise"}
        request = _make_request(method="POST", path="/admin/users/new", org=org)
        passthrough = MagicMock()
        passthrough.status_code = 200
        result = _run_dispatch(request, call_next_response=passthrough)
        assert result.status_code == 200


class TestBypassConditions:
    """Test cases where enforcement is bypassed."""

    def test_get_request_bypasses_enforcement(self):
        """GET requests should never be enforced."""
        org = {"id": 1, "max_users": 0, "plan": "starter"}
        request = _make_request(method="GET", path="/admin/users/new", org=org)
        passthrough = MagicMock()
        passthrough.status_code = 200
        result = _run_dispatch(request, call_next_response=passthrough)
        assert result.status_code == 200

    def test_non_enforced_path_bypasses(self):
        """POST to a path not in ENFORCEMENT_RULES should pass through."""
        org = {"id": 1, "max_users": 0, "plan": "starter"}
        request = _make_request(method="POST", path="/api/login", org=org)
        passthrough = MagicMock()
        passthrough.status_code = 200
        result = _run_dispatch(request, call_next_response=passthrough)
        assert result.status_code == 200

    def test_missing_org_bypasses(self):
        """No org in request.state should pass through gracefully."""
        request = _make_request(method="POST", path="/clients/new", org=None)
        passthrough = MagicMock()
        passthrough.status_code = 200
        result = _run_dispatch(request, call_next_response=passthrough)
        assert result.status_code == 200

    def test_missing_org_id_bypasses(self):
        """Org dict without 'id' should pass through gracefully."""
        org = {"plan": "starter", "max_clients": 0}
        request = _make_request(method="POST", path="/clients/new", org=org)
        passthrough = MagicMock()
        passthrough.status_code = 200
        result = _run_dispatch(request, call_next_response=passthrough)
        assert result.status_code == 200

    @patch("middleware.plan_enforcement.tenant_count", side_effect=Exception("DB connection lost"))
    @patch("middleware.plan_enforcement.SessionLocal")
    def test_db_error_fails_open(self, mock_session_cls, mock_count):
        """DB errors should fail open (allow the request)."""
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        org = {"id": 1, "max_users": 5, "plan": "starter"}
        request = _make_request(method="POST", path="/admin/users/new", org=org)
        passthrough = MagicMock()
        passthrough.status_code = 200
        result = _run_dispatch(request, call_next_response=passthrough)
        assert result.status_code == 200


class TestEnforcementRules:
    """Verify the ENFORCEMENT_RULES mapping is correct."""

    def test_enforcement_rules_excludes_users(self):
        """Spec (Equipe CaseHub, 28/05/2026): usuários ilimitados — /admin/users/new
        must NOT be enforced so user creation is never blocked."""
        from middleware.plan_enforcement import ENFORCEMENT_RULES
        assert "/admin/users/new" not in ENFORCEMENT_RULES

    def test_enforcement_rules_has_clients(self):
        """ENFORCEMENT_RULES must include /clients/new."""
        from middleware.plan_enforcement import ENFORCEMENT_RULES
        assert "/clients/new" in ENFORCEMENT_RULES

    def test_enforcement_rules_has_cases(self):
        """ENFORCEMENT_RULES must include /cases/new."""
        from middleware.plan_enforcement import ENFORCEMENT_RULES
        assert "/cases/new" in ENFORCEMENT_RULES

    def test_enforcement_rules_structure(self):
        """Each rule must have model, limit_field, and resource_name."""
        from middleware.plan_enforcement import ENFORCEMENT_RULES
        for path, rule in ENFORCEMENT_RULES.items():
            assert "model" in rule, f"Missing 'model' in rule for {path}"
            assert "limit_field" in rule, f"Missing 'limit_field' in rule for {path}"
            assert "resource_name" in rule, f"Missing 'resource_name' in rule for {path}"
