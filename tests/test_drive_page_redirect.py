"""Regression tests for routes/drive_upload — the ``GET {PREFIX}/drive`` redirect.

Background (Escritorio Demo alpha, 2026-06-15 / handoff 02): the shell "Drive"
menu points at ``{PREFIX}/documents`` (the column-view explorer), but there
was no page handler mounted on ``/drive``. Only ``POST /drive/upload-from-document``
and the JSON ``/api/drive/*`` surface existed, so anyone who *typed* or
followed ``{PREFIX}/drive`` directly got a 404 (UsuarioDemo hit this).

These tests pin:

1. ``GET /drive`` is no longer a 404 — it redirects to ``{PREFIX}/documents``.
2. The redirect is a 3xx with an absolute Location under ``{PREFIX}``.
3. A ``client_id`` query param is carried through to ``/documents`` so
   ``/drive?client_id=N`` opens the explorer rooted at that client's folder.
4. The redirect handler does not require auth or DB (``/documents`` already
   gates login) — so it never forms a redirect loop here.

The handler is tested in isolation by mounting only the ``drive_upload``
router on a minimal FastAPI app: the redirect path touches neither the DB nor
Google Drive, so no real API / token is involved.

Run: pytest tests/test_drive_page_redirect.py
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routes.drive_upload as drive_upload
from core.template_config import PREFIX


@pytest.fixture
def client():
    """Minimal app with only the drive_upload router mounted under PREFIX."""
    app = FastAPI()
    app.include_router(drive_upload.router, prefix=PREFIX)
    # follow_redirects=False so we can assert on the 3xx itself, not the
    # (auth-gated) /documents target.
    return TestClient(app, follow_redirects=False)


def test_drive_page_is_not_404(client):
    """GET {PREFIX}/drive must not 404 anymore — it redirects."""
    resp = client.get(f"{PREFIX}/drive")
    assert resp.status_code != 404
    assert 300 <= resp.status_code < 400


def test_drive_page_redirects_to_documents(client):
    """The redirect target is the real explorer at {PREFIX}/documents."""
    resp = client.get(f"{PREFIX}/drive")
    assert resp.status_code == 307
    location = resp.headers["location"]
    assert location == f"{PREFIX}/documents"


def test_drive_page_preserves_client_id(client):
    """/drive?client_id=N forwards the client_id to /documents."""
    resp = client.get(f"{PREFIX}/drive", params={"client_id": 42})
    assert 300 <= resp.status_code < 400
    location = resp.headers["location"]
    assert location.startswith(f"{PREFIX}/documents")
    assert "client_id=42" in location


def test_drive_page_no_client_id_has_clean_target(client):
    """Without client_id the redirect target carries no query string."""
    resp = client.get(f"{PREFIX}/drive")
    location = resp.headers["location"]
    assert "?" not in location


def test_drive_redirect_needs_no_auth_or_db(client):
    """The redirect handler resolves without a DB session or logged-in user.

    The previous absence of any page handler meant 404; the new handler is a
    pure redirect (auth is enforced downstream by /documents), so the request
    completes with a 3xx even with no auth cookie and no DB wiring on the
    minimal test app.
    """
    resp = client.get(f"{PREFIX}/drive")
    assert resp.status_code == 307
