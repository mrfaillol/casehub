"""HTTP-layer tests for routes/integrations_gateway.py — admin-only status.

These need the app stack (FastAPI / SQLAlchemy) and run under the normal
pytest conftest. The router is mounted on a minimal app; the current user and
the audit sink are swapped via monkeypatch so no real auth or DB write is hit.
"""
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

STATUS_URL = "/casehub/integrations/gateway/status"


def _user(user_type, uid, email):
    user = MagicMock()
    user.id = uid
    user.email = email
    user.user_type = user_type
    return user


@pytest.fixture
def make_client(db, monkeypatch):
    """Return a builder: make_client(user, captured=None) -> TestClient.

    `user` is what the route's get_current_user resolves to (None for
    unauthenticated). When `captured` (a list) is passed, log_action calls are
    recorded into it instead of touching the audit table.
    """
    from routes import integrations_gateway as route_mod

    def _build(user, captured=None):
        def _get_db_override():
            yield db

        monkeypatch.setattr(route_mod, "get_current_user", lambda request, _db: user)
        if captured is not None:
            monkeypatch.setattr(
                route_mod, "log_action", lambda _db, **kwargs: captured.append(kwargs)
            )
        app = FastAPI()
        app.include_router(route_mod.router, prefix="/casehub")
        app.dependency_overrides[route_mod.get_db] = _get_db_override
        return TestClient(app)

    return _build


def test_status_requires_authentication(make_client):
    resp = make_client(None).get(STATUS_URL)
    assert resp.status_code == 401
    assert resp.json()["error"] == "auth_required"


def test_status_forbidden_for_non_admin(make_client):
    member = _user("member", 2, "member@test.com")
    resp = make_client(member).get(STATUS_URL)
    assert resp.status_code == 403
    assert resp.json()["error"] == "admin_required"


def test_status_admin_sees_three_disabled_providers(make_client):
    admin = _user("admin", 1, "admin@test.com")
    resp = make_client(admin).get(STATUS_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["gateway_enabled"] is False
    assert body["default_off"] is True
    assert body["provider_count"] == 3
    names = {p["provider_name"] for p in body["providers"]}
    assert names == {"google-calendar", "gmail", "google-drive"}
    for provider in body["providers"]:
        assert provider["status"] == "disabled"
        assert provider["enabled"] is False
        assert provider["configured"] is False


def test_status_response_leaks_no_credential_ref(make_client):
    admin = _user("admin", 1, "admin@test.com")
    resp = make_client(admin).get(STATUS_URL)
    assert resp.status_code == 200
    text = resp.text
    assert "credential_ref" not in text
    assert "secret" not in text.lower()


def test_status_audit_log_is_body_free(make_client):
    admin = _user("admin", 1, "admin@test.com")
    captured = []
    resp = make_client(admin, captured=captured).get(STATUS_URL)
    assert resp.status_code == 200
    assert len(captured) == 1
    call = captured[0]
    assert call["action"] == "gateway.status.read"
    assert call["entity_type"] == "integration_gateway"
    assert call["user_id"] == 1
    # audit details carry counts/flags only — no provider bodies or refs
    assert set(call["details"]) == {"provider_count", "gateway_enabled"}
    assert call["details"]["provider_count"] == 3
