"""
Tests for models.task - Task model including subtasks, dependencies, and kanban position.
"""
import pytest
from datetime import datetime, date

from models.task import Task, Reminder
from tests.conftest import TestSession


class TestTaskModel:
    """Tests for the Task SQLAlchemy model."""

    def test_create_basic_task(self, db):
        task = Task(title="File I-130")
        db.add(task)
        db.flush()

        assert task.id is not None
        assert task.title == "File I-130"
        assert task.status == "pending"
        assert task.priority == "medium"

    def test_task_default_position_is_zero(self, db):
        task = Task(title="Default position task")
        db.add(task)
        db.flush()

        assert task.position == 0

    def test_task_default_depends_on_is_empty(self, db):
        task = Task(title="No dependencies")
        db.add(task)
        db.flush()

        assert task.depends_on == [] or task.depends_on is None

    def test_task_with_parent_task_id(self, db):
        parent = Task(title="Parent task")
        db.add(parent)
        db.flush()

        child = Task(title="Subtask", parent_task_id=parent.id)
        db.add(child)
        db.flush()

        assert child.parent_task_id == parent.id

    def test_task_subtasks_relationship(self, db):
        parent = Task(title="Parent")
        db.add(parent)
        db.flush()

        child1 = Task(title="Child 1", parent_task_id=parent.id)
        child2 = Task(title="Child 2", parent_task_id=parent.id)
        db.add_all([child1, child2])
        db.flush()

        # Refresh to load relationships
        db.refresh(parent)
        subtask_titles = sorted([s.title for s in parent.subtasks])
        assert subtask_titles == ["Child 1", "Child 2"]

    def test_task_parent_task_backref(self, db):
        parent = Task(title="Parent backref test")
        db.add(parent)
        db.flush()

        child = Task(title="Child backref test", parent_task_id=parent.id)
        db.add(child)
        db.flush()
        db.refresh(child)

        assert child.parent_task is not None
        assert child.parent_task.title == "Parent backref test"

    def test_task_with_depends_on(self, db):
        task = Task(title="Dependent task", depends_on=[1, 2, 3])
        db.add(task)
        db.flush()
        db.refresh(task)

        assert task.depends_on == [1, 2, 3]

    def test_task_with_custom_position(self, db):
        task = Task(title="Positioned task", position=5)
        db.add(task)
        db.flush()

        assert task.position == 5

    def test_task_status_values(self, db):
        for status in ["pending", "in_progress", "blocked", "completed"]:
            task = Task(title=f"Task {status}", status=status)
            db.add(task)
            db.flush()
            assert task.status == status

    def test_task_priority_values(self, db):
        for priority in ["low", "medium", "high", "urgent"]:
            task = Task(title=f"Task {priority}", priority=priority)
            db.add(task)
            db.flush()
            assert task.priority == priority

    def test_task_completed_at(self, db):
        now = datetime.now()
        task = Task(title="Done task", status="completed", completed_at=now)
        db.add(task)
        db.flush()

        assert task.completed_at is not None

    def test_task_due_date(self, db):
        due = date(2026, 6, 1)
        task = Task(title="Task with due date", due_date=due)
        db.add(task)
        db.flush()

        assert task.due_date == due


class TestReminderModel:
    """Tests for the Reminder SQLAlchemy model."""

    def test_create_reminder(self, db):
        reminder = Reminder(
            title="Follow up with USCIS",
            due_date=datetime(2026, 4, 15),
        )
        db.add(reminder)
        db.flush()

        assert reminder.id is not None
        assert reminder.is_completed is False

    def test_reminder_complete(self, db):
        now = datetime.now()
        reminder = Reminder(
            title="Completed reminder",
            due_date=datetime(2026, 4, 15),
            is_completed=True,
            completed_at=now,
        )
        db.add(reminder)
        db.flush()

        assert reminder.is_completed is True
        assert reminder.completed_at is not None
