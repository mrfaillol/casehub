"""Regression test for routes/notifications.check_deadlines — multi-site N+1.

check_deadlines iterates a 4-day reminder window. For each day it fetches the
tasks due that day, then inside the inner loop it issued per-task DB lookups:
- one tenant_query(Case).filter(Case.id == task.case_id).first() per task;
- one tenant_query(User).filter(User.id == task.assigned_to).first() per task;
- a tenant_query(User).filter(user_type=='admin').first() admin fallback per
  task without an assignee (same query repeated every loop turn).

All three are now batched: cases and assignees into dicts built once per day,
and the admin fallback cached once for the whole call.

Run: pytest tests/test_notifications_check_deadlines.py
"""
import asyncio
from datetime import date, timedelta

import pytest
from sqlalchemy import event

import routes.notifications as notifs
from models import Case, Client, Task, User

_ORG_ID = 15


@pytest.fixture
def request_stub(mock_request):
    mock_request.cookies = {}
    mock_request.state.org_id = _ORG_ID
    return mock_request


class _AdminUser:
    user_type = "admin"
    email = "admin@test.com"
    id = 1


def _seed(db, n_per_day):
    """For each reminder offset in [0, 1, 3, 7] days, n_per_day tasks due that
    day, each pointing at its own case + assigned to its own user."""
    offsets = [0, 1, 3, 7]
    today = date.today()
    for d_off in offsets:
        for i in range(n_per_day):
            client = Client(org_id=_ORG_ID, first_name=f"C{d_off}-{i}", last_name="X")
            db.add(client)
            db.flush()
            case = Case(
                org_id=_ORG_ID,
                client_id=client.id,
                case_number=f"DL-{_ORG_ID}-{d_off}-{i}",
                case_name=f"Case {d_off}-{i}",
            )
            db.add(case)
            user = User(
                org_id=_ORG_ID,
                email=f"u-{d_off}-{i}@test.com",
                name=f"User {d_off}-{i}",
                password_hash="x",
                user_type="case_worker",
            )
            db.add(user)
            db.flush()
            db.add(Task(
                org_id=_ORG_ID,
                title=f"Task {d_off}-{i}",
                case_id=case.id,
                assigned_to=user.id,
                due_date=today + timedelta(days=d_off),
                status="pending",
                priority="medium",
            ))
    db.commit()


def _count_selects(db, monkeypatch, request_stub, n_per_day):
    _seed(db, n_per_day)

    monkeypatch.setattr(notifs, "get_current_user",
                        lambda req, d: _AdminUser())

    class _FakeEmailService:
        def is_configured(self):
            return True

        def send_deadline_reminder(self, **kwargs):
            return {"success": True}

    monkeypatch.setattr(notifs, "email_service", _FakeEmailService())

    selects = []
    engine = db.get_bind()

    def _on_exec(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(engine, "before_cursor_execute", _on_exec)
    try:
        result = asyncio.run(notifs.check_deadlines(request_stub, db=db))
    finally:
        event.remove(engine, "before_cursor_execute", _on_exec)

    assert result["status"] == "completed"
    assert result["emails_sent"] == 4 * n_per_day   # one per task in 4 days
    return len(selects)


def test_check_deadlines_does_not_scale_with_tasks(db, monkeypatch, request_stub):
    """Pre-fix: 1 admin (per-task) + per-day (1 tasks + 2*n_tasks per-task
    lookups) -> ~1 + 4*(1 + 2*n) = 9 + 8*n SELECTs at the assignee-set worst.
    After: 1 admin (cached) + 4*(1 tasks + 1 cases-batch + 1 users-batch) = 13
    SELECTs regardless of n."""
    n_per_day = 5
    select_count = _count_selects(db, monkeypatch, request_stub, n_per_day)

    # After: 13 + ORM overhead. Pre-fix at n=5 would be ~49 (worst case
    # without the admin fallback, since every task has an assignee here).
    assert select_count <= 20, (
        f"{select_count} SELECTs for n_per_day={n_per_day} — expected ~13 "
        f"(batched per-day, admin cached), not the pre-fix per-task pattern"
    )
