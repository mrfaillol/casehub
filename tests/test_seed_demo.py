"""
Test CaseHub Demo Seed Script (scripts/seed_demo.py).

Validates:
  - Demo data constants have correct structure and counts
  - Immigration clients have country_of_origin (visa-related)
  - Lite clients have CPF (Brazilian ID)
  - Idempotency: seed_demo skips if demo org exists
  - seed_demo function signature and module importability
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Ensure scripts/ is importable
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


# ---------------------------------------------------------------------------
# Demo data validation
# ---------------------------------------------------------------------------

class TestDemoDataConstants:
    """Validate the demo data constants in seed_demo module."""

    def test_immigration_clients_has_5_entries(self):
        """IMMIGRATION_CLIENTS must have exactly 5 entries."""
        from scripts.seed_demo import IMMIGRATION_CLIENTS
        assert len(IMMIGRATION_CLIENTS) == 5

    def test_lite_clients_has_5_entries(self):
        """LITE_CLIENTS must have exactly 5 entries."""
        from scripts.seed_demo import LITE_CLIENTS
        assert len(LITE_CLIENTS) == 5

    def test_immigration_cases_has_3_entries(self):
        """IMMIGRATION_CASES must have exactly 3 entries."""
        from scripts.seed_demo import IMMIGRATION_CASES
        assert len(IMMIGRATION_CASES) == 3

    def test_lite_cases_has_3_entries(self):
        """LITE_CASES must have exactly 3 entries."""
        from scripts.seed_demo import LITE_CASES
        assert len(LITE_CASES) == 3

    def test_immigration_tasks_has_8_entries(self):
        """IMMIGRATION_TASKS must have exactly 8 entries."""
        from scripts.seed_demo import IMMIGRATION_TASKS
        assert len(IMMIGRATION_TASKS) == 8

    def test_lite_tasks_has_8_entries(self):
        """LITE_TASKS must have exactly 8 entries."""
        from scripts.seed_demo import LITE_TASKS
        assert len(LITE_TASKS) == 8


class TestImmigrationClientFields:
    """Verify immigration clients have visa-related fields."""

    def test_all_have_country_of_origin(self):
        """Every immigration client must have country_of_origin."""
        from scripts.seed_demo import IMMIGRATION_CLIENTS
        for client in IMMIGRATION_CLIENTS:
            assert "country_of_origin" in client, f"Missing country_of_origin in {client}"
            assert client["country_of_origin"], "country_of_origin must not be empty"

    def test_all_have_email(self):
        """Every immigration client must have an email address."""
        from scripts.seed_demo import IMMIGRATION_CLIENTS
        for client in IMMIGRATION_CLIENTS:
            assert "email" in client
            assert "@" in client["email"]


class TestLiteClientFields:
    """Verify lite clients have Brazilian-specific fields."""

    def test_all_have_cpf(self):
        """Every lite client must have a CPF (Brazilian tax ID)."""
        from scripts.seed_demo import LITE_CLIENTS
        for client in LITE_CLIENTS:
            assert "cpf" in client, f"Missing cpf in {client}"
            assert client["cpf"], "cpf must not be empty"

    def test_all_have_city_and_state(self):
        """Every lite client must have city and state."""
        from scripts.seed_demo import LITE_CLIENTS
        for client in LITE_CLIENTS:
            assert "city" in client, f"Missing city in {client}"
            assert "state" in client, f"Missing state in {client}"


class TestImmigrationCaseFields:
    """Verify immigration cases have visa-related fields."""

    def test_all_have_visa_type(self):
        """Every immigration case must have a visa_type."""
        from scripts.seed_demo import IMMIGRATION_CASES
        for case in IMMIGRATION_CASES:
            assert "visa_type" in case
            assert case["visa_type"]

    def test_all_have_receipt_number(self):
        """Every immigration case must have a receipt_number."""
        from scripts.seed_demo import IMMIGRATION_CASES
        for case in IMMIGRATION_CASES:
            assert "receipt_number" in case
            assert case["receipt_number"]


class TestSeedDemoIdempotency:
    """Verify seed_demo is idempotent (skips if demo org exists)."""

    def test_seed_demo_function_exists(self):
        """seed_demo function must be importable."""
        from scripts.seed_demo import seed_demo
        assert callable(seed_demo)

    @patch("scripts.seed_demo.get_org_by_slug")
    @patch("scripts.seed_demo.get_db")
    @patch("scripts.seed_demo.init_db")
    def test_seed_demo_skips_if_demo_org_exists(self, mock_init, mock_get_db, mock_get_slug):
        """seed_demo should skip seeding when 'demo' org already exists."""
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_existing_org = MagicMock()
        mock_existing_org.id = 42
        mock_get_slug.return_value = mock_existing_org

        from scripts.seed_demo import seed_demo
        seed_demo("immigration")

        # Should not have called db.add (no new records created)
        mock_db.add.assert_not_called()

    def test_seed_demo_source_checks_existing_org(self):
        """seed_demo source must check for existing demo org."""
        import inspect
        from scripts.seed_demo import seed_demo
        source = inspect.getsource(seed_demo)
        assert 'get_org_by_slug(db, "demo")' in source or "get_org_by_slug(db, 'demo')" in source
