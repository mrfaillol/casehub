"""
Tests for routes/improvement_tasks.py - the cmd.vingren.me ingest receiver.

Authority: ruling 2026-05-06-cmd-control-center-activation
"""
import hashlib
import hmac
import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services import improvement_task_service
from models.improvement_task import ImprovementTask


HMAC_KEY = "test-hmac-key-32-bytes-minimum-length-12345"


@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    """Activate the feature flag and HMAC key for every test."""
    monkeypatch.setenv("CASEHUB_IMPROVEMENT_HMAC_KEY", HMAC_KEY)
    monkeypatch.setenv("CASEHUB_IMPROVEMENT_TASKS_ENABLED", "1")


@pytest.fixture
def client(db):
    """Mount only the improvement_tasks router on a minimal FastAPI app.

    Use FastAPI's dependency_overrides on the route module's bound `get_db`
    symbol — monkeypatching `models.get_db` would not affect the already-
    resolved `Depends(get_db)` at route definition time.
    """
    from routes import improvement_tasks as route_mod

    def _get_db_override():
        try:
            yield db
        finally:
            pass

    app = FastAPI()
    app.include_router(route_mod.router, prefix="/casehub")
    app.dependency_overrides[route_mod.get_db] = _get_db_override
    return TestClient(app)


def _sign(body: bytes, key: str = HMAC_KEY) -> str:
    return hmac.new(key.encode(), body, hashlib.sha256).hexdigest()


def _post(client: TestClient, payload: dict, *, sign: bool = True, key: str = HMAC_KEY):
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if sign:
        headers["X-CMD-Ingest-Signature"] = _sign(body, key)
    return client.post("/casehub/api/v1/improvement-tasks", content=body, headers=headers)


# ----------------------------------------------------------------------------
# Service-layer tests (no HTTP, direct DB)
# ----------------------------------------------------------------------------

def test_service_create_task_idempotent(db):
    task1 = improvement_task_service.create_task(
        db, envelope_ref="svc-001", kind="ui-polish", title="First"
    )
    task2 = improvement_task_service.create_task(
        db, envelope_ref="svc-001", kind="ui-polish", title="Second (ignored)"
    )
    assert task1.id == task2.id
    assert task1.title == "First"


def test_service_template_refactor_is_quarantined(db):
    task = improvement_task_service.create_task(
        db, envelope_ref="svc-002", kind="template-refactor", title="HALT-blocked"
    )
    assert task.halt_blocked is True
    assert task.status == "quarantined"
    assert "HALT" in (task.failure_reason or "")


def test_service_normal_kind_received(db):
    task = improvement_task_service.create_task(
        db, envelope_ref="svc-003", kind="ui-polish", title="Should be received"
    )
    assert task.halt_blocked is False
    assert task.status == "received"


def test_service_priority_normalized(db):
    t1 = improvement_task_service.create_task(db, envelope_ref="svc-p1", kind="ui-polish", title="x", priority="P0")
    t2 = improvement_task_service.create_task(db, envelope_ref="svc-p2", kind="ui-polish", title="x", priority="invalid")
    assert t1.priority == "P0"
    assert t2.priority == "P2"


def test_service_mark_dispatched(db):
    task = improvement_task_service.create_task(db, envelope_ref="svc-d1", kind="ui-polish", title="x")
    updated = improvement_task_service.mark_dispatched(db, task.id, "https://github.com/mrfaillol/casehub-prod/pull/999")
    assert updated.status == "dispatched"
    assert updated.dispatch_url.endswith("/pull/999")
    assert updated.dispatched_at is not None


def test_service_mark_completed(db):
    task = improvement_task_service.create_task(db, envelope_ref="svc-c1", kind="ui-polish", title="x")
    improvement_task_service.mark_dispatched(db, task.id, "url")
    updated = improvement_task_service.mark_completed(db, task.id)
    assert updated.status == "done"
    assert updated.completed_at is not None


# ----------------------------------------------------------------------------
# HTTP-level tests
# ----------------------------------------------------------------------------

def test_post_with_valid_hmac_creates_task(client):
    payload = {
        "envelope_ref": "test-env-001",
        "kind": "ui-polish",
        "title": "Adjust dashboard spacing",
        "summary": "Smoke test from intake-triage",
        "requested_runtime": "claude",
        "skill": "pixel-perfect-auditor",
        "priority": "P2",
    }
    resp = _post(client, payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["ok"] is True
    assert data["envelope_ref"] == "test-env-001"
    assert data["status"] == "received"
    assert data["halt_blocked"] is False
    assert "task_id" in data


def test_post_idempotent_on_envelope_ref(client):
    payload = {
        "envelope_ref": "test-env-002",
        "kind": "ui-polish",
        "title": "First",
    }
    r1 = _post(client, payload)
    assert r1.status_code == 201
    first_id = r1.json()["task_id"]

    payload2 = {**payload, "title": "Second (should be ignored)"}
    r2 = _post(client, payload2)
    assert r2.status_code == 200
    assert r2.json().get("duplicate") is True
    assert r2.json()["task_id"] == first_id


def test_post_rejects_bad_hmac(client):
    payload = {"envelope_ref": "test-env-003", "kind": "ui-polish", "title": "Bad sig"}
    body = json.dumps(payload).encode()
    headers = {
        "Content-Type": "application/json",
        "X-CMD-Ingest-Signature": "0" * 64,
    }
    resp = client.post("/casehub/api/v1/improvement-tasks", content=body, headers=headers)
    assert resp.status_code == 401


def test_post_rejects_missing_signature(client):
    payload = {"envelope_ref": "test-env-004", "kind": "ui-polish", "title": "No sig"}
    resp = _post(client, payload, sign=False)
    assert resp.status_code == 401


def test_post_rejects_missing_envelope_ref(client):
    payload = {"kind": "ui-polish", "title": "Missing envelope_ref"}
    resp = _post(client, payload)
    assert resp.status_code == 400


def test_post_rejects_invalid_kind(client):
    payload = {"envelope_ref": "test-env-005", "kind": "Bad Kind With Spaces", "title": "x"}
    resp = _post(client, payload)
    assert resp.status_code == 400


def test_template_refactor_is_halt_blocked(client):
    payload = {
        "envelope_ref": "test-env-006",
        "kind": "template-refactor",
        "title": "Should be HALT-blocked",
    }
    resp = _post(client, payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["halt_blocked"] is True
    assert data["status"] == "quarantined"


def test_post_payload_too_large_rejected(client):
    big = {
        "envelope_ref": "test-env-007",
        "kind": "ui-polish",
        "title": "oversized",
        "payload": {"data": "x" * 300_000},
    }
    resp = _post(client, big)
    assert resp.status_code == 413


def test_disabled_returns_503(client, monkeypatch):
    """When the feature flag is off, all endpoints return 503."""
    monkeypatch.setenv("CASEHUB_IMPROVEMENT_TASKS_ENABLED", "0")
    payload = {"envelope_ref": "test-disabled", "kind": "ui-polish", "title": "x"}
    resp = _post(client, payload)
    assert resp.status_code == 503
    assert "disabled" in resp.json()["detail"].lower()
