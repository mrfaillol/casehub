"""Regression test for routes/calendar.get_events — multi-site N+1.

get_events iterated `cases` issuing one tenant_query(Client)...first() per
case (N+1), then iterated `tasks` issuing one case query AND one client query
per task with a case_id (two more N+1s in the same handler). All three are
now batched into dicts before the loops, mirroring the pattern from #560.

The honest metric for an N+1 is SQL statement count, not wall time (SQLite
in-memory has no network latency).

Run: pytest tests/test_calendar_events_route.py
"""
import asyncio
from datetime import date, datetime, timedelta

import pytest
from fastapi.responses import JSONResponse
from sqlalchemy import event

import routes.calendar as calendar_routes
from models import Case, Client, Task

_ORG_ID = 13


@pytest.fixture
def request_stub(mock_request):
    mock_request.cookies = {}
    mock_request.state.org_id = _ORG_ID
    return mock_request


def _seed(db, n_cases, n_tasks):
    """n_cases cases (each with own client + a filing_date so they emit events)
    plus n_tasks tasks (each pointing at one of the cases)."""
    case_ids = []
    for i in range(n_cases):
        client = Client(org_id=_ORG_ID, first_name=f"Client{i}", last_name="X")
        db.add(client)
        db.flush()
        case = Case(
            org_id=_ORG_ID,
            client_id=client.id,
            case_number=f"CAL-{_ORG_ID}-{i}",
            visa_type="eb2_niw",
            filing_date=date.today() - timedelta(days=i),
            created_at=datetime.utcnow() - timedelta(days=i),
        )
        db.add(case)
        db.flush()
        case_ids.append(case.id)

    for j in range(n_tasks):
        db.add(Task(
            org_id=_ORG_ID,
            title=f"Task {j}",
            case_id=case_ids[j % len(case_ids)] if case_ids else None,
            due_date=date.today() + timedelta(days=j),
            status="pending",
            priority="medium",
        ))
    db.commit()


def _count_selects(db, monkeypatch, request_stub, n_cases, n_tasks):
    _seed(db, n_cases, n_tasks)
    monkeypatch.setattr(calendar_routes, "get_current_user", lambda req, d: object())

    selects = []
    engine = db.get_bind()

    def _on_exec(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(engine, "before_cursor_execute", _on_exec)
    try:
        result = asyncio.run(
            calendar_routes.get_events(
                request_stub, start=None, end=None, filter_type=None,
                user_id=None, db=db,
            )
        )
    finally:
        event.remove(engine, "before_cursor_execute", _on_exec)

    assert isinstance(result, JSONResponse)
    return len(selects)


def test_get_events_does_not_scale_with_cases_or_tasks(db, monkeypatch, request_stub):
    """SELECT count must stay constant in cases + tasks: the per-case client
    lookup and the per-task case/client lookups are now batched."""
    n_cases = 6
    n_tasks = 6
    select_count = _count_selects(db, monkeypatch, request_stub, n_cases, n_tasks)

    # 1 cases + 1 case-clients batch + 1 tasks + 1 task-cases batch +
    # 1 task-clients batch = 5 SELECTs.
    # Pre-fix: 1 + n_cases + 1 + 2*n_tasks = 1 + 6 + 1 + 12 = 20.
    assert select_count <= 8, (
        f"{select_count} SELECTs for n_cases={n_cases}, n_tasks={n_tasks} — "
        f"expected ~5 (one batched query per kind), not the pre-fix "
        f"1 + n_cases + 1 + 2*n_tasks pattern"
    )
