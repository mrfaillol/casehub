"""Regression tests for services.messaging_hub_service — return-shape stability.

`get_unread_counts()` builds a fixed-key dict {whatsapp,email,sms,call,total}
then assigns `counts[row.channel] = ...` for every GROUP BY row. `row.channel`
is uncontrolled DB data: a value outside the whitelist (NULL, or a future
channel) was silently added as an extra dict key, so the function's return
shape was not stable. (It is a plain dict, so this never raised — assignment
to an unknown key just creates it — but callers and the template should not
receive a `None` key or unexpected channels.)

This is a correctness/contract fix, not a 500 fix.

`unified_messages` is a raw-migration table (not an ORM model), so the test
creates a minimal version of it directly.

Run: pytest tests/test_messaging_hub_service.py
"""
import pytest
from sqlalchemy import text

from services.messaging_hub_service import MessagingHubService


@pytest.fixture
def unified_messages_table(db):
    """Minimal unified_messages table — just the columns get_unread_counts reads.

    unified_messages is not an ORM model, so conftest's drop_all does not clear
    it; the in-memory StaticPool keeps it alive across tests. Drop explicitly on
    both ends to keep each test isolated."""
    db.execute(text("DROP TABLE IF EXISTS unified_messages"))
    db.execute(text(
        "CREATE TABLE unified_messages ("
        "  id INTEGER PRIMARY KEY,"
        "  channel TEXT,"
        "  is_read BOOLEAN,"
        "  direction TEXT"
        ")"
    ))
    db.commit()
    yield db
    db.rollback()
    db.execute(text("DROP TABLE IF EXISTS unified_messages"))
    db.commit()


def test_get_unread_counts_keeps_stable_shape_for_unknown_channels(unified_messages_table):
    """A channel outside {whatsapp,email,sms,call} — or NULL — must not leak
    into the returned dict as an extra key. Known channels are counted
    per-channel; every unread inbound row still contributes to total."""
    db = unified_messages_table
    db.execute(text(
        "INSERT INTO unified_messages (channel, is_read, direction) VALUES "
        "('whatsapp', 0, 'inbound'),"
        "('whatsapp', 0, 'inbound'),"
        "('email',    0, 'inbound'),"
        "('telegram', 0, 'inbound'),"   # future / unknown channel
        "(NULL,       0, 'inbound')"    # NULL channel
    ))
    db.commit()

    counts = MessagingHubService(db, org_id=1).get_unread_counts()

    assert counts['whatsapp'] == 2
    assert counts['email'] == 1
    assert counts['sms'] == 0
    assert counts['call'] == 0
    assert counts['total'] == 5                       # every unread inbound row
    # the unknown / NULL channels did not leak in as extra keys
    assert set(counts) == {'whatsapp', 'email', 'sms', 'call', 'total'}


def test_get_unread_counts_excludes_read_and_outbound(unified_messages_table):
    """Only unread inbound rows are counted; read or outbound rows are ignored."""
    db = unified_messages_table
    db.execute(text(
        "INSERT INTO unified_messages (channel, is_read, direction) VALUES "
        "('whatsapp', 0, 'inbound'),"   # counted
        "('whatsapp', 1, 'inbound'),"   # read -> ignored
        "('email',    0, 'outbound')"   # outbound -> ignored
    ))
    db.commit()

    counts = MessagingHubService(db, org_id=1).get_unread_counts()

    assert counts['whatsapp'] == 1
    assert counts['email'] == 0
    assert counts['total'] == 1


def test_get_unread_counts_empty_table(unified_messages_table):
    """Empty unified_messages -> all-zero counts, no crash (empty state)."""
    counts = MessagingHubService(unified_messages_table, org_id=1).get_unread_counts()
    assert counts == {'whatsapp': 0, 'email': 0, 'sms': 0, 'call': 0, 'total': 0}
