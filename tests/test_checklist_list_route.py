"""Regression test for routes/checklist.list_checklists — N+1 query.

list_checklists pre-fetched documents in one batched query, but then issued a
separate `tenant_query(Client)...first()` for every case inside the loop — an
N+1: one client SELECT per case. Clients are now batched into a dict up front,
mirroring the existing docs_by_case pattern.

The honest metric for an N+1 is SQL statement count, not wall time (SQLite
in-memory has no network latency, so timing would understate the real cost).

Run: pytest tests/test_checklist_list_route.py
"""
import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import event

import routes.checklist as checklist
from models import Case, Client

_ORG_ID = 11


class _FakeChecklist:
    progress_percent = 50
    visa_label = "EB-2 NIW"
    total_present = 1
    total_required = 2

    def to_dict(self):
        return {}


@pytest.fixture
def request_stub(mock_request):
    mock_request.cookies = {}
    mock_request.state.org_id = _ORG_ID
    return mock_request


def _seed(db, n):
    """n cases, each with its own client, in org _ORG_ID."""
    for i in range(n):
        client = Client(org_id=_ORG_ID, first_name=f"Client{i}", last_name="X")
        db.add(client)
        db.flush()
        db.add(Case(
            org_id=_ORG_ID,
            client_id=client.id,
            case_number=f"CASE-{_ORG_ID}-{i}",
            visa_type="eb2_niw",
            created_at=datetime.utcnow() - timedelta(days=i),
        ))
    db.commit()


def _count_selects(db, monkeypatch, request_stub, n):
    """Run list_checklists with n cases and return the SELECT statement count."""
    _seed(db, n)

    monkeypatch.setattr("services.checklist_generator.generate_checklist",
                        lambda *a, **k: _FakeChecklist())
    monkeypatch.setattr("services.checklist_generator.normalize_visa_type",
                        lambda vt: "eb2_niw")
    monkeypatch.setattr("services.checklist_generator.get_supported_visa_types",
                        lambda: [])
    monkeypatch.setattr(checklist, "get_current_user", lambda req, d: object())
    monkeypatch.setattr(checklist.templates, "TemplateResponse",
                        lambda name, ctx: {"_template": name, **ctx})

    selects = []
    engine = db.get_bind()

    def _on_exec(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(engine, "before_cursor_execute", _on_exec)
    try:
        result = asyncio.run(checklist.list_checklists(request_stub, db=db))
    finally:
        event.remove(engine, "before_cursor_execute", _on_exec)

    assert result["total"] == n          # every seeded case rendered
    return len(selects)


def test_list_checklists_client_fetch_does_not_scale_with_cases(db, monkeypatch, request_stub):
    """The SELECT count must not grow with the number of cases: clients are
    fetched in one batched query, not one-per-case. Regression for the N+1."""
    n = 8
    select_count = _count_selects(db, monkeypatch, request_stub, n)

    # cases + documents + clients = 3 batched SELECTs (small margin for ORM).
    # The pre-fix N+1 issued one client SELECT per case -> ~n+2.
    assert select_count <= 5, (
        f"{select_count} SELECTs for {n} cases — expected a constant ~3 "
        f"(N+1 client lookup not batched)"
    )
