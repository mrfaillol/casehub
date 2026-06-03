"""Regression test for routes/efiling.create_submission — per-doc N+1.

create_submission iterated the requested `document_ids` calling
`tenant_query(Document).filter(Document.id == doc_id).first()` per id — one
SELECT per id. Submission order matters (documents are packed into the
e-filing in the order the user listed), so the fix builds a dict from a
single `.in_` batch and iterates `doc_ids` against it.

Run: pytest tests/test_efiling_create_submission.py
"""
import asyncio
import json

import pytest
from fastapi.responses import RedirectResponse
from sqlalchemy import event

import routes.efiling as efiling
from models import Case, Client, Document

_ORG_ID = 19


@pytest.fixture
def request_stub(mock_request):
    mock_request.cookies = {}
    mock_request.state.org_id = _ORG_ID
    return mock_request


class _User:
    id = 1


def _seed(db, n):
    """Client + case + n documents with predictable names."""
    client = Client(org_id=_ORG_ID, first_name="C", last_name="X")
    db.add(client)
    db.flush()
    case = Case(org_id=_ORG_ID, client_id=client.id, case_number=f"EF-{_ORG_ID}")
    db.add(case)
    db.flush()
    ids = []
    for i in range(n):
        d = Document(
            org_id=_ORG_ID,
            client_id=client.id,
            name=f"Doc-{i}",
            file_path=f"/tmp/doc-{i}.pdf",
        )
        db.add(d)
        db.flush()
        ids.append(d.id)
    db.commit()
    return case.id, ids


def _run(db, monkeypatch, request_stub, doc_ids, case_id):
    monkeypatch.setattr(efiling, "get_current_user", lambda req, d: _User())
    monkeypatch.setattr(efiling, "ensure_tables", lambda _db: None)

    captured = {}

    def _fake_calc_fees(form, premium, _flag):
        return {"total": 0}

    def _fake_create(*, case_id, form_number, filing_type, service_center,
                     documents, notes):
        captured["documents"] = documents
        return {"submission_id": "sub-test-001"}

    monkeypatch.setattr(efiling.efiling_service, "calculate_fees", _fake_calc_fees)
    monkeypatch.setattr(efiling.efiling_service, "create_submission", _fake_create)

    # The handler also INSERTs into efiling_submissions; the table + enum
    # bindings need Postgres. Short-circuit just that INSERT in the test —
    # SELECTs and other writes still go through real_execute.
    real_execute = db.execute

    def _wrapped_execute(statement, *args, **kwargs):
        if "INSERT INTO efiling_submissions" in str(statement):
            return None
        return real_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", _wrapped_execute)

    selects = []
    engine = db.get_bind()

    def _on_exec(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(engine, "before_cursor_execute", _on_exec)
    try:
        result = asyncio.run(efiling.create_submission(
            request_stub,
            case_id=case_id,
            form_number="I-130",
            filing_type="initial",
            service_center=None,
            document_ids=json.dumps(doc_ids),
            premium_processing=False,
            notes=None,
            db=db,
        ))
    finally:
        event.remove(engine, "before_cursor_execute", _on_exec)

    return result, len(selects), captured


def test_create_submission_batches_document_lookup(db, monkeypatch, request_stub):
    """SELECT count for the document lookup is constant in n_ids: per-id
    `.first()` replaced by one `.in_` batch."""
    n = 8
    case_id, ids = _seed(db, n)
    result, select_count, captured = _run(db, monkeypatch, request_stub, ids, case_id)

    assert isinstance(result, RedirectResponse)
    assert len(captured["documents"]) == n
    # Pre-fix: 1 per doc id + small overhead = at least n SELECTs from the
    # loop alone. After: 1 .in_ + small overhead. Allow generous margin
    # since the handler also runs ensure_tables (CREATE TABLE IF NOT EXISTS).
    assert select_count <= 6, (
        f"{select_count} SELECTs for n={n} doc ids — expected ~1 for the "
        f"document fetch, not the pre-fix per-id pattern"
    )


def test_create_submission_preserves_doc_order(db, monkeypatch, request_stub):
    """Submission order = the order the user listed doc_ids in, even if the
    `.in_` batch returns rows in a different order."""
    _, ids = _seed(db, 5)
    reversed_ids = list(reversed(ids))
    _, _, captured = _run(db, monkeypatch, request_stub, reversed_ids, 1)

    assert [d["id"] for d in captured["documents"]] == reversed_ids
