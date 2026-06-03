"""
Test CaseHub Feature Flag system (middleware/features.py).
Tests require_feature dependency, plan-based feature resolution,
and the fallback feature map.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException

from middleware.features import (
    require_feature,
    _get_org_features,
    _PLAN_FEATURES_FALLBACK,
)


# --- Helpers ---

def _mock_request_with_org(plan="professional", features=None, org_dict=True):
    """
    Build a mock Request whose state.org carries plan/features info.

    Args:
        plan: Plan name string.
        features: A list of feature strings (or None to fall through to plan).
        org_dict: If True the org is a dict; if False it's an object with attrs.
    """
    request = MagicMock()
    if org_dict:
        org = {"plan": plan}
        if features is not None:
            org["features"] = features
        request.state.org = org
    else:
        org = MagicMock()
        org.plan = plan
        org.features = features
        request.state.org = org
    request.state.org_id = 1
    return request


def _mock_db_no_plans_table():
    """Return a mock DB session whose execute always raises (no plans table)."""
    db = MagicMock()
    db.execute.side_effect = Exception("no such table: plans")
    return db


# ===================================================================
# _get_org_features tests
# ===================================================================

class TestGetOrgFeatures:
    """Test the internal feature resolution function."""

    def test_no_org_returns_empty(self):
        """When request has no org, features should be empty."""
        request = MagicMock()
        request.state.org = None
        db = _mock_db_no_plans_table()
        assert _get_org_features(request, db) == []

    def test_org_with_features_list(self):
        """When org has a features list, that list is returned."""
        request = _mock_request_with_org(features=["sso", "api_access"])
        db = _mock_db_no_plans_table()
        features = _get_org_features(request, db)
        assert "sso" in features
        assert "api_access" in features

    def test_fallback_to_plan_map_starter(self):
        """When org has no features list and DB has no plans table, fall back to hardcoded map."""
        request = _mock_request_with_org(plan="starter", features=None)
        db = _mock_db_no_plans_table()
        features = _get_org_features(request, db)
        assert features == _PLAN_FEATURES_FALLBACK["starter"]

    def test_fallback_to_plan_map_enterprise(self):
        """Enterprise plan should include enterprise-level features."""
        request = _mock_request_with_org(plan="enterprise", features=None)
        db = _mock_db_no_plans_table()
        features = _get_org_features(request, db)
        assert "sso" in features
        assert "audit" in features
        assert "api_access" in features

    def test_unknown_plan_falls_back_to_starter(self):
        """An unknown plan name should fall back to starter features."""
        request = _mock_request_with_org(plan="nonexistent_plan", features=None)
        db = _mock_db_no_plans_table()
        features = _get_org_features(request, db)
        assert features == _PLAN_FEATURES_FALLBACK["starter"]

    def test_org_as_object_with_attrs(self):
        """Should also work when org is an object (not a dict) with attributes."""
        request = _mock_request_with_org(
            plan="professional", features=None, org_dict=False
        )
        db = _mock_db_no_plans_table()
        features = _get_org_features(request, db)
        assert features == _PLAN_FEATURES_FALLBACK["professional"]


# ===================================================================
# require_feature tests
# ===================================================================

class TestRequireFeature:
    """Test the require_feature dependency factory."""

    @pytest.mark.asyncio
    async def test_allows_access_when_feature_in_plan(self):
        """require_feature should return True when feature is in org's plan."""
        dep = require_feature("cases")
        request = _mock_request_with_org(plan="starter")
        db = _mock_db_no_plans_table()
        result = await dep(request=request, db=db)
        assert result is True

    @pytest.mark.asyncio
    async def test_blocks_access_when_feature_not_in_plan(self):
        """require_feature should raise HTTP 402 when feature is not in plan."""
        dep = require_feature("sso")
        request = _mock_request_with_org(plan="starter")
        db = _mock_db_no_plans_table()
        with pytest.raises(HTTPException) as exc_info:
            await dep(request=request, db=db)
        assert exc_info.value.status_code == 402
        assert "sso" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_enterprise_has_all_features(self):
        """Enterprise plan should pass require_feature for all enterprise features."""
        enterprise_features = _PLAN_FEATURES_FALLBACK["enterprise"]
        request = _mock_request_with_org(plan="enterprise")
        db = _mock_db_no_plans_table()
        for feat in enterprise_features:
            dep = require_feature(feat)
            result = await dep(request=request, db=db)
            assert result is True

    @pytest.mark.asyncio
    async def test_starter_blocked_from_ai_lor(self):
        """Starter plan should not have access to ai_lor."""
        dep = require_feature("ai_lor")
        request = _mock_request_with_org(plan="starter")
        db = _mock_db_no_plans_table()
        with pytest.raises(HTTPException) as exc_info:
            await dep(request=request, db=db)
        assert exc_info.value.status_code == 402

    @pytest.mark.asyncio
    async def test_professional_has_ai_lor(self):
        """Professional plan should have access to ai_lor."""
        dep = require_feature("ai_lor")
        request = _mock_request_with_org(plan="professional")
        db = _mock_db_no_plans_table()
        result = await dep(request=request, db=db)
        assert result is True


# ===================================================================
# Plan feature map sanity tests
# ===================================================================

class TestPlanFeaturesMap:
    """Validate the hardcoded plan-features fallback map."""

    def test_starter_has_core_features(self):
        """Starter plan should include basic features."""
        starter = _PLAN_FEATURES_FALLBACK["starter"]
        assert "cases" in starter
        assert "clients" in starter
        assert "documents" in starter

    def test_professional_superset_of_starter(self):
        """Professional plan features should be a superset of starter."""
        starter = set(_PLAN_FEATURES_FALLBACK["starter"])
        professional = set(_PLAN_FEATURES_FALLBACK["professional"])
        assert starter.issubset(professional), \
            f"Starter features not in professional: {starter - professional}"

    def test_enterprise_superset_of_professional(self):
        """Enterprise plan features should be a superset of professional."""
        professional = set(_PLAN_FEATURES_FALLBACK["professional"])
        enterprise = set(_PLAN_FEATURES_FALLBACK["enterprise"])
        assert professional.issubset(enterprise), \
            f"Professional features not in enterprise: {professional - enterprise}"

    def test_all_plans_have_cases_and_clients(self):
        """Every plan should at least include cases and clients."""
        for plan_name, features in _PLAN_FEATURES_FALLBACK.items():
            assert "cases" in features, f"Plan '{plan_name}' missing 'cases'"
            assert "clients" in features, f"Plan '{plan_name}' missing 'clients'"
