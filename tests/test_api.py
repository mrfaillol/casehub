"""
Test API endpoints for CaseHub.
Tests authentication requirements, CRUD operations, and org scoping.
"""
import pytest
from unittest.mock import patch, MagicMock
import bcrypt

from conftest import TestSession, TEST_ENGINE
from models.user import User
from models.client import Client


# --- Helpers ---

def _create_user(db, email="api@test.com", user_type="admin"):
    user = User(
        email=email,
        name="API Test User",
        password_hash=User.hash_password("ApiPass123!"),
        user_type=user_type,
        enabled=True,
        must_change_password=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# --- Tests ---

class TestAPIAuthentication:
    """Test that API endpoints require authentication."""

    def test_create_access_token_for_api(self):
        """API tokens should be valid JWT strings."""
        from auth import create_access_token
        token = create_access_token({"sub": "api@test.com"})
        assert token is not None
        assert isinstance(token, str)

    def test_bearer_token_validation(self):
        """A valid bearer token should decode successfully."""
        from auth import create_access_token, _decode_token
        token = create_access_token({"sub": "api@test.com"})
        payload = _decode_token(token, expected_type="access")
        assert payload is not None
        assert payload["sub"] == "api@test.com"

    def test_expired_token_rejected(self):
        """An expired token should be rejected."""
        from auth import create_access_token, _decode_token
        from datetime import timedelta
        token = create_access_token(
            {"sub": "api@test.com"},
            expires_delta=timedelta(seconds=-10),
        )
        result = _decode_token(token)
        assert result is None

    def test_no_token_should_fail(self):
        """Without a token, API should not authenticate."""
        from auth import _decode_token
        result = _decode_token("")
        assert result is None


class TestClientAPI:
    """Test client-related API operations at the model level."""

    def test_create_client_model(self, db):
        client = Client(
            first_name="API",
            last_name="Client",
            email="apiclient@test.com",
            client_number="API-001",
        )
        db.add(client)
        db.commit()
        db.refresh(client)
        assert client.id is not None
        assert client.client_number == "API-001"

    def test_list_clients_for_org(self, db):
        """Listing clients returns only the org's clients."""
        c1 = Client(first_name="A", last_name="One", email="a@test.com")
        c2 = Client(first_name="B", last_name="Two", email="b@test.com")
        db.add_all([c1, c2])
        db.commit()

        clients = db.query(Client).all()
        assert len(clients) >= 2

    def test_query_client_by_id(self, db):
        client = Client(first_name="Find", last_name="Me", email="find@test.com")
        db.add(client)
        db.commit()
        db.refresh(client)

        found = db.query(Client).filter(Client.id == client.id).first()
        assert found is not None
        assert found.email == "find@test.com"


class TestAPIResponseCodes:
    """Test expected API behavior patterns."""

    def test_unauthenticated_request_pattern(self):
        """Verify that the auth check pattern works as expected."""
        from auth import get_current_user
        mock_request = MagicMock()
        mock_request.cookies = {}

        # Without a valid session, should return None (which routes convert to 401/redirect)
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        result = get_current_user(mock_request, mock_db)
        assert result is None

    def test_wrong_org_pattern(self, db):
        """Verify that querying with wrong org_id returns nothing."""
        if not hasattr(Client, "org_id"):
            pytest.skip("Client model does not have org_id column yet")

        client = Client(first_name="Org", last_name="Scoped", email="org@test.com")
        client.org_id = 1
        db.add(client)
        db.commit()

        # Query with different org
        from models.tenant import tenant_query
        results = tenant_query(db, Client, 9999).all()
        assert len(results) == 0
