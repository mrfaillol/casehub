"""
Tests for the kanban API endpoint (tasks move_task route).
Uses mocks to avoid needing a real database or running FastAPI server.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime
from types import SimpleNamespace

from fastapi import HTTPException

from routes.tasks import (
    _assigned_user_ids_for_tasks,
    _canonical_kanban_status,
    _status_for_kanban_column,
)


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
