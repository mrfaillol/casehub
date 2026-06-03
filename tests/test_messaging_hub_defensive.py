"""Regression tests for MessagingHubService defensive degradation.

Discovered by the self-hosted P0 smoke (PR #588): the messaging routes
500 on a fresh DB because their raw-SQL queries hit ``unified_messages``
/ ``email_accounts`` tables that aren't declared as SQLAlchemy models.
Same defect class as portal_access (PR #572).

These tests pin the new defensive contract on three service methods:

- ``get_threads`` → empty list when ``unified_messages`` missing
- ``get_unread_counts`` → zero-counts dict (with ``total: 0``) when missing
- ``get_channel_status`` → "0 accounts" string when ``email_accounts`` missing

The session is rolled back on each failure so subsequent ORM work on
the same request does not raise PendingRollbackError.

Run: pytest tests/test_messaging_hub_defensive.py
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from services.messaging_hub_service import MessagingHubService


_ORG_ID = 51


def _install_failing_execute(db, monkeypatch, exc_cls, table_marker: str):
    """Replace db.execute with a stub that raises ``exc_cls`` whenever
    the SQL string contains ``table_marker``. Mimics Postgres'
    UndefinedTable / SQLite OperationalError without needing the table
    to actually exist.

    Returns a state dict so the test can assert ``rollbacks`` count.
    """
    state = {"rollbacks": 0}
    real_execute = db.execute
    real_rollback = db.rollback

    def fake_execute(statement, *args, **kwargs):
        if table_marker in str(statement):
            raise exc_cls(str(statement), {}, Exception(f"no such table: {table_marker}"))
        return real_execute(statement, *args, **kwargs)

    def fake_rollback():
        state["rollbacks"] += 1
        return real_rollback()

    monkeypatch.setattr(db, "execute", fake_execute)
    monkeypatch.setattr(db, "rollback", fake_rollback)
    return state


def test_get_threads_returns_empty_when_unified_messages_missing(db, monkeypatch):
    """``unified_messages`` is the source-of-truth table for the
    messaging thread list. When it's absent, ``get_threads`` must
    degrade to an empty list (not 500)."""
    state = _install_failing_execute(db, monkeypatch, OperationalError, "unified_messages")

    service = MessagingHubService(db, org_id=_ORG_ID)
    threads = service.get_threads(limit=50)

    assert threads == [], (
        "get_threads must return [] when unified_messages is missing, "
        "not raise. Required so the messaging page renders 'no conversations'."
    )
    assert state["rollbacks"] == 1, (
        "Failed execute must trigger db.rollback() — otherwise the next "
        "ORM query on this session raises PendingRollbackError."
    )


def test_get_threads_handles_programming_error_too(db, monkeypatch):
    """Postgres raises ProgrammingError (UndefinedTable subclass).
    Both paths must degrade identically."""
    state = _install_failing_execute(db, monkeypatch, ProgrammingError, "unified_messages")

    service = MessagingHubService(db, org_id=_ORG_ID)
    threads = service.get_threads()

    assert threads == []
    assert state["rollbacks"] == 1


def test_get_unread_counts_returns_zero_dict_when_table_missing(db, monkeypatch):
    """The unread badge needs ``total`` and per-channel keys present
    even when the table is missing. Without this guard the messaging
    hub page header would 500 trying to read ``unread_counts['total']``.
    """
    state = _install_failing_execute(db, monkeypatch, OperationalError, "unified_messages")

    service = MessagingHubService(db, org_id=_ORG_ID)
    counts = service.get_unread_counts()

    assert counts == {
        "whatsapp": 0,
        "email": 0,
        "sms": 0,
        "call": 0,
        "total": 0,
    }, "Zero-counts dict must include all channels + total."
    assert state["rollbacks"] == 1


def test_get_channel_status_falls_back_to_zero_accounts(db, monkeypatch):
    """``email_accounts`` is a raw-migration table. On a fresh deploy
    the SELECT raises; the channel status panel must still render.

    The WhatsApp / SMS / Call branches are independent — only the
    email row falls back to "0 accounts"."""
    state = _install_failing_execute(db, monkeypatch, ProgrammingError, "email_accounts")

    service = MessagingHubService(db, org_id=_ORG_ID)
    status = service.get_channel_status()

    assert status["email"] == "0 accounts", (
        "Email status must say '0 accounts' (not raise) when "
        "email_accounts table is missing."
    )
    assert "whatsapp" in status
    assert state["rollbacks"] == 1


def test_existing_553_shape_contract_preserved(db, monkeypatch):
    """Sanity guard: the defensive wrappers must not break the
    return-shape contract PR #553 locked in. The defect class is a
    table-missing failure, not a shape change."""
    # When the table EXISTS but is empty, the shape must stay the same.
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS unified_messages ("
        "  id INTEGER PRIMARY KEY,"
        "  channel TEXT,"
        "  is_read BOOLEAN,"
        "  direction TEXT"
        ")"
    ))
    db.commit()
    try:
        service = MessagingHubService(db, org_id=_ORG_ID)
        counts = service.get_unread_counts()
        # PR #553 contract: dict has exactly these keys.
        assert set(counts) == {"whatsapp", "email", "sms", "call", "total"}
    finally:
        db.execute(text("DROP TABLE IF EXISTS unified_messages"))
        db.commit()
