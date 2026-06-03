"""Regression tests for routes/assistente._get_user_learning_context.

The Maestro chat at ``/casehub/assistente/api/chat`` builds a context
string from firm + custom + sources + (new) user learning entries.
This module pins the four contracts that matter when the user
learning corpus joins the chat flow:

1. **Flag gate**: when ``CASEHUB_MAESTRO_LEARNING_ENABLED`` is OFF,
   the helper returns the empty string and never touches the DB —
   keeps the alpha posture (Maestro pipeline off until Council ruling).
2. **Anonymous user gate**: a None / id-less user yields the empty
   string — the corpus is per-user; an unauthenticated chat must not
   leak someone else's notes.
3. **Filter contract**: when enabled, the helper returns ONLY entries
   that belong to (user_id, org_id) AND are ``enabled=True``.
4. **Cap contract**: at most ``_MAX_ENTRIES_FOR_CHAT_CTX`` entries
   reach the prompt, and each is truncated to
   ``_MAX_ENTRY_BYTES_FOR_CHAT_CTX`` — protects the chat token budget.

Run: pytest tests/test_maestro_chat_context_wiring.py
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

# Soft dependency on PR #575 (which adds the MaestroLearningEntry model
# to models/__init__.py). If the model is not yet importable in this
# checkout, skip the whole module — the runtime code in routes/assistente
# already degrades silently in the same scenario.
MaestroLearningEntry = pytest.importorskip(
    "models",
    reason="Requires PR #575 (MaestroLearningEntry model). Skipped on main.",
).__dict__.get("MaestroLearningEntry")
if MaestroLearningEntry is None:
    pytest.skip(
        "MaestroLearningEntry not yet present in models/ — depends on PR #575.",
        allow_module_level=True,
    )

import routes.assistente as assistente


_ORG_ID = 41


@pytest.fixture
def fake_user():
    return SimpleNamespace(id=701, email="a@example.com")


def _enable_flag(monkeypatch, enabled=True):
    monkeypatch.setenv(
        "CASEHUB_MAESTRO_LEARNING_ENABLED",
        "1" if enabled else "",
    )


def _seed(db, user_id, org_id, title, content, enabled=True, tags=None):
    e = MaestroLearningEntry(
        org_id=org_id,
        user_id=user_id,
        title=title,
        content=content,
        source="manual",
        tags=tags or [],
        enabled=enabled,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


# ---------------------------------------------------------------------------
# Flag gate
# ---------------------------------------------------------------------------


def test_returns_empty_when_flag_disabled(db, monkeypatch, fake_user):
    _enable_flag(monkeypatch, enabled=False)
    # Seed an entry to prove the helper does NOT pick it up.
    _seed(db, fake_user.id, _ORG_ID, "title", "hello")

    assert assistente._get_user_learning_context(db, _ORG_ID, fake_user) == ""


# ---------------------------------------------------------------------------
# Anonymous user gate
# ---------------------------------------------------------------------------


def test_returns_empty_for_anonymous_user(db, monkeypatch):
    _enable_flag(monkeypatch, enabled=True)
    # No user object at all
    assert assistente._get_user_learning_context(db, _ORG_ID, None) == ""

    # User-shaped object without an id (e.g. partial deserialisation)
    no_id_user = SimpleNamespace(email="x@example.com")
    assert assistente._get_user_learning_context(db, _ORG_ID, no_id_user) == ""


# ---------------------------------------------------------------------------
# Filter contract — user + org + enabled
# ---------------------------------------------------------------------------


def test_returns_only_entries_for_this_user_org_and_enabled(db, monkeypatch, fake_user):
    _enable_flag(monkeypatch, enabled=True)

    # Entry 1: matches — should appear
    _seed(db, fake_user.id, _ORG_ID, "Glossário", "EB-2 NIW = National Interest Waiver")
    # Entry 2: different user — should NOT appear
    _seed(db, 999, _ORG_ID, "OTHER USER", "should not appear")
    # Entry 3: different org — should NOT appear
    _seed(db, fake_user.id, 9999, "OTHER ORG", "should not appear")
    # Entry 4: disabled — should NOT appear
    _seed(db, fake_user.id, _ORG_ID, "Draft", "in-progress, disabled", enabled=False)

    ctx = assistente._get_user_learning_context(db, _ORG_ID, fake_user)

    assert "Glossário" in ctx
    assert "EB-2 NIW" in ctx
    # Verbatim title from other-user / other-org / disabled — must not leak
    assert "OTHER USER" not in ctx
    assert "OTHER ORG" not in ctx
    assert "Draft" not in ctx


def test_section_header_signals_user_authoring(db, monkeypatch, fake_user):
    """The block must be labelled so the model treats it as user-authored
    (preference) rather than firm-canonical knowledge — matters when an
    entry contradicts the firm context."""
    _enable_flag(monkeypatch, enabled=True)
    _seed(db, fake_user.id, _ORG_ID, "Title", "Body")

    ctx = assistente._get_user_learning_context(db, _ORG_ID, fake_user)
    assert "Anotações do usuário" in ctx
    # Signals authoring + how to resolve conflicts
    assert "valide contra o contexto do escritório" in ctx


# ---------------------------------------------------------------------------
# Cap contract — entry count + per-entry truncation
# ---------------------------------------------------------------------------


def test_caps_total_entries_pulled_into_context(db, monkeypatch, fake_user):
    _enable_flag(monkeypatch, enabled=True)

    n = assistente._MAX_ENTRIES_FOR_CHAT_CTX + 5  # 5 over the cap
    for i in range(n):
        _seed(db, fake_user.id, _ORG_ID, f"Entry-{i:02d}", f"body-{i:02d}")

    ctx = assistente._get_user_learning_context(db, _ORG_ID, fake_user)
    # Count distinct entry headers in the assembled block
    header_count = ctx.count("### Entry-")
    assert header_count == assistente._MAX_ENTRIES_FOR_CHAT_CTX, (
        f"Expected at most _MAX_ENTRIES_FOR_CHAT_CTX="
        f"{assistente._MAX_ENTRIES_FOR_CHAT_CTX} entries, "
        f"found {header_count}."
    )


def test_truncates_each_entry_to_byte_cap(db, monkeypatch, fake_user):
    _enable_flag(monkeypatch, enabled=True)

    huge = "x" * (assistente._MAX_ENTRY_BYTES_FOR_CHAT_CTX * 3)
    _seed(db, fake_user.id, _ORG_ID, "Huge", huge)

    ctx = assistente._get_user_learning_context(db, _ORG_ID, fake_user)
    # A substring of (cap + 1) x's must not appear in the assembled
    # context — proves truncation kicked in. The entry body alone was
    # 3× the cap; only ``cap`` x's may have made it through.
    assert ("x" * (assistente._MAX_ENTRY_BYTES_FOR_CHAT_CTX + 1)) not in ctx
    # Sanity: at least ``cap`` x's DID make it (otherwise the truncation
    # would be too aggressive and the test would pass for the wrong reason).
    assert ("x" * assistente._MAX_ENTRY_BYTES_FOR_CHAT_CTX) in ctx


# ---------------------------------------------------------------------------
# Defensive — DB failure degrades silently (chat keeps working)
# ---------------------------------------------------------------------------


def test_db_failure_returns_empty_string(db, monkeypatch, fake_user):
    """A broken DB query must NOT break the chat — the helper logs and
    returns the empty string so the rest of the system context still
    serves the response."""
    _enable_flag(monkeypatch, enabled=True)

    real_query = db.query

    def fake_query(*args, **kwargs):
        raise RuntimeError("simulated db failure")

    monkeypatch.setattr(db, "query", fake_query)

    ctx = assistente._get_user_learning_context(db, _ORG_ID, fake_user)
    assert ctx == ""

    # Restore so other tests in this module are unaffected.
    monkeypatch.setattr(db, "query", real_query)
