"""
Tests for Kanban card document attachments (FB3, alpha UsuarioDemo).

Covers the new endpoints in `routes.tasks`:
  - POST /tasks/api/{task_id}/document  → upload a file, creates a Document
        row with task_id set (Trello-style card attachment).
  - GET  /tasks/api/{task_id}/documents → list attachments of a task.
  - GET  /tasks/api/{task_id}/document/{doc_id} → download one attachment.

The attachment pipeline reuses the same guards as routes.documents.upload
(filename sanitize / path-traversal, extension allowlist, size cap, SHA256
content hash). Everything must stay org-scoped via tenant_query +
_visible_task_filter so a card from another tenant never leaks.

These run against the real in-memory SQLite DB (conftest fixtures) so the
multi-tenant isolation and the idempotent migration are genuinely exercised,
not mocked.
"""
import io
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from starlette.datastructures import Headers, UploadFile

import routes.tasks as task_routes
from models import Organization, Task, User, Document
from models.tenant import tenant_query


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class _Req(SimpleNamespace):
    """Minimal stand-in for a FastAPI Request carrying request.state.org_id."""


def _request(org_id):
    return _Req(state=SimpleNamespace(org_id=org_id))


def _seed_org_user(db, *, org_id, user_id):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        org = Organization(id=org_id, uuid=f"org-{org_id}", name=f"Org {org_id}", slug=f"org-{org_id}")
        db.add(org)
    user = User(
        id=user_id,
        org_id=org_id,
        email=f"u{user_id}@org{org_id}.test",
        name=f"User {user_id}",
        password_hash="hash",
        user_type="case_worker",
        enabled=True,
    )
    db.add(user)
    db.flush()
    return org, user


def _seed_task(db, *, org_id, user_id, title="Card"):
    task = Task(
        title=title,
        status="pending",
        priority="medium",
        org_id=org_id,
        created_by=user_id,
        visibility="org",
    )
    db.add(task)
    db.flush()
    return task


def _upload(content=b"%PDF-1.4\nfake-pdf\n", filename="anexo.pdf", content_type="application/pdf"):
    return UploadFile(
        file=io.BytesIO(content),
        size=len(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


# ---------------------------------------------------------------------------
# Migration idempotency
# ---------------------------------------------------------------------------
class TestSchemaMigration:
    def test_ensure_kanban_schema_adds_documents_task_id_idempotent(self, db):
        from sqlalchemy import text

        def _cols():
            return {row[1] for row in db.execute(text("PRAGMA table_info(documents)")).fetchall()}

        # On the test DB the model already declares task_id (create_all). To prove
        # the runtime ALTER path (the one that matters for a legacy Postgres DB
        # that predates this column), rebuild a documents table WITHOUT task_id.
        db.execute(text("DROP TABLE IF EXISTS documents"))
        db.execute(text(
            "CREATE TABLE documents (id INTEGER PRIMARY KEY, name VARCHAR(255), org_id INTEGER)"
        ))
        db.commit()
        assert "task_id" not in _cols()

        # First run adds the column.
        task_routes._ensure_kanban_schema(db)
        assert "task_id" in _cols()

        # Second run must NOT raise (idempotent) and column still present.
        task_routes._ensure_kanban_schema(db)
        assert "task_id" in _cols()


# ---------------------------------------------------------------------------
# Upload endpoint
# ---------------------------------------------------------------------------
class TestAttachDocument:
    @pytest.mark.asyncio
    async def test_upload_creates_document_with_task_id(self, db, tmp_path):
        _, user = _seed_org_user(db, org_id=1, user_id=1)
        task = _seed_task(db, org_id=1, user_id=1)
        db.commit()

        with patch.object(task_routes, "get_current_user", return_value=user), \
             patch.object(task_routes, "UPLOAD_DIR", str(tmp_path)):
            resp = await task_routes.attach_task_document(
                _request(1), task.id, file=_upload(), db=db
            )

        assert resp.status_code == 200
        doc = tenant_query(db, Document, 1).filter(Document.task_id == task.id).first()
        assert doc is not None
        assert doc.task_id == task.id
        assert doc.org_id == 1
        assert doc.uploaded_by == user.id
        assert doc.file_hash  # SHA256 computed
        assert os.path.exists(doc.file_path)

    @pytest.mark.asyncio
    async def test_upload_rejects_disallowed_extension(self, db, tmp_path):
        _, user = _seed_org_user(db, org_id=1, user_id=1)
        task = _seed_task(db, org_id=1, user_id=1)
        db.commit()

        with patch.object(task_routes, "get_current_user", return_value=user), \
             patch.object(task_routes, "UPLOAD_DIR", str(tmp_path)):
            resp = await task_routes.attach_task_document(
                _request(1), task.id,
                file=_upload(content=b"#!/bin/sh\n", filename="evil.sh", content_type="text/x-sh"),
                db=db,
            )
        assert resp.status_code == 400
        assert tenant_query(db, Document, 1).count() == 0

    @pytest.mark.asyncio
    async def test_upload_unauthenticated_401(self, db, tmp_path):
        task = _seed_task(db, org_id=1, user_id=1)
        db.commit()
        with patch.object(task_routes, "get_current_user", return_value=None):
            resp = await task_routes.attach_task_document(
                _request(1), task.id, file=_upload(), db=db
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_cross_tenant_task_404(self, db, tmp_path):
        # User belongs to org 1; task belongs to org 2. Must NOT attach.
        _, user1 = _seed_org_user(db, org_id=1, user_id=1)
        _seed_org_user(db, org_id=2, user_id=2)
        task_org2 = _seed_task(db, org_id=2, user_id=2)
        db.commit()

        with patch.object(task_routes, "get_current_user", return_value=user1), \
             patch.object(task_routes, "UPLOAD_DIR", str(tmp_path)):
            resp = await task_routes.attach_task_document(
                _request(1), task_org2.id, file=_upload(), db=db
            )
        assert resp.status_code == 404
        # No document leaked into either org.
        assert db.query(Document).count() == 0


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------
class TestListDocuments:
    @pytest.mark.asyncio
    async def test_list_returns_task_attachments(self, db, tmp_path):
        _, user = _seed_org_user(db, org_id=1, user_id=1)
        task = _seed_task(db, org_id=1, user_id=1)
        db.commit()

        with patch.object(task_routes, "get_current_user", return_value=user), \
             patch.object(task_routes, "UPLOAD_DIR", str(tmp_path)):
            await task_routes.attach_task_document(_request(1), task.id, file=_upload(filename="a.pdf"), db=db)
            await task_routes.attach_task_document(_request(1), task.id, file=_upload(filename="b.pdf"), db=db)
            resp = await task_routes.list_task_documents(_request(1), task.id, db=db)

        import json
        body = json.loads(resp.body.decode())
        assert body["success"] is True
        names = sorted(d["name"] for d in body["documents"])
        assert names == ["a.pdf", "b.pdf"]
        assert all("download_url" in d for d in body["documents"])

    @pytest.mark.asyncio
    async def test_list_does_not_leak_cross_tenant(self, db, tmp_path):
        # Two orgs, one task each, one attachment each. Org 1 must only see its own.
        _, user1 = _seed_org_user(db, org_id=1, user_id=1)
        _, user2 = _seed_org_user(db, org_id=2, user_id=2)
        task1 = _seed_task(db, org_id=1, user_id=1, title="t1")
        task2 = _seed_task(db, org_id=2, user_id=2, title="t2")
        db.commit()

        with patch.object(task_routes, "UPLOAD_DIR", str(tmp_path)):
            with patch.object(task_routes, "get_current_user", return_value=user1):
                await task_routes.attach_task_document(_request(1), task1.id, file=_upload(filename="own.pdf"), db=db)
            with patch.object(task_routes, "get_current_user", return_value=user2):
                await task_routes.attach_task_document(_request(2), task2.id, file=_upload(filename="other.pdf"), db=db)

            # Org 1 listing its own task: sees only own.pdf.
            with patch.object(task_routes, "get_current_user", return_value=user1):
                resp_own = await task_routes.list_task_documents(_request(1), task1.id, db=db)
                # Org 1 trying to read org 2's task id → 404, never the cross-tenant doc.
                resp_cross = await task_routes.list_task_documents(_request(1), task2.id, db=db)

        import json
        own = json.loads(resp_own.body.decode())
        assert [d["name"] for d in own["documents"]] == ["own.pdf"]
        assert resp_cross.status_code == 404


# ---------------------------------------------------------------------------
# Delete endpoint
# ---------------------------------------------------------------------------
class TestDeleteDocument:
    @pytest.mark.asyncio
    async def test_delete_removes_task_attachment_without_deleting_task(self, db, tmp_path):
        _, user = _seed_org_user(db, org_id=1, user_id=1)
        task = _seed_task(db, org_id=1, user_id=1)
        db.commit()

        with patch.object(task_routes, "get_current_user", return_value=user), \
             patch.object(task_routes, "UPLOAD_DIR", str(tmp_path)):
            await task_routes.attach_task_document(_request(1), task.id, file=_upload(filename="wrong.pdf"), db=db)
            doc = tenant_query(db, Document, 1).filter(Document.task_id == task.id).one()
            doc_id = doc.id
            file_path = doc.file_path

            resp = await task_routes.delete_task_document(_request(1), task.id, doc_id, db=db)

        import json
        body = json.loads(resp.body.decode())
        assert resp.status_code == 200
        assert body == {"success": True, "task_id": task.id, "document_id": doc_id}
        assert tenant_query(db, Document, 1).filter(Document.task_id == task.id).count() == 0
        assert tenant_query(db, Task, 1).filter(Task.id == task.id).first() is not None
        assert not os.path.exists(file_path)

    @pytest.mark.asyncio
    async def test_delete_does_not_remove_cross_tenant_attachment(self, db, tmp_path):
        _, user1 = _seed_org_user(db, org_id=1, user_id=1)
        _, user2 = _seed_org_user(db, org_id=2, user_id=2)
        task1 = _seed_task(db, org_id=1, user_id=1, title="own")
        task2 = _seed_task(db, org_id=2, user_id=2, title="other")
        db.commit()

        with patch.object(task_routes, "UPLOAD_DIR", str(tmp_path)):
            with patch.object(task_routes, "get_current_user", return_value=user2):
                await task_routes.attach_task_document(_request(2), task2.id, file=_upload(filename="other.pdf"), db=db)
            doc = tenant_query(db, Document, 2).filter(Document.task_id == task2.id).one()
            doc_id = doc.id
            file_path = doc.file_path

            with patch.object(task_routes, "get_current_user", return_value=user1):
                resp = await task_routes.delete_task_document(_request(1), task2.id, doc_id, db=db)

        assert resp.status_code == 404
        assert tenant_query(db, Document, 2).filter(Document.id == doc_id).first() is not None
        assert os.path.exists(file_path)
        assert tenant_query(db, Task, 1).filter(Task.id == task1.id).first() is not None


# ---------------------------------------------------------------------------
# UI contract — the modal must expose the "Anexos" section + wiring
# ---------------------------------------------------------------------------
class TestKanbanAttachmentUI:
    def test_template_has_attachment_section_and_js(self):
        from pathlib import Path
        html = (Path(__file__).resolve().parent.parent / "templates" / "app" / "tasks" / "kanban.html").read_text()
        # Markup
        assert 'id="ch-task-modal-attachments"' in html
        assert 'id="ch-task-modal-attach-input"' in html
        assert 'id="ch-task-modal-attach-add"' in html
        assert "Anexar documento" in html
        # JS wiring hits the new endpoints
        assert "/tasks/api/' + _modalCurrentTaskId + '/document'" in html
        assert "/tasks/api/' + _modalCurrentTaskId + '/document/' + docId" in html
        assert "data-attachment-remove" in html
        assert "/tasks/api/' + taskId + '/documents'" in html
        assert "loadAttachments(data.id)" in html
        assert "renderAttachmentRow" in html
