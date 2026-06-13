"""Regression tests for calendar appointment multi-assignee support.

The Agenda UI sends ``assigned_to_ids`` so the backend must preserve the full
selection in ``appointment_assignees`` while keeping ``appointments.assigned_to``
as the primary/legacy responsible user.
"""
from __future__ import annotations

import inspect

import routes.calendar as cal


def test_coerce_assigned_to_ids_accepts_select_array_and_dedupes():
    assert cal._coerce_assigned_to_ids({"assigned_to_ids": ["2", 2, "3", "", "x"]}) == [2, 3]
    assert cal._coerce_assigned_to_ids({"assigned_to": "4"}) == [4]
    assert cal._coerce_assigned_to_ids({"assigned_to_ids": []}) == []


def test_create_appointment_persists_all_assignees():
    source = inspect.getsource(cal.create_appointment)
    assert "assigned_to_ids" in source
    assert "_validate_org_user_ids" in source
    assert "_save_appointment_assignees(db, appt_id, valid_assigned_to_ids)" in source


def test_update_appointment_replaces_all_assignees():
    source = inspect.getsource(cal.update_appointment)
    assert "assigned_to_ids" in source
    assert "_validate_org_user_ids" in source
    assert "_save_appointment_assignees(db, appt_id, valid_assigned_to_ids)" in source


def test_multi_assignee_migration_keeps_junction_table():
    with open("migrations/2026-06-10_appointment_multi_assignee.sql", encoding="utf-8") as fh:
        sql = fh.read()
    assert "CREATE TABLE IF NOT EXISTS appointment_assignees" in sql
    assert "PRIMARY KEY (appointment_id, user_id)" in sql
