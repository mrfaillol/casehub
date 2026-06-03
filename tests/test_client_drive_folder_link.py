"""Regression tests for routes/clients — per-client Drive folder linking.

The Client model has carried ``drive_folder_id`` + ``drive_folder_name``
columns for some time, but no route persisted them. The GET endpoint
derived the folder from the client's name (``LASTNAME, First - VISA``)
via Drive search — brittle: any rename, missing visa_type, or Drive
ACL change broke it. Goal frente C ("Drive POR CLIENTE: vincular
client_id ↔ Drive folder") needs an **explicit** persisted link.

These tests pin:

1. **URL parser**: bare id, three Drive URL shapes, and rejection of
   garbage. The UI lets lawyers paste a folder link (much more common
   than pasting a bare id).
2. **POST persists**: a valid id (or URL) lands in
   ``client.drive_folder_id`` + ``drive_folder_name``.
3. **POST unlink**: empty ``drive_folder_id`` clears both columns —
   same endpoint, no DELETE needed.
4. **GET prefers stored**: when ``drive_folder_id`` is set, the response
   uses it (``source="stored"``) instead of the legacy name search.
5. **Cross-tenant safety**: a client from another org cannot be
   modified — 404, not 403, no enumeration leak.

Run: pytest tests/test_client_drive_folder_link.py
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import routes.clients as clients
from models import Client


_ORG_ID = 31


def _make_request(body: dict, org_id=_ORG_ID):
    """Stub request: state.org_id + .json() coroutine returning ``body``."""
    request = SimpleNamespace()
    request.state = SimpleNamespace(org_id=org_id)
    request.cookies = {}

    async def _json():
        return body

    request.json = _json
    return request


def _patch_auth(monkeypatch, user=object()):
    monkeypatch.setattr(clients, "get_current_user", lambda req, db: user)


def _seed_client(db, org_id=_ORG_ID, first="Maria", last="Silva"):
    c = Client(org_id=org_id, first_name=first, last_name=last)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# URL parser
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Bare ids
        ("1A2B3C4D5E6F7G8", "1A2B3C4D5E6F7G8"),
        ("abcdefghijklmnop_-1234567890", "abcdefghijklmnop_-1234567890"),
        # /drive/folders/
        ("https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQ",
         "1AbCdEfGhIjKlMnOpQ"),
        ("https://drive.google.com/drive/u/0/folders/1AbCdEfGhIjKlMnOpQ?usp=sharing",
         "1AbCdEfGhIjKlMnOpQ"),
        # open?id= / file/d/
        ("https://drive.google.com/open?id=1Xyz_-AbC_DefGhIjKl",
         "1Xyz_-AbC_DefGhIjKl"),
        ("https://drive.google.com/file/d/1Xyz_-AbC_DefGhIjKl/view",
         "1Xyz_-AbC_DefGhIjKl"),
    ],
)
def test_parse_drive_folder_id_accepts_valid_forms(raw, expected):
    assert clients._parse_drive_folder_id(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "https://evil.example.com/folders/abc1234567890123",  # wrong host
        "https://drive.google.com/drive/folders/short",       # < 15 chars
        "just a string with no id",
    ],
)
def test_parse_drive_folder_id_rejects_garbage(raw):
    assert clients._parse_drive_folder_id(raw) is None


# ---------------------------------------------------------------------------
# POST persists
# ---------------------------------------------------------------------------


def test_post_persists_drive_folder_id_from_url(db, monkeypatch):
    _patch_auth(monkeypatch)
    c = _seed_client(db)

    body = {
        "drive_folder_id": "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQ",
        "drive_folder_name": "Cliente Maria — Imigração",
    }
    payload = _run(clients.set_client_drive_folder(_make_request(body), c.id, db))

    assert payload["success"] is True
    assert payload["drive_folder_id"] == "1AbCdEfGhIjKlMnOpQ"
    db.refresh(c)
    assert c.drive_folder_id == "1AbCdEfGhIjKlMnOpQ"
    assert c.drive_folder_name == "Cliente Maria — Imigração"


def test_post_persists_bare_id(db, monkeypatch):
    _patch_auth(monkeypatch)
    c = _seed_client(db)

    body = {"drive_folder_id": "1Xyz_-AbC_DefGhIjKl"}
    payload = _run(clients.set_client_drive_folder(_make_request(body), c.id, db))

    assert payload["drive_folder_id"] == "1Xyz_-AbC_DefGhIjKl"
    db.refresh(c)
    assert c.drive_folder_id == "1Xyz_-AbC_DefGhIjKl"


def test_post_rejects_invalid_drive_folder_id(db, monkeypatch):
    _patch_auth(monkeypatch)
    c = _seed_client(db)

    body = {"drive_folder_id": "https://evil.com/folders/abc1234567890123"}
    payload = _run(clients.set_client_drive_folder(_make_request(body), c.id, db))

    assert payload["success"] is False
    assert payload["error"] == "invalid_drive_folder_id"
    db.refresh(c)
    assert c.drive_folder_id is None  # nothing persisted


def test_post_with_empty_id_unlinks(db, monkeypatch):
    """Same endpoint handles unlink — caller posts ``drive_folder_id=""``."""
    _patch_auth(monkeypatch)
    c = _seed_client(db)
    c.drive_folder_id = "1AbCdEfGhIjKlMnOpQ"
    c.drive_folder_name = "previously linked"
    db.commit()

    payload = _run(clients.set_client_drive_folder(
        _make_request({"drive_folder_id": ""}), c.id, db,
    ))

    assert payload["success"] is True
    assert payload["unlinked"] is True
    db.refresh(c)
    assert c.drive_folder_id is None
    assert c.drive_folder_name is None


# ---------------------------------------------------------------------------
# GET prefers stored
# ---------------------------------------------------------------------------


def test_get_prefers_stored_drive_folder_id(db, monkeypatch):
    """When ``drive_folder_id`` is set, GET uses it and never falls back
    to the brittle name-derived search — even if the Drive handler would
    fail."""
    _patch_auth(monkeypatch)
    c = _seed_client(db)
    c.drive_folder_id = "1AbCdEfGhIjKlMnOpQ"
    c.drive_folder_name = "Cliente Maria"
    db.commit()

    # If the legacy fallback ran it would import GoogleDriveHandler.
    # Replace it with a sentinel that would explode — we should NEVER
    # reach that branch.
    def _explode(*args, **kwargs):
        raise AssertionError(
            "Legacy name-based fallback must not run when drive_folder_id "
            "is stored — the stored id is the source of truth."
        )

    monkeypatch.setattr(
        "services.google_drive_handler.GoogleDriveHandler",
        _explode,
    )

    payload = _run(clients.get_client_drive_folder(
        _make_request({}), c.id, db,
    ))

    assert payload["success"] is True
    assert payload["folder_id"] == "1AbCdEfGhIjKlMnOpQ"
    assert payload["source"] == "stored"
    assert "drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQ" in payload["web_link"]


# ---------------------------------------------------------------------------
# Cross-tenant safety
# ---------------------------------------------------------------------------


def test_post_returns_404_for_other_org_client(db, monkeypatch):
    """A client from a different org must return 404 — not 403 — so an
    attacker cannot enumerate client ids across orgs by status code."""
    from fastapi import HTTPException
    _patch_auth(monkeypatch)

    # Seed a client in org B; caller is in org A (the request's org_id).
    other_client = _seed_client(db, org_id=999)

    body = {"drive_folder_id": "1AbCdEfGhIjKlMnOpQ"}
    with pytest.raises(HTTPException) as exc_info:
        _run(clients.set_client_drive_folder(
            _make_request(body, org_id=_ORG_ID), other_client.id, db,
        ))
    assert exc_info.value.status_code == 404
