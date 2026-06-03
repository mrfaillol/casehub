"""Regression tests for routes/maestro_learn — feature-flag + ownership.

The Maestro Learning Space endpoints under ``/casehub/maestro/learn`` are
gated behind ``CASEHUB_MAESTRO_LEARNING_ENABLED`` (default: off) and own
a per-user corpus. Three risk surfaces matter here:

1. **Flag posture**: when disabled, EVERY endpoint must short-circuit
   to ``503`` before touching the DB — never accidentally exercise the
   feature.
2. **Ownership**: a user from org A must never see, edit or delete an
   entry that belongs to a different user (audit-#514 red line).
3. **Quotas**: the per-user cap protects the chat token budget;
   ``content`` size cap protects the request body limit.

Run: pytest tests/test_maestro_learn_routes.py
"""
from __future__ import annotations

import asyncio
import json
import os
from types import SimpleNamespace

import pytest

import routes.maestro_learn as ml
from models import MaestroLearningEntry


_ORG_ID = 21


def _make_request(org_id=_ORG_ID):
    """Minimal request stub exposing ``state.org_id`` (what the routes read)."""
    request = SimpleNamespace()
    request.state = SimpleNamespace(org_id=org_id)
    request.cookies = {}
    return request


def _patch_auth(monkeypatch, user):
    monkeypatch.setattr(ml, "get_current_user", lambda req, db: user)


def _enable_flag(monkeypatch, enabled=True):
    monkeypatch.setenv(
        "CASEHUB_MAESTRO_LEARNING_ENABLED",
        "1" if enabled else "",
    )


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _decode(response):
    return json.loads(response.body)


@pytest.fixture
def fake_user():
    return SimpleNamespace(id=101, email="a@example.com")


# ---------------------------------------------------------------------------
# Feature flag — disabled posture
# ---------------------------------------------------------------------------


def test_create_returns_503_when_flag_disabled(db, monkeypatch, fake_user):
    """Disabled feature short-circuits to 503 *before* DB work — protects
    the alpha posture (Maestro pipeline off until Council ruling)."""
    _enable_flag(monkeypatch, enabled=False)
    _patch_auth(monkeypatch, fake_user)

    payload = ml.LearningEntryCreate(content="hello")
    response = _run(ml.create_learning_entry(_make_request(), payload, db))

    assert response.status_code == 503
    body = _decode(response)
    assert body["error"] == "feature_disabled"
    # No row should have been written.
    count = db.query(MaestroLearningEntry).count()
    assert count == 0


def test_list_returns_503_when_flag_disabled(db, monkeypatch, fake_user):
    _enable_flag(monkeypatch, enabled=False)
    _patch_auth(monkeypatch, fake_user)

    response = _run(ml.list_learning_entries(_make_request(), db=db))
    assert response.status_code == 503


def test_get_returns_503_when_flag_disabled(db, monkeypatch, fake_user):
    _enable_flag(monkeypatch, enabled=False)
    _patch_auth(monkeypatch, fake_user)

    response = _run(ml.get_learning_entry(_make_request(), 1, db=db))
    assert response.status_code == 503


def test_delete_returns_503_when_flag_disabled(db, monkeypatch, fake_user):
    _enable_flag(monkeypatch, enabled=False)
    _patch_auth(monkeypatch, fake_user)

    response = _run(ml.delete_learning_entry(_make_request(), 1, db=db))
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# Happy path — create + list + get + update + delete (flag ENABLED)
# ---------------------------------------------------------------------------


def test_create_list_get_update_delete_roundtrip(db, monkeypatch, fake_user):
    """The full CRUD cycle works against the in-memory SQLite when the
    feature flag is enabled — guards against schema regressions."""
    _enable_flag(monkeypatch, enabled=True)
    _patch_auth(monkeypatch, fake_user)

    # CREATE
    payload = ml.LearningEntryCreate(
        title="Glossário OAB",
        content="EB-2 NIW = National Interest Waiver",
        source="manual",
        tags=["oab", "visa"],
    )
    resp_create = _run(ml.create_learning_entry(_make_request(), payload, db))
    assert resp_create.status_code == 201
    created = _decode(resp_create)
    entry_id = created["id"]
    assert created["title"] == "Glossário OAB"
    assert created["tags"] == ["oab", "visa"]
    assert created["enabled"] is True

    # LIST
    resp_list = _run(ml.list_learning_entries(_make_request(), db=db))
    body = _decode(resp_list)
    assert body["total"] == 1
    assert body["items"][0]["id"] == entry_id

    # GET
    resp_get = _run(ml.get_learning_entry(_make_request(), entry_id, db=db))
    fetched = _decode(resp_get)
    assert fetched["id"] == entry_id

    # UPDATE — partial (only enabled)
    upd = ml.LearningEntryUpdate(enabled=False)
    resp_upd = _run(ml.update_learning_entry(_make_request(), entry_id, upd, db))
    updated = _decode(resp_upd)
    assert updated["enabled"] is False
    assert updated["title"] == "Glossário OAB"  # not changed

    # DELETE
    resp_del = _run(ml.delete_learning_entry(_make_request(), entry_id, db=db))
    assert _decode(resp_del)["deleted"] is True

    # GET after delete -> 404
    resp_get2 = _run(ml.get_learning_entry(_make_request(), entry_id, db=db))
    assert resp_get2.status_code == 404


# ---------------------------------------------------------------------------
# Ownership — cross-user isolation (audit-#514 red line)
# ---------------------------------------------------------------------------


def test_get_other_users_entry_returns_404_not_403(db, monkeypatch):
    """A user must NOT be able to fetch another user's entry by id — and
    the response must be 404 (not 403), so an attacker cannot enumerate
    other users' entry ids by status code.

    This is the audit-#514 red line for per-user data: never leak
    existence across owners."""
    _enable_flag(monkeypatch, enabled=True)

    # User A creates an entry
    user_a = SimpleNamespace(id=201, email="a@example.com")
    _patch_auth(monkeypatch, user_a)
    payload = ml.LearningEntryCreate(content="user A's note")
    resp = _run(ml.create_learning_entry(_make_request(), payload, db))
    entry_id = _decode(resp)["id"]

    # User B (same org) tries to read it
    user_b = SimpleNamespace(id=202, email="b@example.com")
    _patch_auth(monkeypatch, user_b)
    resp_b = _run(ml.get_learning_entry(_make_request(), entry_id, db=db))
    assert resp_b.status_code == 404

    # User B tries to delete it
    resp_b_del = _run(ml.delete_learning_entry(_make_request(), entry_id, db=db))
    assert resp_b_del.status_code == 404


def test_list_only_returns_own_entries(db, monkeypatch):
    """``list`` MUST filter by user_id — cross-user leakage in the list
    endpoint would be the worst failure mode (one request leaks everyone)."""
    _enable_flag(monkeypatch, enabled=True)

    # User A creates 2 entries
    user_a = SimpleNamespace(id=301, email="a@example.com")
    _patch_auth(monkeypatch, user_a)
    for i in range(2):
        _run(ml.create_learning_entry(
            _make_request(), ml.LearningEntryCreate(content=f"A-{i}"), db,
        ))

    # User B creates 1 entry
    user_b = SimpleNamespace(id=302, email="b@example.com")
    _patch_auth(monkeypatch, user_b)
    _run(ml.create_learning_entry(
        _make_request(), ml.LearningEntryCreate(content="B-only"), db,
    ))

    # B's list should show only B's 1 entry
    resp_b = _run(ml.list_learning_entries(_make_request(), db=db))
    body_b = _decode(resp_b)
    assert body_b["total"] == 1
    assert body_b["items"][0]["content"] == "B-only"


# ---------------------------------------------------------------------------
# Quota — per-user cap
# ---------------------------------------------------------------------------


def test_create_returns_409_when_per_user_cap_reached(db, monkeypatch, fake_user):
    """The 201st entry for one user MUST be rejected with 409 —
    protects the chat token budget."""
    _enable_flag(monkeypatch, enabled=True)
    _patch_auth(monkeypatch, fake_user)

    # Skip the slow path: seed MAX_ENTRIES_PER_USER rows directly.
    for i in range(ml.MAX_ENTRIES_PER_USER):
        db.add(MaestroLearningEntry(
            org_id=_ORG_ID,
            user_id=fake_user.id,
            title=f"e{i}",
            content="x",
            source="manual",
            tags=[],
            enabled=True,
        ))
    db.commit()

    # The next create should fail
    resp = _run(ml.create_learning_entry(
        _make_request(),
        ml.LearningEntryCreate(content="one too many"),
        db,
    ))
    assert resp.status_code == 409
    assert _decode(resp)["error"] == "quota_exceeded"
