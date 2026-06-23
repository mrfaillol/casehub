"""
CaseHub - 2FA self-healing schema tests.

The 2FA feature shipped without a migration. Environments that were not
manually patched lacked the totp_* columns on `users` and the `backup_codes`
table, so get_2fa_status raised SQLAlchemyError and the UI showed
"2FA temporariamente indisponivel". These tests prove that against a fresh DB
WITHOUT the 2FA schema, the public service methods auto-create the (additive,
idempotent) schema and then return a valid status.
"""
import pytest
from sqlalchemy import text

from models.user import User
from services.two_factor import TwoFactorService


def _columns(db, table):
    return {row[1] for row in db.execute(text(f"PRAGMA table_info({table})")).fetchall()}


def _table_exists(db, table):
    return bool(db.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
        {"t": table},
    ).first())


@pytest.fixture
def _clear_schema_guard():
    """The ensure runs once per engine; clear the guard so each test exercises
    the self-heal path against the freshly-created (per-test) tables."""
    TwoFactorService._schema_ensured.clear()
    yield
    TwoFactorService._schema_ensured.clear()


def _make_user(db):
    user = User(
        email="2fa@test.com",
        name="2FA User",
        password_hash="x",
        user_type="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_fresh_db_lacks_2fa_schema(db):
    """Sanity: the User model / metadata does NOT define the 2FA schema, so a
    fresh DB is missing exactly the bits the bug was about."""
    cols = _columns(db, "users")
    assert "totp_secret" not in cols
    assert "totp_enabled" not in cols
    assert not _table_exists(db, "backup_codes")


def test_get_2fa_status_self_heals(_clear_schema_guard, db):
    """get_2fa_status against a DB without the 2FA schema must auto-create it
    and return a valid (non-unavailable) status — not raise."""
    user = _make_user(db)
    service = TwoFactorService(db)

    status = service.get_2fa_status(user.id)

    # Schema was created lazily.
    cols = _columns(db, "users")
    assert {"totp_secret", "totp_enabled", "totp_setup_at", "totp_verified_at"} <= cols
    assert _table_exists(db, "backup_codes")
    assert "ix_backup_codes_user_id" in {
        row[1] for row in db.execute(text("PRAGMA index_list('backup_codes')")).fetchall()
    }

    # Valid status (the route's unavailable_status() fallback is NOT triggered).
    assert status["enabled"] is False
    assert status["setup_at"] is None
    assert status["backup_codes_remaining"] == 0


def test_ensure_creates_usable_schema(_clear_schema_guard, db):
    """After ensure, the totp columns and backup_codes table are usable for the
    actual 2FA queries (insert/update/select round-trip)."""
    user = _make_user(db)
    service = TwoFactorService(db)

    service._ensure_2fa_schema()

    # totp_secret column is writable (the column the bug was missing).
    db.execute(
        text("UPDATE users SET totp_secret = :s, totp_enabled = true WHERE id = :id"),
        {"s": "ABC123", "id": user.id},
    )
    db.commit()
    # backup_codes table accepts inserts and the FK column.
    db.execute(
        text("INSERT INTO backup_codes (user_id, code, used) VALUES (:u, :c, false)"),
        {"u": user.id, "c": "DEADBEEF"},
    )
    db.commit()

    status = service.get_2fa_status(user.id)
    assert status["enabled"]  # truthy (SQLite stores BOOLEAN as 0/1)
    assert status["backup_codes_remaining"] == 1


def test_ensure_is_idempotent(_clear_schema_guard, db):
    """Calling ensure many times is safe and preserves data (no DROP)."""
    user = _make_user(db)
    service = TwoFactorService(db)

    service._ensure_2fa_schema()
    db.execute(
        text("UPDATE users SET totp_secret = :s WHERE id = :id"),
        {"s": "KEEPME", "id": user.id},
    )
    db.commit()

    # Re-run ensure repeatedly; data must survive, no exception.
    for _ in range(3):
        TwoFactorService._schema_ensured.clear()
        service._ensure_2fa_schema()

    still = db.execute(
        text("SELECT totp_secret FROM users WHERE id = :id"), {"id": user.id}
    ).scalar()
    assert still == "KEEPME"  # additive ensure did not wipe the column/data
