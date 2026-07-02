"""Regression: the LIVE /casehub/integrations route must pass org_id/db.

core/v2_canonical_routes.py::register_canonical_routes registers a route at
the exact same path (``{PREFIX}/integrations``) as routes/integrations.py's
``integrations_index`` — and FastAPI/Starlette route matching is
first-registered-wins for an exact path+method match. Since
``register_canonical_routes`` is called BEFORE the legacy router
include_router() loop in core/app_factory.create_app(), the canonical
handler always wins for this path; ``integrations_index`` is dead code for
it. Before this fix, the canonical handler called
``routes.integrations._integration_cards()`` with ZERO arguments, so
``org_id``/``db`` were always ``None`` regardless of what TenantMiddleware
resolved on ``request.state.org_id`` — this silently degraded every
integration card that depends on tenant context (e.g. the Google Drive root
folder lookup, Gmail OAuth per-org accounts).

This test builds the REAL app via ``core.app_factory.create_app()`` (same
call production uses) so both routers are registered exactly as they are in
prod, drives a real login, and:
  1. confirms which handler wins the route table for this exact path
     (guards against a future re-shadowing regressing which fix applies);
  2. spies on ``routes.integrations._integration_cards`` to prove the
     canonical handler calls it with the REAL (org_id, db) — not zero args.
"""
from __future__ import annotations

import os
import uuid as _uuid

os.environ.setdefault("CASEHUB_PRODUCT", "lite")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-integ-canon-32chars!")
os.environ.setdefault(
    "ENCRYPTION_KEY",
    "dGVzdC1lbmNyeXB0aW9uLWtleS1mb3ItdGVzdHMxMjM=",
)

import bcrypt
import pytest


@pytest.fixture(scope="module")
def app_and_client():
    from fastapi.testclient import TestClient
    from core.app_factory import create_app

    app = create_app("lite")
    with TestClient(
        app,
        follow_redirects=False,
        headers={"host": "integcanon.casehub.legal"},
    ) as client:
        yield app, client


@pytest.fixture(scope="module")
def seeded_user(app_and_client) -> dict:
    from models.base import SessionLocal
    from models.tenant import Organization
    from models.user import User

    email = "smoke@integcanon.test"
    password = "IntegCanonSmoke!2026"

    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == "integcanon").first()
        if org is None:
            org = Organization(
                uuid=str(_uuid.uuid4()),
                name="Integ Canon Smoke Org",
                slug="integcanon",
                domain="integcanon.casehub.legal",
                is_active=True,
            )
            db.add(org)
            db.flush()

        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(
                email=email,
                name="Integ Canon Smoke",
                password_hash=bcrypt.hashpw(
                    password.encode("utf-8"), bcrypt.gensalt()
                ).decode("utf-8"),
                user_type="admin",
                enabled=True,
                must_change_password=False,
                org_id=org.id,
            )
            db.add(user)
        db.commit()
        org_id = org.id
    finally:
        db.close()

    return {"email": email, "password": password, "org_id": org_id}


def _login(client, creds: dict):
    resp = client.post(
        "/casehub/login",
        data={"email": creds["email"], "password": creds["password"]},
    )
    return resp.cookies.get("casehub_token")


def test_integrations_route_resolves_to_canonical_handler(app_and_client):
    """Route-table sanity: whichever handler wins for this exact path must
    be the one this test (and the fix) actually targets. If this starts
    failing because the legacy ``integrations_index`` wins instead, the
    other assertion in this file stops being meaningful and must be
    re-pointed."""
    app, _ = app_and_client
    matches = [
        r for r in app.routes
        if getattr(r, "path", None) == "/casehub/integrations"
        and "GET" in getattr(r, "methods", set())
    ]
    assert matches, "no route registered for /casehub/integrations"
    winner = matches[0]
    assert winner.endpoint.__qualname__.startswith("register_canonical_routes"), (
        f"expected the canonical route to win first-match, got "
        f"{winner.endpoint.__module__}.{winner.endpoint.__qualname__} instead — "
        "if this is now routes.integrations.integrations_index, the org_id "
        "fix needs to move back to that file."
    )


def test_integrations_canon_passes_real_org_id_and_db(
    app_and_client, seeded_user, monkeypatch,
):
    """The actual regression: hit the real registered path end-to-end and
    confirm the canonical handler invokes `_integration_cards` with the
    REAL org_id + a real Session, not `_integration_cards()` (zero args,
    pre-fix behavior — which always resolved to org_id=None/db=None
    regardless of TenantMiddleware)."""
    import routes.integrations as integrations_mod

    calls = []
    _real_cards = integrations_mod._integration_cards

    def _spy_cards(org_id=None, db=None):
        calls.append({"org_id": org_id, "db": db})
        return _real_cards(org_id, db)

    monkeypatch.setattr(integrations_mod, "_integration_cards", _spy_cards)

    _, client = app_and_client
    token = _login(client, seeded_user)
    assert token, "login did not set casehub_token cookie — auth flow regressed"

    resp = client.get("/casehub/integrations")
    assert resp.status_code == 200, resp.text

    assert calls, (
        "routes.integrations._integration_cards was never invoked — "
        "core/v2_canonical_routes.py's integrations_canon route is not "
        "delegating to it at all."
    )
    assert calls[0]["org_id"] == seeded_user["org_id"], (
        "core/v2_canonical_routes.py:integrations_canon must pass the real "
        "tenant org_id (from request.state.org_id) to _integration_cards — "
        "pre-fix it called _integration_cards() with zero args, so org_id "
        "was always None regardless of what TenantMiddleware resolved."
    )
    assert calls[0]["db"] is not None, (
        "integrations_canon must pass the real DB session to "
        "_integration_cards — pre-fix it was always None."
    )
