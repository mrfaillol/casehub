"""Tests for CRM auto-create Drive folder on client cadastro (N7).

Context: the Drive helper (``GoogleDriveHandler.get_client_folder`` /
``create_client_folder_structure``) existed for a long time but was
NEVER wired into ``create_client`` — a client cadastro created the row
but never provisioned its Drive folder (C9 REFUTED in the UsuarioDemo
2026-06-15 meeting analysis).

This wires it CONSERVATIVELY, behind a per-org opt-in toggle
(``Organization.features["auto_create_drive_folder"]``, default OFF):

1. **Toggle ON** -> the Drive helper (mocked, never the real API) is
   called and the returned folder id/name are persisted on the client.
2. **Toggle OFF** (default) -> the helper is NEVER instantiated; no
   surprise Drive writes in prod.
3. **Drive failure is non-fatal** -> if the helper raises or returns
   nothing, the client is still created; ``drive_folder_id`` stays
   ``None`` and no exception escapes.
4. **Org-scoped** -> the toggle is read from the caller's own org;
   another org's flag never leaks in.

The real Google Drive API is NEVER called here — ``GoogleDriveHandler``
is always patched.

Run: pytest tests/test_client_auto_drive_folder.py
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import routes.clients as clients
from models import Client
from models.tenant import Organization


_ORG_ID = 31


def _run(coro):
    return asyncio.run(coro)


def _seed_org(db, org_id=_ORG_ID, *, auto_folder=None, slug=None):
    """Seed an Organization. ``auto_folder`` None -> no key at all (default
    OFF); True/False -> explicit feature flag value."""
    features = {}
    if auto_folder is not None:
        features["auto_create_drive_folder"] = auto_folder
    org = Organization(
        id=org_id,
        uuid=f"org-{org_id}-test",
        name=f"Org {org_id}",
        slug=slug or f"org-{org_id}",
        features=features,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _seed_client(db, org_id=_ORG_ID, first="PessoaDemo", last="Silva"):
    c = Client(org_id=org_id, first_name=first, last_name=last)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _fake_request(org_id=_ORG_ID):
    return SimpleNamespace(state=SimpleNamespace(org_id=org_id))


def _patch_handler(monkeypatch, *, folder_id="1AutoCreatedFolderId", raises=False):
    """Patch GoogleDriveHandler so the real Drive API is never touched.

    Returns the MagicMock class so callers can assert call counts.
    """
    instance = MagicMock()
    instance.service = object()  # "connected"
    instance.is_connected.return_value = True
    if raises:
        instance.get_client_folder.side_effect = RuntimeError("Drive 503")
    else:
        instance.get_client_folder.return_value = folder_id

    handler_cls = MagicMock(return_value=instance)
    monkeypatch.setattr(
        "services.google_drive_handler.GoogleDriveHandler", handler_cls
    )
    return handler_cls, instance


# ---------------------------------------------------------------------------
# Toggle gating
# ---------------------------------------------------------------------------


def test_toggle_on_calls_helper_and_persists_folder(db, monkeypatch):
    _seed_org(db, auto_folder=True)
    c = _seed_client(db)
    handler_cls, instance = _patch_handler(monkeypatch, folder_id="1Folder_AbcDef_123")

    clients._maybe_auto_create_drive_folder(_fake_request(), db, c)

    # Helper instantiated org-scoped and asked to provision the folder.
    handler_cls.assert_called_once()
    _, kwargs = handler_cls.call_args
    assert kwargs.get("org_id") == _ORG_ID
    instance.get_client_folder.assert_called_once()

    db.refresh(c)
    assert c.drive_folder_id == "1Folder_AbcDef_123"
    assert c.drive_folder_name  # a human-readable name was stored


def test_toggle_off_default_does_not_call_helper(db, monkeypatch):
    """No feature key at all (the default for every existing org) -> the
    Drive handler is never even instantiated."""
    _seed_org(db, auto_folder=None)
    c = _seed_client(db)
    handler_cls, instance = _patch_handler(monkeypatch)

    clients._maybe_auto_create_drive_folder(_fake_request(), db, c)

    handler_cls.assert_not_called()
    db.refresh(c)
    assert c.drive_folder_id is None


def test_toggle_explicit_false_does_not_call_helper(db, monkeypatch):
    _seed_org(db, auto_folder=False)
    c = _seed_client(db)
    handler_cls, _ = _patch_handler(monkeypatch)

    clients._maybe_auto_create_drive_folder(_fake_request(), db, c)

    handler_cls.assert_not_called()
    db.refresh(c)
    assert c.drive_folder_id is None


# ---------------------------------------------------------------------------
# Failure isolation
# ---------------------------------------------------------------------------


def test_drive_failure_does_not_raise(db, monkeypatch):
    """Helper raises -> swallowed; client left untouched, no exception."""
    _seed_org(db, auto_folder=True)
    c = _seed_client(db)
    _patch_handler(monkeypatch, raises=True)

    # Must NOT raise.
    clients._maybe_auto_create_drive_folder(_fake_request(), db, c)

    db.refresh(c)
    assert c.drive_folder_id is None


def test_drive_not_connected_is_noop(db, monkeypatch):
    """Toggle ON but no Drive token (handler.service is None) -> no-op,
    no persisted id, no exception."""
    _seed_org(db, auto_folder=True)
    c = _seed_client(db)
    instance = MagicMock()
    instance.service = None
    instance.is_connected.return_value = False
    monkeypatch.setattr(
        "services.google_drive_handler.GoogleDriveHandler",
        MagicMock(return_value=instance),
    )

    clients._maybe_auto_create_drive_folder(_fake_request(), db, c)

    instance.get_client_folder.assert_not_called()
    db.refresh(c)
    assert c.drive_folder_id is None


def test_helper_returns_no_folder_id_is_noop(db, monkeypatch):
    """Drive connected but returns None (e.g. ACL / quota) -> nothing
    persisted, no exception."""
    _seed_org(db, auto_folder=True)
    c = _seed_client(db)
    _patch_handler(monkeypatch, folder_id=None)

    clients._maybe_auto_create_drive_folder(_fake_request(), db, c)

    db.refresh(c)
    assert c.drive_folder_id is None


# ---------------------------------------------------------------------------
# Org scoping
# ---------------------------------------------------------------------------


def test_other_orgs_flag_does_not_leak(db, monkeypatch):
    """Caller org has the flag OFF; a *different* org has it ON. The
    helper must not fire for the caller."""
    _seed_org(db, org_id=_ORG_ID, auto_folder=False, slug="caller")
    _seed_org(db, org_id=999, auto_folder=True, slug="other")
    c = _seed_client(db, org_id=_ORG_ID)
    handler_cls, _ = _patch_handler(monkeypatch)

    clients._maybe_auto_create_drive_folder(_fake_request(org_id=_ORG_ID), db, c)

    handler_cls.assert_not_called()
    db.refresh(c)
    assert c.drive_folder_id is None


def test_missing_org_row_is_noop(db, monkeypatch):
    """Caller org_id has no Organization row -> treat as OFF, no crash."""
    c = _seed_client(db, org_id=12345)
    handler_cls, _ = _patch_handler(monkeypatch)

    clients._maybe_auto_create_drive_folder(_fake_request(org_id=12345), db, c)

    handler_cls.assert_not_called()
    db.refresh(c)
    assert c.drive_folder_id is None


# ---------------------------------------------------------------------------
# Integration through create_client
# ---------------------------------------------------------------------------


def _patch_auth(monkeypatch):
    monkeypatch.setattr(clients, "get_current_user", lambda req, db: object())


def _create_request(org_id=_ORG_ID):
    request = SimpleNamespace(state=SimpleNamespace(org_id=org_id))

    async def _form():
        return {}

    request.form = _form
    return request


def _call_create_client(db, *, first_name, last_name, org_id=_ORG_ID):
    """Chama create_client passando TODOS os params Form como valores.
    Chamar o handler direto NÃO resolve Form(...), então qualquer campo
    não-passado vira um objeto Form e quebra encrypt_value/commit."""
    return _run(
        clients.create_client(
            _create_request(org_id),
            first_name=first_name,
            last_name=last_name,
            email=None, phone=None, whatsapp=None, date_of_birth=None,
            country_of_origin=None, ssn=None, alien_number=None,
            passport_number=None, cpf=None, rg=None, cnpj=None,
            oab_number=None, client_type="individual", address=None,
            status="lead", notes=None,
            db=db,
        )
    )


def test_create_client_wires_auto_folder_when_on(db, monkeypatch):
    _patch_auth(monkeypatch)
    _seed_org(db, auto_folder=True)
    handler_cls, instance = _patch_handler(monkeypatch, folder_id="1WiredFolderId")

    resp = _call_create_client(db, first_name="Joao", last_name="Souza")

    # Cadastro succeeded (redirect to the new client view).
    assert getattr(resp, "status_code", None) == 302
    created = (
        db.query(Client)
        .filter(Client.org_id == _ORG_ID, Client.first_name == "Joao")
        .first()
    )
    assert created is not None
    db.refresh(created)
    assert created.drive_folder_id == "1WiredFolderId"
    instance.get_client_folder.assert_called_once()


def test_create_client_does_not_fire_when_off(db, monkeypatch):
    _patch_auth(monkeypatch)
    _seed_org(db, auto_folder=None)  # default OFF
    handler_cls, _ = _patch_handler(monkeypatch)

    resp = _call_create_client(db, first_name="Ana", last_name="Lima")

    assert getattr(resp, "status_code", None) == 302
    created = (
        db.query(Client)
        .filter(Client.org_id == _ORG_ID, Client.first_name == "Ana")
        .first()
    )
    assert created is not None
    handler_cls.assert_not_called()
    assert created.drive_folder_id is None


def test_create_client_survives_drive_failure(db, monkeypatch):
    """Toggle ON but Drive blows up -> cadastro STILL succeeds."""
    _patch_auth(monkeypatch)
    _seed_org(db, auto_folder=True)
    _patch_handler(monkeypatch, raises=True)

    resp = _call_create_client(db, first_name="Carlos", last_name="Pereira")

    assert getattr(resp, "status_code", None) == 302
    created = (
        db.query(Client)
        .filter(Client.org_id == _ORG_ID, Client.first_name == "Carlos")
        .first()
    )
    assert created is not None  # client created despite Drive failure
    db.refresh(created)
    assert created.drive_folder_id is None
