"""
Test authentication flows for CaseHub.
Tests JWT creation, validation, login/logout, rate limiting, and protected routes.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import jwt
import bcrypt

from conftest import TestSession, TEST_ENGINE
from models.base import Base
from models.user import User


# --- Helpers ---

def _create_test_user(db, email="user@test.com", password="TestPass123!", user_type="admin"):
    """Insert a test user into the DB."""
    user = User(
        email=email,
        name="Test User",
        password_hash=bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
        user_type=user_type,
        enabled=True,
        must_change_password=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# --- Tests ---

class TestJWTTokens:
    """Test JWT token creation and validation."""

    def test_create_access_token_returns_string(self):
        from auth import create_access_token
        token = create_access_token({"sub": "user@test.com"})
        assert isinstance(token, str)
        assert len(token) > 20

    def test_create_access_token_contains_claims(self):
        from auth import create_access_token, SECRET_KEY, ALGORITHM
        token = create_access_token({"sub": "user@test.com"})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "user@test.com"
        assert payload["type"] == "access"
        assert "exp" in payload

    def test_create_refresh_token_has_long_expiry(self):
        from auth import create_refresh_token, SECRET_KEY, ALGORITHM
        token = create_refresh_token({"sub": "user@test.com"})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["type"] == "refresh"
        # Refresh token should expire > 1 day from now
        exp = datetime.utcfromtimestamp(payload["exp"])
        assert exp > datetime.utcnow() + timedelta(days=1)

    def test_decode_valid_token(self):
        from auth import create_access_token, _decode_token
        token = create_access_token({"sub": "user@test.com"})
        payload = _decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user@test.com"

    def test_decode_invalid_token_returns_none(self):
        from auth import _decode_token
        result = _decode_token("invalid.token.here")
        assert result is None

    def test_decode_expired_token_returns_none(self):
        from auth import create_access_token, _decode_token
        token = create_access_token(
            {"sub": "user@test.com"},
            expires_delta=timedelta(seconds=-1),
        )
        result = _decode_token(token)
        assert result is None

    def test_decode_wrong_type_returns_none(self):
        from auth import create_access_token, _decode_token
        token = create_access_token({"sub": "user@test.com"})
        # Expect access token, but ask for refresh type
        result = _decode_token(token, expected_type="refresh")
        assert result is None


class TestGetCurrentUser:
    """Test get_current_user extracts user from cookie."""

    def test_no_cookie_returns_none(self, db, mock_request):
        from auth import get_current_user
        mock_request.cookies = {}
        # We need to mock Depends(get_db) by passing db directly
        result = get_current_user(mock_request, db)
        assert result is None

    def test_invalid_cookie_returns_none(self, db, mock_request):
        from auth import get_current_user
        mock_request.cookies = {"casehub_token": "garbage"}
        result = get_current_user(mock_request, db)
        assert result is None

    def test_valid_cookie_returns_user(self, db, mock_request):
        from auth import get_current_user, create_access_token
        user = _create_test_user(db)
        token = create_access_token({"sub": user.email})
        mock_request.cookies = {"casehub_token": token}
        # Model an unresolved-tenant request (apex / single-tenant): real
        # TenantMiddleware sets request.state.org_id to an int or leaves it
        # absent, never to a truthy MagicMock. Without this, the IDOR C5
        # unscoped-admin guard (auth._enforce_tenant_binding) would treat the
        # auto-mock org_id as a "resolved tenant" and reject the org_id-less
        # test user — an artifact of the bare MagicMock fixture, not runtime.
        mock_request.state.org_id = None
        result = get_current_user(mock_request, db)
        assert result is not None
        assert result.email == user.email

    def test_valid_cookie_nonexistent_user_returns_none(self, db, mock_request):
        from auth import get_current_user, create_access_token
        token = create_access_token({"sub": "ghost@nowhere.com"})
        mock_request.cookies = {"casehub_token": token}
        result = get_current_user(mock_request, db)
        assert result is None


class TestUserModel:
    """Test User model password hashing and verification."""

    def test_verify_correct_password(self, db):
        user = _create_test_user(db, password="MySecret99!")
        assert user.verify_password("MySecret99!") is True

    def test_verify_wrong_password(self, db):
        user = _create_test_user(db, password="MySecret99!")
        assert user.verify_password("WrongPassword") is False

    def test_hash_password_is_unique(self):
        h1 = User.hash_password("same")
        h2 = User.hash_password("same")
        # bcrypt uses random salt, so hashes differ
        assert h1 != h2

    def test_user_must_change_password_default(self, db):
        user = User(
            email="new@test.com",
            name="New",
            password_hash=User.hash_password("temp"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        assert user.must_change_password is True
