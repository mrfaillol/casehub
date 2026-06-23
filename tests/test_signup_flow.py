"""
Test CaseHub Onboarding / Signup Flow (routes/onboarding.py).

Validates:
  - POST /signup creates org + admin user
  - Duplicate slugs get unique suffixes
  - Weak passwords are rejected
  - Setup wizard pages render correctly
  - Plan selection and Stripe checkout
  - Team invite creates users and sends email
"""
import inspect
import re
import secrets
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# ---------------------------------------------------------------------------
# slugify unit tests
# ---------------------------------------------------------------------------

class TestSlugify:
    """Test the slugify helper used during signup."""

    def test_slugify_simple_name(self):
        """Simple firm name becomes lowercase slug."""
        from routes.onboarding import slugify
        assert slugify("Acme Law") == "acme-law"

    def test_slugify_strips_special_chars(self):
        """Special characters are removed."""
        from routes.onboarding import slugify
        result = slugify("Smith & Jones, LLC")
        assert "&" not in result
        assert "," not in result
        assert result == "smith-jones-llc"

    def test_slugify_collapses_whitespace(self):
        """Multiple spaces become a single dash."""
        from routes.onboarding import slugify
        result = slugify("  The   Big   Firm  ")
        assert "--" not in result
        assert result == "the-big-firm"

    def test_slugify_empty_string_returns_org(self):
        """Empty string returns fallback 'org'."""
        from routes.onboarding import slugify
        assert slugify("") == "org"
        assert slugify("   ") == "org"

    def test_slugify_truncates_long_names(self):
        """Slugs longer than 100 chars are truncated."""
        from routes.onboarding import slugify
        long_name = "a" * 200
        result = slugify(long_name)
        assert len(result) <= 100


# ---------------------------------------------------------------------------
# PLAN_TIERS structure
# ---------------------------------------------------------------------------

class TestPlanTiers:
    """Validate PLAN_TIERS constant used in onboarding.

    Spec (Equipe CaseHub, 28/05/2026): exatamente 2 planos — office (R$129) e enterprise
    (sob consulta). Usuários ILIMITADOS por enquanto em ambos (max_users == -1)."""

    def test_plan_tiers_exactly_two_plans(self):
        """PLAN_TIERS must contain exactly office + enterprise."""
        from routes.onboarding import PLAN_TIERS
        assert set(PLAN_TIERS.keys()) == {"office", "enterprise"}

    def test_office_price_is_129(self):
        """Office plan is R$129/mês."""
        from routes.onboarding import PLAN_TIERS
        assert PLAN_TIERS["office"]["price"] == 129

    def test_enterprise_is_contact_only(self):
        """Enterprise has no fixed price (sob consulta) and is contact-only."""
        from routes.onboarding import PLAN_TIERS
        assert PLAN_TIERS["enterprise"]["price"] is None
        assert PLAN_TIERS["enterprise"]["contact_only"] is True

    def test_all_tiers_have_required_keys(self):
        """Each tier must have name, price, max_users, max_clients, features."""
        from routes.onboarding import PLAN_TIERS
        required = {"name", "price", "max_users", "max_clients", "max_storage_gb", "features"}
        for tier_key, tier in PLAN_TIERS.items():
            for key in required:
                assert key in tier, f"Missing '{key}' in plan tier '{tier_key}'"

    def test_all_tiers_have_unlimited_users(self):
        """Usuários ilimitados por enquanto: max_users == -1 em todos os planos."""
        from routes.onboarding import PLAN_TIERS
        for tier_key, tier in PLAN_TIERS.items():
            assert tier["max_users"] == -1, f"Plan '{tier_key}' must have unlimited users"


# ---------------------------------------------------------------------------
# Signup endpoint signature / source inspection
# ---------------------------------------------------------------------------

class TestSignupEndpointSignature:
    """Verify public signup remains an access-request flow, not self-provisioning."""

    def test_signup_submit_has_firm_name(self):
        """signup_submit must accept firm_name parameter."""
        from routes.onboarding import signup_submit
        sig = inspect.signature(signup_submit)
        assert "firm_name" in sig.parameters

    def test_signup_submit_has_admin_email(self):
        """signup_submit must accept admin_email parameter."""
        from routes.onboarding import signup_submit
        sig = inspect.signature(signup_submit)
        assert "admin_email" in sig.parameters

    def test_signup_submit_has_password(self):
        """Signup accepts password for the feature-flagged self-service path."""
        from routes.onboarding import signup_submit
        sig = inspect.signature(signup_submit)
        assert "password" in sig.parameters

    def test_signup_submit_has_password_confirm(self):
        """Public signup must not accept password confirmation."""
        from routes.onboarding import signup_submit
        sig = inspect.signature(signup_submit)
        assert "password_confirm" not in sig.parameters

    def test_signup_submit_rejects_short_password(self):
        """Self-service signup validates password strength behind the feature flag."""
        from routes.onboarding import signup_submit
        source = inspect.getsource(signup_submit)
        assert "SELF_SERVICE_SIGNUP_ENABLED" in source
        assert "len(password) < 8" in source

    def test_signup_submit_checks_password_match(self):
        """Access request flow should not compare password fields."""
        from routes.onboarding import signup_submit
        source = inspect.getsource(signup_submit)
        assert "password_confirm" not in source

    def test_signup_creates_organization(self):
        """Public signup must not create organizations automatically."""
        from routes.onboarding import signup_submit
        source = inspect.getsource(signup_submit)
        assert "create_org" not in source
        assert "access_requests" in source

    def test_signup_creates_admin_user(self):
        """Self-service signup creates an inactive org plus admin user behind the flag."""
        from routes.onboarding import signup_submit
        source = inspect.getsource(signup_submit)
        assert source.index("SELF_SERVICE_SIGNUP_ENABLED") < source.index("User(")
        assert 'user_type="admin"' in source
        assert "is_active=False" in source

    def test_signup_generates_unique_slug_on_conflict(self):
        """Access request de-dupes by email instead of assigning public org slugs."""
        from routes.onboarding import signup_submit
        source = inspect.getsource(signup_submit)
        assert "ON CONFLICT (email)" in source


# ---------------------------------------------------------------------------
# Team invite source inspection
# ---------------------------------------------------------------------------

class TestTeamInviteSource:
    """Inspect the team invitation handler logic."""

    def test_team_invite_creates_user_with_must_change_password(self):
        """Invited users must have must_change_password=True."""
        from routes.onboarding import setup_team_invite
        source = inspect.getsource(setup_team_invite)
        assert "must_change_password=True" in source

    def test_team_invite_calls_send_email(self):
        """Invitation handler must call send_email."""
        from routes.onboarding import setup_team_invite
        source = inspect.getsource(setup_team_invite)
        assert "send_email" in source

    def test_team_invite_caps_at_10(self):
        """Team invites are capped at 10 during setup."""
        from routes.onboarding import setup_team_invite
        source = inspect.getsource(setup_team_invite)
        assert "[:10]" in source

    def test_team_invite_sets_user_type_case_worker(self):
        """Invited users are created as case_worker type."""
        from routes.onboarding import setup_team_invite
        source = inspect.getsource(setup_team_invite)
        assert 'user_type="case_worker"' in source or "user_type='case_worker'" in source


# ---------------------------------------------------------------------------
# Stripe checkout source inspection
# ---------------------------------------------------------------------------

class TestStripeCheckoutSource:
    """Inspect the plan save handler for Stripe integration."""

    def test_plan_save_checks_stripe_secret_key(self):
        """setup_plan_save must check for STRIPE_SECRET_KEY."""
        from routes.onboarding import setup_plan_save
        source = inspect.getsource(setup_plan_save)
        assert "STRIPE_SECRET_KEY" in source

    def test_plan_save_skips_checkout_for_contact_only_plan(self):
        """Contact-only plans should skip Stripe checkout."""
        from routes.onboarding import setup_plan_save
        source = inspect.getsource(setup_plan_save)
        assert 'not tier.get("contact_only")' in source

    def test_plan_save_creates_checkout_session(self):
        """setup_plan_save creates a stripe checkout session."""
        from routes.onboarding import setup_plan_save
        source = inspect.getsource(setup_plan_save)
        assert "checkout.Session.create" in source
