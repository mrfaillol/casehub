"""Regression test for routes/onboarding.setup_team_invite — per-email N+1.

setup_team_invite (POST /casehub/setup/team/invite) issued
`db.query(User).filter(User.email == email).first()` per email to skip
already-existing users — N SELECTs per call (bounded at 10).

The fix batches the existence check into one `.in_(emails_to_invite)`
query. The absolute win is small (bounded N), but the pattern is correct.

Run: pytest tests/test_onboarding_team_invite.py
"""
import asyncio

import pytest
from fastapi.responses import RedirectResponse
from sqlalchemy import event

import routes.onboarding as onboarding
from models import Organization, User

_ORG_ID = 23


@pytest.fixture
def request_stub(mock_request):
    mock_request.cookies = {}
    return mock_request


def _seed_existing(db, emails):
    for em in emails:
        db.add(User(
            email=em,
            name=em.split("@")[0],
            password_hash="x",
            user_type="case_worker",
            enabled=True,
            org_id=_ORG_ID,
        ))
    db.commit()


def _seed_org(db):
    org = db.query(Organization).filter(Organization.id == _ORG_ID).first()
    if org is None:
        org = Organization(
            id=_ORG_ID,
            uuid="team-invite-org",
            name="Test Org",
            slug="team-invite-org",
            is_active=True,
        )
        db.add(org)
        db.commit()
    return org


def _run(db, monkeypatch, request_stub, emails_form):
    _seed_org(db)
    user = type("UserStub", (), {"id": 501, "email": "admin@test.com", "org_id": _ORG_ID})()
    monkeypatch.setattr(onboarding, "get_current_user", lambda req, d: user)
    sent = []
    monkeypatch.setattr(onboarding, "send_email",
                        lambda **kwargs: sent.append(kwargs["to_email"]))

    selects = []
    engine = db.get_bind()

    def _on_exec(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(engine, "before_cursor_execute", _on_exec)
    try:
        result = asyncio.run(onboarding.setup_team_invite(
            request_stub, emails=emails_form, db=db,
        ))
    finally:
        event.remove(engine, "before_cursor_execute", _on_exec)

    return result, len(selects), sent


def test_setup_team_invite_batches_existence_check(db, monkeypatch, request_stub):
    """One .in_() SELECT replaces n per-email .first() lookups; existing
    users are still skipped from the invite list."""
    _seed_existing(db, ["dup1@test.com", "dup2@test.com"])
    emails = "dup1@test.com, dup2@test.com, new1@test.com, new2@test.com, new3@test.com"
    result, select_count, sent = _run(db, monkeypatch, request_stub, emails)

    assert isinstance(result, RedirectResponse)
    # 3 new users invited; the 2 existing skipped.
    assert sorted(sent) == ["new1@test.com", "new2@test.com", "new3@test.com"]
    # 1 batched .in_() existence check. Pre-fix would have been n=5 per-email
    # SELECTs (plus the user create + autoflush noise).
    assert select_count <= 4, (
        f"{select_count} SELECTs for 5 emails — expected ~1 .in_ batch"
    )


def test_setup_team_invite_empty_form(db, monkeypatch, request_stub):
    """Empty email list -> redirect with error, no DB writes."""
    _seed_org(db)
    user = type("UserStub", (), {"id": 501, "email": "admin@test.com", "org_id": _ORG_ID})()
    monkeypatch.setattr(onboarding, "get_current_user", lambda req, d: user)

    result = asyncio.run(onboarding.setup_team_invite(request_stub, emails="", db=db))

    assert isinstance(result, RedirectResponse)
    assert "No+valid+emails" in str(result.headers.get("location", ""))
