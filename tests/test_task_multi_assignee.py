"""Regression tests for Kanban task multi-assignee support."""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import routes.tasks as tasks


def test_coerce_task_assignee_ids_accepts_arrays_form_lists_and_legacy_scalar():
    class FormLike:
        def __init__(self, values):
            self.values = values

        def getlist(self, key):
            return self.values.get(key, [])

        def get(self, key):
            return self.values.get(key)

    assert tasks._coerce_task_assignee_ids({"assigned_to_ids": ["2", 2, "3", "", "x"]}) == [2, 3]
    assert tasks._coerce_task_assignee_ids({"assigned_to": "4"}) == [4]
    assert tasks._coerce_task_assignee_ids({"assigned_to_ids": []}) == []
    assert tasks._coerce_task_assignee_ids(FormLike({"assigned_to_ids": ["7", "7", "8"]})) == [7, 8]
    assert tasks._coerce_task_assignee_ids(FormLike({"assigned_to": "9"})) == [9]


def test_task_multi_assignee_migration_keeps_junction_table_and_backfill():
    with open("migrations/2026-06-13_task_multi_assignee.sql", encoding="utf-8") as fh:
        sql = fh.read()

    assert "CREATE TABLE IF NOT EXISTS task_assignees" in sql
    assert "REFERENCES tasks(id) ON DELETE CASCADE" in sql
    assert "REFERENCES users(id) ON DELETE CASCADE" in sql
    assert "PRIMARY KEY (task_id, user_id)" in sql
    assert "SELECT id, assigned_to" in sql
    assert "ON CONFLICT DO NOTHING" in sql


def test_task_visibility_and_user_filter_include_junction_table():
    visible_source = inspect.getsource(tasks._visible_task_filter)
    filter_source = inspect.getsource(tasks._assigned_to_user_filter)

    assert "task_assignees ta_visible" in visible_source
    assert "task_assignees ta_filter" in filter_source
    assert "Task.assigned_to == user_id" in visible_source
    assert "Task.assigned_to == user_id" in filter_source


def test_assigned_user_ids_for_tasks_includes_legacy_and_junction_ids():
    task_rows = [
        SimpleNamespace(id=10, assigned_to=2),
        SimpleNamespace(id=11, assigned_to=None),
    ]

    class Db:
        def execute(self, *args, **kwargs):
            return SimpleNamespace(
                fetchall=lambda: [
                    SimpleNamespace(task_id=10, user_id=3),
                    SimpleNamespace(task_id=11, user_id=4),
                ]
            )

    assert tasks._assigned_user_ids_for_tasks(task_rows, db=Db()) == [2, 3, 4]


def test_task_detail_and_update_contract_use_assigned_to_ids():
    detail_source = inspect.getsource(tasks.get_task_detail)
    update_source = inspect.getsource(tasks.update_task_api)

    assert '"assigned_to_ids": assignee_ids' in detail_source
    assert '"assigned_to_ids" in body or "assigned_to" in body' in update_source
    assert "_validate_task_assignee_ids" in update_source
    assert "_save_task_assignees(db, task.id, assignee_ids)" in update_source
    assert "_notify_new_task_assignees" in update_source


def test_kanban_template_uses_checkbox_picker_and_avatar_stack():
    with open("templates/app/tasks/kanban.html", encoding="utf-8") as fh:
        template = fh.read()

    assert "data-assignee-checkbox" in template
    assert 'name="assigned_to_ids"' in template
    assert "selectedAssigneeIds()" in template
    assert "setAssigneeSelection(data.assigned_to_ids" in template
    assert "ch-task-card__avatars" in template
    assert "+{{ _assignees|length - 3 }}" in template
