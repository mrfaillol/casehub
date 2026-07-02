"""Regression test for the 2026-07-01 prod-outage-class lock-queue mitigation.

Root cause: an ALTER TABLE ADD COLUMN needs an ACCESS EXCLUSIVE lock. If some
other session is idle-in-transaction holding even a plain read lock on the
target table (e.g. a request handler awaiting a slow external HTTP call with
its DB transaction still open — see
tests/test_whatsapp_chat_profile_pic_db_session_leak.py), a lazy startup
schema-ensure ALTER TABLE queues indefinitely for that lock — and Postgres's
FIFO per-relation lock queue then makes every OTHER query on the table queue
behind THAT ALTER, turning one stuck session into a full-site outage.

`core.app_factory._alter_table_add_column_bounded` bounds this: it wraps the
ALTER in a SAVEPOINT with a short `SET LOCAL lock_timeout`, so if the lock
isn't available quickly it gives up (to retry next request/restart) instead
of queuing indefinitely and becoming the new head of the queue that
everything else on the table piles up behind.

These tests exercise the helper directly with a fake Session double (no
Postgres available in this sandbox) to assert:
  - the happy path executes SET LOCAL + ALTER inside a nested transaction
    and commits it
  - a simulated lock-timeout error is swallowed (does not propagate) and
    rolls back only the SAVEPOINT, not the outer transaction
  - SET LOCAL lock_timeout is always issued before the ALTER
"""
from core.app_factory import _alter_table_add_column_bounded


class _FakeSavepoint:
    def __init__(self, order):
        self._order = order

    def commit(self):
        self._order.append("savepoint.commit")

    def rollback(self):
        self._order.append("savepoint.rollback")


class _FakeSession:
    """Records every db.execute(...) call; can be told to raise on ALTER."""

    def __init__(self, order, raise_on_alter=False):
        self._order = order
        self._raise_on_alter = raise_on_alter
        self.outer_rollback_called = False

    def begin_nested(self):
        self._order.append("begin_nested")
        return _FakeSavepoint(self._order)

    def execute(self, clause, *args, **kwargs):
        sql = str(clause)
        if "SET LOCAL lock_timeout" in sql:
            self._order.append(("set_lock_timeout", sql))
        elif "ALTER TABLE" in sql:
            self._order.append(("alter", sql))
            if self._raise_on_alter:
                raise Exception("simulated: canceling statement due to lock timeout")
        else:
            self._order.append(("other", sql))

    def rollback(self):
        # The OUTER (whole-migration) transaction rollback. Must never be
        # called by _alter_table_add_column_bounded itself — only the
        # SAVEPOINT should roll back on a lock timeout.
        self.outer_rollback_called = True


def test_happy_path_sets_lock_timeout_then_alters_then_commits_savepoint():
    order = []
    db = _FakeSession(order)

    _alter_table_add_column_bounded(db, "users", "onboarding_completed_at", "TIMESTAMP")

    kinds = [item[0] if isinstance(item, tuple) else item for item in order]
    assert kinds == ["begin_nested", "set_lock_timeout", "alter", "savepoint.commit"], (
        "SET LOCAL lock_timeout must be issued before the ALTER, and the "
        "SAVEPOINT must be committed on success, in this exact order."
    )
    assert db.outer_rollback_called is False


def test_lock_timeout_error_is_swallowed_and_only_rolls_back_the_savepoint():
    order = []
    db = _FakeSession(order, raise_on_alter=True)

    # Must not raise — a bounded lock wait failing is an expected, retryable
    # outcome, not a fatal error that should crash startup or the request.
    _alter_table_add_column_bounded(db, "users", "onboarding_completed_at", "TIMESTAMP")

    kinds = [item[0] if isinstance(item, tuple) else item for item in order]
    assert kinds == ["begin_nested", "set_lock_timeout", "alter", "savepoint.rollback"], (
        "A lock-timeout (or any) failure on the ALTER must roll back only "
        "the SAVEPOINT, not raise, and not touch the outer transaction — "
        "otherwise every earlier successfully-applied ALTER TABLE in the "
        "same long-lived migration transaction would be silently undone."
    )
    assert db.outer_rollback_called is False, (
        "the outer session.rollback() must never be called by this helper — "
        "that would wipe out every prior column migration already applied "
        "in the same startup migration transaction"
    )


def test_custom_lock_timeout_value_is_honored():
    order = []
    db = _FakeSession(order)

    _alter_table_add_column_bounded(db, "appointments", "archived_at", "TIMESTAMP", lock_timeout="1500ms")

    set_stmts = [sql for item in order if isinstance(item, tuple) and item[0] == "set_lock_timeout" for sql in [item[1]]]
    assert any("1500ms" in sql for sql in set_stmts)
