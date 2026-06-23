"""Unit tests for WhatsApp multi-session per-tenant (F29).

Covers:
  - process_inbound respects requested_org_id (from X-Org-Id header)
  - _resolve_inbound_org precedence: requested_org_id > matched_org_id >
    single-org fallback > default org > first org
  - phone match still wins when X-Org-Id is absent (legacy compat)

DB-touching tests rely on a stub SQLAlchemy session that records the SQL
calls — we don't need a real DB for the precedence logic.

Run: pytest tests/test_whatsapp_multi_tenant.py
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def stub_db(monkeypatch):
    """Build a SQLAlchemy-shaped session stub that:
      - resolves organization existence via _execute_lookup
      - returns canned rows for phone match
    """
    db = MagicMock()

    # We pre-bake responses for the SELECT id FROM organizations WHERE id=:id
    # used by _resolve_inbound_org and for the org-list scan.
    org_exists = {1, 4, 2}  # 1=default? 4=tenanta, 2=other
    org_with_slug_default = 2

    def execute(stmt, params=None):
        sql = str(stmt).lower()
        result = MagicMock()
        if "where id = :id" in sql:
            org_id = (params or {}).get("id")
            if org_id in org_exists:
                row = MagicMock()
                row.id = org_id
                result.first.return_value = row
            else:
                result.first.return_value = None
        elif "where slug = 'default'" in sql:
            row = MagicMock()
            row.id = org_with_slug_default
            result.first.return_value = row
        elif "order by id limit 2" in sql:
            # 2+ orgs
            rows = [MagicMock(id=1), MagicMock(id=4)]
            result.fetchall.return_value = rows
        elif "order by id limit 1" in sql:
            row = MagicMock()
            row.id = 1
            result.first.return_value = row
        else:
            # default no-op
            result.fetchall.return_value = []
            result.first.return_value = None
            result.fetchone.return_value = None
            result.rowcount = 0
        return result

    db.execute.side_effect = execute
    return db


def test_resolve_inbound_org_prefers_requested_org_id(stub_db):
    from services.whatsapp_inbound_service import _resolve_inbound_org

    # When X-Org-Id says 4 and phone match says 1, the header wins.
    resolved = _resolve_inbound_org(stub_db, matched_org_id=1, requested_org_id=4)
    assert resolved == 4


def test_resolve_inbound_org_validates_requested_org_id_exists(stub_db):
    from services.whatsapp_inbound_service import _resolve_inbound_org

    # When X-Org-Id points to a non-existent org, fall back to matched_org_id.
    resolved = _resolve_inbound_org(stub_db, matched_org_id=1, requested_org_id=99)
    assert resolved == 1


def test_resolve_inbound_org_falls_back_to_matched_when_no_header(stub_db):
    from services.whatsapp_inbound_service import _resolve_inbound_org

    # Legacy flow: no header, phone matched a client in org 4.
    resolved = _resolve_inbound_org(stub_db, matched_org_id=4)
    assert resolved == 4


def test_resolve_inbound_org_uses_default_slug_when_unmatched(stub_db):
    from services.whatsapp_inbound_service import _resolve_inbound_org

    # No phone match, 2+ orgs exist, default slug present -> use default.
    resolved = _resolve_inbound_org(stub_db, matched_org_id=None)
    # stub returns 2 for slug='default'
    assert resolved == 2


def test_process_inbound_threads_requested_org_id_through(monkeypatch):
    """process_inbound should pass requested_org_id to _resolve_inbound_org
    AND honor it over the matched_org_id when present."""
    from services import whatsapp_inbound_service as svc

    captured = {}

    def fake_persist(db, **kwargs):
        return (101, 1, 42)  # inbound_id=101, matched_org=1, client=42

    def fake_link(*args, **kwargs):
        captured["link_org_id"] = kwargs.get("org_id")
        return None

    def fake_seed(*args, **kwargs):
        captured["seed_org_id"] = kwargs.get("org_id")
        return None

    def fake_mirror(db, **kwargs):
        captured["mirror_org_id"] = kwargs.get("org_id")
        return 999

    monkeypatch.setattr(svc, "persist_inbound_message", fake_persist)
    monkeypatch.setattr(svc, "link_pending_field_request", fake_link)
    monkeypatch.setattr(svc, "seed_training_sample_if_enabled", fake_seed)
    monkeypatch.setattr(svc, "mirror_inbound_to_clone", fake_mirror)
    # Stub _resolve_inbound_org to return whatever was requested (validates that
    # process_inbound passes requested_org_id through).
    monkeypatch.setattr(
        svc,
        "_resolve_inbound_org",
        lambda db, matched, requested_org_id=None: requested_org_id or matched,
    )

    db = MagicMock()
    result = svc.process_inbound(
        db,
        from_phone="5511999999999",
        message="hello",
        media_type="text",
        raw_payload={"some": "thing"},
        requested_org_id=4,
    )

    # Resolved org honors the header (4) over the phone match (1).
    assert result["matched_org_id"] == 1  # raw phone match unchanged
    assert result["resolved_org_id"] == 4  # header took precedence
    assert result["requested_org_id"] == 4
    # Downstream calls all received the resolved org (4).
    assert captured["link_org_id"] == 4
    assert captured["seed_org_id"] == 4
    assert captured["mirror_org_id"] == 4


def test_process_inbound_no_header_falls_back_to_phone_match(monkeypatch):
    """Without X-Org-Id, the legacy phone-match precedence applies."""
    from services import whatsapp_inbound_service as svc

    monkeypatch.setattr(svc, "persist_inbound_message", lambda db, **k: (101, 7, 42))
    monkeypatch.setattr(svc, "link_pending_field_request", lambda *a, **k: None)
    monkeypatch.setattr(svc, "seed_training_sample_if_enabled", lambda *a, **k: None)
    monkeypatch.setattr(svc, "mirror_inbound_to_clone", lambda db, **k: 999)
    monkeypatch.setattr(
        svc, "_resolve_inbound_org", lambda db, matched, requested_org_id=None: matched
    )

    db = MagicMock()
    result = svc.process_inbound(
        db,
        from_phone="5511999999999",
        message="hello",
        media_type="text",
        raw_payload=None,
    )

    assert result["matched_org_id"] == 7
    assert result["resolved_org_id"] == 7
    assert result["requested_org_id"] is None
