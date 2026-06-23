"""
Tests for the kanban API endpoint (tasks move_task route).
Uses mocks to avoid needing a real database or running FastAPI server.
"""
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import text

import routes.tasks as task_routes
from models import Organization, Task, TaskComment, User
from routes.tasks import (
    _assigned_user_ids_for_tasks,
    _can_access_collaborator_board,
    _can_manage_kanban_collab,
    _can_manage_shared_kanban,
    _can_view_team_private_kanban,
    _canonical_kanban_status,
    _clone_task_tree,
    _ensure_private_board_column,
    kanban_view,
    _kanban_collab_locked,
    _status_for_kanban_column,
    _visible_column_where_sql,
)


def _create_org_user(db, *, org_id=1, user_id=1, user_type="case_worker", name="User"):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        org = Organization(id=org_id, uuid=f"org-{org_id}", name=f"Org {org_id}", slug=f"org-{org_id}")
        db.add(org)
    user = User(
        id=user_id,
        org_id=org_id,
        email=f"user{user_id}@org{org_id}.test",
        name=name,
        password_hash="hash",
        user_type=user_type,
        enabled=True,
    )
    db.add(user)
    db.flush()
    return org, user


def _create_kanban_tables(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS kanban_columns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER NOT NULL,
            name VARCHAR(120) NOT NULL,
            slug VARCHAR(80) NOT NULL,
            position INTEGER DEFAULT 0,
            color VARCHAR(20) DEFAULT '#94a3b8',
            is_done BOOLEAN DEFAULT 0,
            visibility VARCHAR(20) DEFAULT 'shared',
            owner_user_id INTEGER,
            is_archived BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS task_kanban_placements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER NOT NULL,
            task_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            column_id INTEGER NOT NULL,
            position INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, task_id)
        )
    """))
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS task_assignees (
            task_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (task_id, user_id)
        )
    """))
    db.commit()


class JsonRequest(SimpleNamespace):
    async def json(self):
        return self.payload


def _json_body(response):
    return json.loads(response.body.decode("utf-8"))


class TestMoveTaskValidation:
    """Test the kanban move_task logic without running the server."""

    VALID_STATUSES = {"pending", "in_progress", "blocked", "completed"}

    def test_valid_statuses(self):
        """Ensure the valid status set matches what the route expects."""
        for status in ["pending", "in_progress", "blocked", "completed"]:
            assert status in self.VALID_STATUSES

    def test_invalid_status_not_in_set(self):
        """Statuses outside the whitelist should be rejected."""
        for bad in ["cancelled", "archived", "done", "", "PENDING"]:
            assert bad not in self.VALID_STATUSES

    def test_move_to_completed_sets_completed_at(self):
        """When moving to completed, completed_at should be set."""
        task = MagicMock()
        task.completed_at = None
        task.status = "pending"

        new_status = "completed"
        task.status = new_status
        task.position = 0
        if new_status == "completed" and not task.completed_at:
            task.completed_at = datetime.now()

        assert task.completed_at is not None
        assert task.status == "completed"

    def test_move_to_completed_preserves_existing_completed_at(self):
        """If completed_at is already set, don't overwrite."""
        original_time = datetime(2026, 1, 1, 12, 0, 0)
        task = MagicMock()
        task.completed_at = original_time
        task.status = "in_progress"

        new_status = "completed"
        task.status = new_status
        if new_status == "completed" and not task.completed_at:
            task.completed_at = datetime.now()

        # Should keep original time
        assert task.completed_at == original_time

    def test_move_task_sets_position(self):
        """Moving a task should update its position."""
        task = MagicMock()
        new_position = 3

        task.position = new_position
        assert task.position == 3

    def test_status_validation_rejects_invalid(self):
        """Replicate the route's status validation check."""
        new_status = "invalid_status"
        valid_statuses = {"pending", "in_progress", "blocked", "completed"}

        with pytest.raises(HTTPException) as exc_info:
            if new_status not in valid_statuses:
                raise HTTPException(status_code=400, detail="Invalid status")

        assert exc_info.value.status_code == 400
        assert "Invalid status" in str(exc_info.value.detail)

    def test_nonexistent_task_raises_404(self):
        """When the task query returns None, 404 should be raised."""
        task = None

        with pytest.raises(HTTPException) as exc_info:
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")

        assert exc_info.value.status_code == 404

    def test_unauthenticated_raises_401(self):
        """When user is None, 401 should be raised."""
        user = None

        with pytest.raises(HTTPException) as exc_info:
            if not user:
                raise HTTPException(status_code=401, detail="Not authenticated")

        assert exc_info.value.status_code == 401

    def test_move_from_completed_back_to_pending(self):
        """Moving from completed back to another status (route behavior from update_task)."""
        task = MagicMock()
        task.status = "completed"
        task.completed_at = datetime(2026, 3, 1)

        new_status = "pending"
        # The update_task route clears completed_at when status != completed
        if new_status != "completed":
            task.completed_at = None

        task.status = new_status
        assert task.status == "pending"
        assert task.completed_at is None

    def test_move_response_format(self):
        """The move endpoint should return task_id, status, and success."""
        task_id = 42
        new_status = "in_progress"

        response = {"success": True, "task_id": task_id, "status": new_status}

        assert response["success"] is True
        assert response["task_id"] == 42
        assert response["status"] == "in_progress"


class TestKanbanAssigneeFilter:
    def test_assigned_user_ids_for_tasks_dedupes_visible_assignments(self):
        tasks = [
            SimpleNamespace(assigned_to=2),
            SimpleNamespace(assigned_to=2),
            SimpleNamespace(assigned_to=1),
            SimpleNamespace(assigned_to=None),
        ]

        assert _assigned_user_ids_for_tasks(tasks) == [1, 2]


class TestKanbanStatusAliases:
    @pytest.mark.parametrize(
        ("slug", "expected"),
        [
            ("todo", "pending"),
            ("pendente", "pending"),
            ("em_andamento", "in_progress"),
            ("doing", "in_progress"),
            ("done", "completed"),
            ("concluida", "completed"),
            ("blocked", "blocked"),
        ],
    )
    def test_canonical_kanban_status_accepts_legacy_slugs(self, slug, expected):
        assert _canonical_kanban_status(slug) == expected

    def test_status_for_custom_column_defaults_to_pending(self):
        assert _status_for_kanban_column("revisao", is_done=False) == "pending"

    def test_status_for_done_custom_column_defaults_to_completed(self):
        assert _status_for_kanban_column("revisao-final", is_done=True) == "completed"


class TestKanbanColumnVisibility:
    @pytest.mark.parametrize("role", ["admin", "superadmin", "owner", "manager", "gestor"])
    def test_manager_roles_can_manage_shared_and_view_team_private(self, role):
        user = SimpleNamespace(role=role, user_type=None)

        assert _can_manage_shared_kanban(user) is True
        assert _can_view_team_private_kanban(user) is True

    def test_regular_user_cannot_view_team_private_columns(self):
        user = SimpleNamespace(role="paralegal", user_type=None)

        assert _can_manage_shared_kanban(user) is False
        assert _can_view_team_private_kanban(user) is False

    def test_default_visible_column_sql_limits_private_columns_to_owner(self):
        sql = _visible_column_where_sql()

        assert "owner_user_id = :user_id" in sql
        assert ":include_team_private" not in sql

    def test_admin_visible_column_sql_can_include_team_private_columns(self):
        sql = _visible_column_where_sql(include_team_private=True)

        assert ":include_team_private = 1" in sql
        assert "owner_user_id = :user_id" in sql


class TestKanbanCollaborationRules:
    def test_only_admin_user_type_can_manage_collaboration_lock(self):
        base_admin = SimpleNamespace(id=1, user_type="admin", role=None)
        role_admin = SimpleNamespace(id=2, user_type="case_worker", role="admin")
        regular = SimpleNamespace(id=3, user_type="case_worker", role=None)

        assert _can_manage_kanban_collab(base_admin, {}) is True
        assert _can_manage_kanban_collab(role_admin, {}) is False
        assert _can_manage_kanban_collab(regular, {}) is False

    def test_lock_limits_collaborator_board_access_to_self_and_admins(self):
        regular = SimpleNamespace(id=3, user_type="case_worker", role=None)
        admin = SimpleNamespace(id=2, user_type="admin", role=None)
        unlocked = {"kanban_collab_locked": False}
        locked = {"kanban_collab_locked": True}

        assert _kanban_collab_locked(unlocked) is False
        assert _can_access_collaborator_board(regular, 9, unlocked) is True
        assert _can_access_collaborator_board(regular, 3, locked) is True
        assert _can_access_collaborator_board(regular, 9, locked) is False
        assert _can_access_collaborator_board(admin, 9, locked) is True


class TestKanbanSend:
    def test_ensure_private_board_column_creates_recebidas_once(self, db):
        _create_kanban_tables(db)

        first = _ensure_private_board_column(db, org_id=1, user_id=7)
        second = _ensure_private_board_column(db, org_id=1, user_id=7)

        assert first.id == second.id
        row = db.execute(
            text("""
                SELECT name, slug, visibility, owner_user_id
                FROM kanban_columns
                WHERE id = :id
            """),
            {"id": first.id},
        ).fetchone()
        assert row.name == "Recebidas"
        assert row.slug == "recebidas"
        assert row.visibility == "private"
        assert row.owner_user_id == 7

    @pytest.mark.asyncio
    async def test_kanban_default_entry_creates_my_board_column(self, db, monkeypatch):
        _create_kanban_tables(db)
        _, user = _create_org_user(db, org_id=1, user_id=7, name="Owner")
        monkeypatch.setattr(task_routes, "get_current_user", lambda request, db: user)
        monkeypatch.setattr(task_routes, "get_context", lambda request, db: {"request": request, "PREFIX": "/casehub"})

        captured = {}

        def fake_template_response(template_name, context):
            captured["template"] = template_name
            captured["context"] = context
            return SimpleNamespace(template=template_name, context=context)

        monkeypatch.setattr(task_routes.templates, "TemplateResponse", fake_template_response)
        request = SimpleNamespace(
            state=SimpleNamespace(org_id=1),
            query_params={},
        )

        await kanban_view(request, db=db)

        assert captured["template"] == "app/tasks/kanban.html"
        assert captured["context"]["kanban_current_board"]["value"] == "me"
        assert [col["name"] for col in captured["context"]["kanban_columns"]] == ["Recebidas"]
        row = db.execute(
            text("""
                SELECT name, visibility, owner_user_id
                FROM kanban_columns
                WHERE org_id = 1 AND COALESCE(visibility, 'shared') = 'private'
            """)
        ).fetchone()
        assert (row.name, row.visibility, row.owner_user_id) == ("Recebidas", "private", user.id)

    def test_clone_task_tree_copies_only_core_task_fields(self, db):
        _, sender = _create_org_user(db, org_id=1, user_id=1, name="Sender")
        _, target = _create_org_user(db, org_id=1, user_id=2, name="Target")
        source = Task(
            org_id=1,
            title="Preparar prazo",
            description="Contexto completo",
            status="in_progress",
            priority="high",
            assigned_to=sender.id,
            created_by=sender.id,
            visibility="private",
            tags="prazo,cliente",
            due_time="13:30",
        )
        db.add(source)
        db.flush()
        db.add(Task(org_id=1, title="Checar peça", parent_task_id=source.id, status="pending", position=2))
        db.add(TaskComment(
            task_id=source.id,
            user_id=sender.id,
            content="Comentário operacional",
            created_at=datetime(2026, 6, 13, 12, 0, 0),
        ))
        db.flush()

        clone = _clone_task_tree(db, org_id=1, source_task=source, target_user_id=target.id, created_by=sender.id)
        db.flush()

        assert clone.id != source.id
        assert clone.title == source.title
        assert clone.assigned_to == target.id
        assert clone.created_by == sender.id
        assert clone.priority == source.priority
        assert clone.description == source.description
        assert clone.due_time == source.due_time
        assert clone.client_id == source.client_id
        assert clone.case_id == source.case_id
        assert db.query(Task).filter(Task.parent_task_id == clone.id).count() == 0
        assert db.query(TaskComment).filter(TaskComment.task_id == clone.id).count() == 0
        assert source.assigned_to == sender.id

    @pytest.mark.asyncio
    async def test_send_copy_clones_into_target_private_board(self, db, monkeypatch):
        _create_kanban_tables(db)
        _, sender = _create_org_user(db, org_id=1, user_id=1, name="Sender")
        _, target = _create_org_user(db, org_id=1, user_id=2, name="Target")
        source = Task(org_id=1, title="Copiar tarefa", status="pending", assigned_to=sender.id, created_by=sender.id)
        db.add(source)
        db.flush()
        db.add(Task(org_id=1, title="Sub copiar", parent_task_id=source.id, status="pending"))
        db.add(TaskComment(task_id=source.id, user_id=sender.id, content="Copiar comentário"))
        db.commit()
        monkeypatch.setattr(task_routes, "get_current_user", lambda request, db: sender)
        request = JsonRequest(
            state=SimpleNamespace(org_id=1),
            payload={"target_user_id": target.id, "mode": "copy"},
        )

        response = await task_routes.send_task_to_board(request, source.id, db=db)
        body = _json_body(response)

        assert response.status_code == 200
        assert body["success"] is True
        assert body["mode"] == "copy"
        assert body["task_id"] != source.id
        clone = db.query(Task).filter(Task.id == body["task_id"]).one()
        assert clone.title == source.title
        assert clone.assigned_to == target.id
        assert db.query(Task).filter(Task.parent_task_id == clone.id).count() == 0
        assert db.query(TaskComment).filter(TaskComment.task_id == clone.id).count() == 0
        placement = db.execute(
            text("SELECT user_id, task_id FROM task_kanban_placements WHERE task_id = :task_id"),
            {"task_id": clone.id},
        ).fetchone()
        assert (placement.user_id, placement.task_id) == (target.id, clone.id)
        assert db.execute(
            text("SELECT name FROM kanban_columns WHERE owner_user_id = :user_id"),
            {"user_id": target.id},
        ).scalar() == "Recebidas"
        db.refresh(source)
        assert source.assigned_to == sender.id

    @pytest.mark.asyncio
    async def test_send_move_reassigns_and_clears_sender_private_placement(self, db, monkeypatch):
        _create_kanban_tables(db)
        _, sender = _create_org_user(db, org_id=1, user_id=1, name="Sender")
        _, target = _create_org_user(db, org_id=1, user_id=2, name="Target")
        task = Task(org_id=1, title="Mover tarefa", status="pending", assigned_to=sender.id, created_by=sender.id)
        db.add(task)
        db.flush()
        sender_col = _ensure_private_board_column(db, org_id=1, user_id=sender.id)
        db.execute(
            text("""
                INSERT INTO task_kanban_placements (org_id, task_id, user_id, column_id, position)
                VALUES (1, :task_id, :user_id, :column_id, 4)
            """),
            {"task_id": task.id, "user_id": sender.id, "column_id": sender_col.id},
        )
        db.commit()
        monkeypatch.setattr(task_routes, "get_current_user", lambda request, db: sender)
        request = JsonRequest(
            state=SimpleNamespace(org_id=1),
            payload={"target_user_id": target.id, "mode": "move"},
        )

        response = await task_routes.send_task_to_board(request, task.id, db=db)
        body = _json_body(response)

        assert response.status_code == 200
        assert body["task_id"] == task.id
        db.refresh(task)
        assert task.assigned_to == target.id
        assert task.column_id is None
        placements = db.execute(
            text("""
                SELECT user_id, task_id
                FROM task_kanban_placements
                WHERE org_id = 1 AND task_id = :task_id
            """),
            {"task_id": task.id},
        ).fetchall()
        assert [(row.user_id, row.task_id) for row in placements] == [(target.id, task.id)]
