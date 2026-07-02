"""Regression test for the 2026-07-01 prod-outage-class lock-queue mitigation
applied to routes/calendar.py's lazy per-request schema-ensure helper.

Same rationale as tests/test_app_factory_lock_timeout_migration.py: ALTER
TABLE ADD COLUMN needs an ACCESS EXCLUSIVE lock, and `appointments` is a
high-traffic table. `_ensure_appointment_feedback_schema` runs on nearly
every calendar request (lazy per-request migration, called before reading/
writing appointment checklist/attachment columns); if some other session is
idle-in-transaction holding a lock on `appointments` when this fires, the
ALTER queues indefinitely and everything else on the table queues FIFO
behind it. Bound the wait with `SET LOCAL lock_timeout` before the ALTER —
Postgres only (SQLite has no session-scoped lock_timeout and doesn't need
one for this single-writer scenario).

Exercises the helper with a fake Session double (no Postgres available in
this sandbox) recording the exact sequence of `db.execute(...)` calls.
"""
import routes.calendar as calendar_routes


class _FakeDialect:
    def __init__(self, name):
        self.name = name


class _FakeBind:
    def __init__(self, dialect_name):
        self.dialect = _FakeDialect(dialect_name)


class _FakeResult:
    def first(self):
        return None

    def fetchall(self):
        return []


class _FakeSession:
    """Records every db.execute(...) call, tagged by SQL shape."""

    def __init__(self, dialect_name):
        self._bind = _FakeBind(dialect_name)
        self.order = []

    def get_bind(self):
        return self._bind

    def execute(self, clause, params=None):
        sql = str(clause)
        if "CREATE TABLE" in sql:
            self.order.append("create_table")
        elif "CREATE INDEX" in sql:
            self.order.append("create_index")
        elif "SET LOCAL lock_timeout" in sql:
            self.order.append("set_lock_timeout")
        elif "information_schema.columns" in sql:
            self.order.append("check_exists_pg")
        elif "PRAGMA table_info" in sql:
            self.order.append("check_exists_sqlite")
        elif "ALTER TABLE" in sql:
            self.order.append(("alter", sql))
        else:
            self.order.append(("other", sql))
        return _FakeResult()

    def commit(self):
        self.order.append("commit")

    def rollback(self):
        self.order.append("rollback")


def _alter_events(order):
    return [item for item in order if isinstance(item, tuple) and item[0] == "alter"]


def test_postgres_sets_lock_timeout_before_each_alter():
    db = _FakeSession("postgresql")

    calendar_routes._ensure_appointment_feedback_schema(db)

    # Two additive columns are declared on "appointments": checklist, attachments.
    alters = _alter_events(db.order)
    assert len(alters) == 2, f"expected 2 ALTER TABLE calls, got: {db.order}"

    for i, item in enumerate(db.order):
        if isinstance(item, tuple) and item[0] == "alter":
            assert db.order[i - 1] == "set_lock_timeout", (
                "SET LOCAL lock_timeout must be issued immediately before "
                "each ALTER TABLE on postgres — otherwise a busy "
                "`appointments` table can queue this lazy per-request "
                "migration (and everything behind it) indefinitely, same "
                "incident class as the 2026-07-01 prod outage."
            )


def test_sqlite_never_sets_lock_timeout():
    db = _FakeSession("sqlite")

    calendar_routes._ensure_appointment_feedback_schema(db)

    assert "set_lock_timeout" not in db.order, (
        "SQLite has no session-scoped lock_timeout statement — issuing "
        "SET LOCAL against it would just raise and get swallowed by the "
        "bare except, silently skipping the column migration."
    )
    alters = _alter_events(db.order)
    assert len(alters) == 2, f"expected 2 ALTER TABLE calls, got: {db.order}"
