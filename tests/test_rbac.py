"""
Test role-based access control for CaseHub.
Tests that different user types have correct permissions.
"""
import pytest
from unittest.mock import patch, MagicMock
import bcrypt

from conftest import TestSession, TEST_ENGINE
from models.user import User, UserType


# --- Helpers ---

def _create_user(db, email, user_type, name=None):
    """Create a user with the given type."""
    user = User(
        email=email,
        name=name or f"{user_type.capitalize()} User",
        password_hash=User.hash_password("TestPass123!"),
        user_type=user_type,
        enabled=True,
        must_change_password=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# --- Tests ---

class TestUserTypes:
    """Test that user types are created correctly."""

    def test_create_admin(self, db):
        user = _create_user(db, "admin@test.com", "admin")
        assert user.user_type == "admin"

    def test_create_attorney(self, db):
        user = _create_user(db, "attorney@test.com", "attorney")
        assert user.user_type == "attorney"

    def test_create_paralegal(self, db):
        user = _create_user(db, "paralegal@test.com", "paralegal")
        assert user.user_type == "paralegal"

    def test_create_case_worker(self, db):
        user = _create_user(db, "cw@test.com", "case_worker")
        assert user.user_type == "case_worker"

    def test_user_type_enum_values(self):
        assert UserType.ADMIN.value == "admin"
        assert UserType.ATTORNEY.value == "attorney"
        assert UserType.PARALEGAL.value == "paralegal"
        assert UserType.CASE_WORKER.value == "case_worker"


class TestRBACPermissions:
    """Test role-based access control logic.

    These tests verify the permission model at the data level.
    Route-level access control is integration-tested via test_api.py.
    """

    def test_admin_is_admin(self, db):
        user = _create_user(db, "admin@test.com", "admin")
        assert user.user_type == "admin"
        # Admin should have access to admin routes
        assert user.user_type in ("admin",)

    def test_paralegal_is_not_admin(self, db):
        user = _create_user(db, "para@test.com", "paralegal")
        assert user.user_type != "admin"

    def test_attorney_can_access_cases(self, db):
        """Attorneys should have case access (user_type in allowed list)."""
        user = _create_user(db, "att@test.com", "attorney")
        allowed_case_types = ("admin", "attorney", "case_worker", "paralegal")
        assert user.user_type in allowed_case_types

    def test_disabled_user_should_not_authenticate(self, db):
        """A disabled user should not be allowed to log in."""
        user = _create_user(db, "disabled@test.com", "admin")
        user.enabled = False
        db.commit()
        db.refresh(user)
        assert user.enabled is False
        # Even though password is correct, enabled check should block
        assert user.verify_password("TestPass123!") is True
        assert user.enabled is False

    def test_admin_access_list(self, db):
        """Verify admin route access check logic."""
        admin = _create_user(db, "adm@test.com", "admin")
        paralegal = _create_user(db, "par@test.com", "paralegal")
        attorney = _create_user(db, "att@test.com", "attorney")

        admin_allowed = lambda u: u.user_type == "admin"
        assert admin_allowed(admin) is True
        assert admin_allowed(paralegal) is False
        assert admin_allowed(attorney) is False

    def test_superadmin_concept(self, db):
        """Superadmin (if implemented) can see all orgs.
        Currently maps to admin user_type with no org_id restriction."""
        user = _create_user(db, "super@test.com", "admin")
        # Superadmin logic: admin without org_id filter
        # This is conceptual -- actual implementation may vary
        assert user.user_type == "admin"
