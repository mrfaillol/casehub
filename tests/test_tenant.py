"""
Test multi-tenancy isolation for CaseHub.
Tests that tenant_query filters, org creation, and cross-org visibility work correctly.
"""
import pytest
import uuid

from conftest import TestSession, TEST_ENGINE
from models.base import Base
from models.tenant import Organization, tenant_query, get_org_by_slug
from models.client import Client
from models.user import User


# --- Helpers ---

def _create_org(db, name="Org A", slug=None):
    """Create a test organization."""
    org = Organization(
        uuid=str(uuid.uuid4()),
        name=name,
        slug=slug or name.lower().replace(" ", "-"),
        email=f"{name.lower().replace(' ', '')}@test.com",
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _create_client(db, org_id, first_name="John", last_name="Doe"):
    """Create a test client scoped to an org."""
    client = Client(
        first_name=first_name,
        last_name=last_name,
        email=f"{first_name.lower()}@test.com",
    )
    # If the Client model has org_id, set it
    if hasattr(client, "org_id"):
        client.org_id = org_id
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


# --- Tests ---

class TestOrganizationModel:
    """Test Organization creation and retrieval."""

    def test_create_organization(self, db):
        org = _create_org(db, name="Test Firm", slug="test-firm")
        assert org.id is not None
        assert org.name == "Test Firm"
        assert org.slug == "test-firm"
        assert org.is_active is True

    def test_org_defaults(self, db):
        org = _create_org(db)
        # Spec (Equipe CaseHub, 28/05/2026): default plan = office, usuários ilimitados (-1).
        assert org.plan == "office"
        assert org.max_users == -1
        assert org.max_clients == 100
        assert org.currency == "USD"
        assert org.timezone == "America/New_York"

    def test_org_unique_slug(self, db):
        _create_org(db, slug="unique-slug")
        with pytest.raises(Exception):
            _create_org(db, slug="unique-slug")

    def test_get_org_by_slug(self, db):
        org = _create_org(db, slug="find-me")
        found = get_org_by_slug(db, "find-me")
        assert found is not None
        assert found.id == org.id

    def test_get_org_by_slug_not_found(self, db):
        result = get_org_by_slug(db, "nonexistent")
        assert result is None


class TestTenantQuery:
    """Test tenant_query filtering."""

    def test_tenant_query_filters_by_org_id(self, db):
        """Verify tenant_query only returns records for the given org."""
        org_a = _create_org(db, name="Org A", slug="org-a")
        org_b = _create_org(db, name="Org B", slug="org-b")

        # Only run this test if Client model supports org_id
        if not hasattr(Client, "org_id"):
            pytest.skip("Client model does not have org_id column yet")

        client_a = _create_client(db, org_a.id, "Alice", "Smith")
        client_b = _create_client(db, org_b.id, "Bob", "Jones")

        # Query from org A's perspective
        query_a = tenant_query(db, Client, org_a.id)
        results_a = query_a.all()
        emails_a = [c.email for c in results_a]

        assert "alice@test.com" in emails_a
        assert "bob@test.com" not in emails_a

    def test_tenant_query_empty_org(self, db):
        """An org with no clients should return empty."""
        org = _create_org(db, slug="empty-org")

        if not hasattr(Client, "org_id"):
            pytest.skip("Client model does not have org_id column yet")

        results = tenant_query(db, Client, org.id).all()
        assert len(results) == 0


class TestCrossTenantIsolation:
    """Test that data from one org is invisible to another."""

    def test_org_a_cannot_see_org_b_clients(self, db):
        """Core isolation test."""
        if not hasattr(Client, "org_id"):
            pytest.skip("Client model does not have org_id column yet")

        org_a = _create_org(db, slug="iso-a")
        org_b = _create_org(db, slug="iso-b")

        _create_client(db, org_a.id, "Alice", "A")
        _create_client(db, org_b.id, "Bob", "B")

        clients_a = tenant_query(db, Client, org_a.id).all()
        clients_b = tenant_query(db, Client, org_b.id).all()

        assert len(clients_a) == 1
        assert clients_a[0].first_name == "Alice"
        assert len(clients_b) == 1
        assert clients_b[0].first_name == "Bob"
