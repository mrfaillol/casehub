"""Regression test for routes/documents_api.batch_approve_documents.

POST /casehub/api/documents/batch-approve was broken on main: the body
referenced `request.state.org_id` but the handler signature was missing
`request: Request` — every call NameError'd (HTTP 500). The same loop also
issued one `tenant_query(Document)...first()` per id (N+1).

Both are now fixed in the same handler:
  - `request: Request` added to the signature.
  - per-id `.first()` replaced by one `.in_(document_ids)` batch + dict lookup.

Run: pytest tests/test_documents_api_batch_approve.py
"""
import asyncio

import pytest
from sqlalchemy import event

import routes.documents_api as docs_api
from models import Client, Document

_ORG_ID = 21


@pytest.fixture
def request_stub(mock_request):
    mock_request.cookies = {}
    mock_request.state.org_id = _ORG_ID
    return mock_request


def _seed(db, n):
    client = Client(org_id=_ORG_ID, first_name="C", last_name="X")
    db.add(client)
    db.flush()
    ids = []
    for i in range(n):
        d = Document(org_id=_ORG_ID, client_id=client.id, name=f"Doc {i}")
        db.add(d)
        db.flush()
        ids.append(d.id)
    db.commit()
    return ids


def _run(db, request_stub, ids):
    selects = []
    engine = db.get_bind()

    def _on_exec(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(engine, "before_cursor_execute", _on_exec)
    try:
        result = asyncio.run(docs_api.batch_approve_documents(
            request=request_stub,
            document_ids=ids,
            user_id=1,
            db=db,
        ))
    finally:
        event.remove(engine, "before_cursor_execute", _on_exec)

    return result, len(selects)


def test_batch_approve_works_and_batches_lookup(db, request_stub):
    """The handler now accepts `request` (no NameError) and issues one batch
    SELECT instead of one per id."""
    n = 8
    ids = _seed(db, n)
    result, select_count = _run(db, request_stub, ids)

    assert result["success"] is True
    assert sorted(result["approved"]) == sorted(ids)
    assert result["not_found"] == []
    assert result["total_approved"] == n

    # 1 .in_ batch + small overhead. Pre-fix would have raised NameError
    # immediately (before any SELECT), so this assertion exists to catch
    # any regression that reverts to the per-id pattern.
    assert select_count <= 3, (
        f"{select_count} SELECTs for n={n} — expected ~1 (.in_ batch)"
    )


def test_batch_approve_reports_missing_ids(db, request_stub):
    """ids not present in the org's documents land in `not_found`."""
    ids = _seed(db, 3)
    requested = ids + [99999, 100000]   # two ids that don't exist
    result, _ = _run(db, request_stub, ids=requested)

    assert sorted(result["approved"]) == sorted(ids)
    assert sorted(result["not_found"]) == [99999, 100000]
    assert result["total_approved"] == 3
