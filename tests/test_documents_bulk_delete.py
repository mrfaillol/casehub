"""Regression test for routes/documents.bulk_delete — N+1 query.

bulk_delete iterated the request id list calling
`tenant_query(Document).filter(Document.id == doc_id).first()` per id —
one SELECT per id (bounded by MAX_BULK_ITEMS=500, but still N).

It now uses a single `.in_(data.ids)` batch query. The test for duplicate
ids is a non-regression guard: the pre-fix code avoided double-counting
duplicates only by accident (SA autoflush would execute the DELETE before
the next `.first()`, so the duplicate lookup returned None). `.in_` makes
the dedup explicit at the query level rather than relying on flush side
effects. The test passes against both the pre- and post-fix code; its
purpose is to lock that contract in.

Run: pytest tests/test_documents_bulk_delete.py
"""
import asyncio

import pytest
from sqlalchemy import event

import routes.documents as docs_route
from routes.documents import BulkDeleteRequest
from models import Client, Document

_ORG_ID = 17


@pytest.fixture
def request_stub(mock_request):
    mock_request.cookies = {}
    mock_request.state.org_id = _ORG_ID
    return mock_request


def _seed(db, n):
    """One client + n documents (no file_path so os.remove is never called)."""
    client = Client(org_id=_ORG_ID, first_name="C", last_name="X")
    db.add(client)
    db.flush()
    ids = []
    for i in range(n):
        doc = Document(
            org_id=_ORG_ID,
            client_id=client.id,
            name=f"Doc {i}",
            file_path=None,
        )
        db.add(doc)
        db.flush()
        ids.append(doc.id)
    db.commit()
    return ids


def _count_selects(db, monkeypatch, request_stub, ids):
    monkeypatch.setattr(docs_route, "get_current_user", lambda req, d: object())

    selects = []
    engine = db.get_bind()

    def _on_exec(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(engine, "before_cursor_execute", _on_exec)
    try:
        result = asyncio.run(
            docs_route.bulk_delete(request_stub, data=BulkDeleteRequest(ids=ids), db=db)
        )
    finally:
        event.remove(engine, "before_cursor_execute", _on_exec)

    return result, len(selects)


def test_bulk_delete_uses_one_select_for_all_ids(db, monkeypatch, request_stub):
    """SELECT count is constant in n: the per-id lookup is batched via .in_."""
    n = 8
    ids = _seed(db, n)
    result, select_count = _count_selects(db, monkeypatch, request_stub, ids)

    assert result == {"deleted": n}
    # 1 .in_ batch SELECT (+ small ORM overhead). Pre-fix: 1 per id = n.
    assert select_count <= 3, (
        f"{select_count} SELECTs for n={n} ids — expected ~1 (.in_ batch), "
        f"not the pre-fix per-id pattern"
    )


def test_bulk_delete_dedupes_duplicate_ids(db, monkeypatch, request_stub):
    """Non-regression guard: a duplicated id in the request list must not
    double-count `deleted`. Pre-fix this held by accident via SA autoflush;
    post-fix it holds because `.in_` returns each row once."""
    ids = _seed(db, 3)
    duplicated = ids + ids   # request each id twice
    result, _ = _count_selects(db, monkeypatch, request_stub, duplicated)
    assert result == {"deleted": 3}, (
        f"expected 3 (unique docs) but got {result['deleted']}"
    )
