"""Controladoria sort/drag reconciliation (handoff 05 + Equipe CaseHub 2026-06-15).

Default order = data_vencimento ASC (closest deadline first), nulls last,
tie-broken by hora_vencimento then id — survives F5. Drag stays native/active
(sort="manual" → p.ordem governs) and can be disabled per-org. Concluidos keep
DESC by data_vencimento (alias fix). Header sort state is dynamic, not hardcoded.
"""

import inspect
from types import SimpleNamespace

from routes import controladoria


class _Result:
    def fetchall(self):
        return []


class _CaptureDB:
    """Records the SQL produced by _get_prazos without a real database.

    get_bind() returns a fake dialect so the PG (NULLS LAST) vs SQLite
    (emulated) branch can be exercised deterministically.
    """

    def __init__(self, dialect="sqlite"):
        self.query = ""
        self.params = {}
        self._dialect = dialect

    def execute(self, query, params=None):
        self.query = str(query)
        self.params = params or {}
        return _Result()

    def get_bind(self):
        if self._dialect is None:
            return None
        return SimpleNamespace(dialect=SimpleNamespace(name=self._dialect))


def _capture(monkeypatch, dialect="sqlite", **kwargs):
    monkeypatch.setattr(controladoria, "_ensure_controladoria_schema", lambda db: None)
    monkeypatch.setattr(
        controladoria,
        "_get_user_directory",
        lambda db, org_id: {"users": [], "by_id": {}, "by_name": {}},
    )
    db = _CaptureDB(dialect)
    controladoria._get_prazos(db, 1, **kwargs)
    return db.query


def _read_dashboard():
    with open("templates/app/controladoria/dashboard.html", "r", encoding="utf-8") as fh:
        return fh.read()


def _order_by(query):
    """Isolate the ORDER BY clause (COALESCE/data_vencimento also appear in SELECT)."""
    return query.split("ORDER BY", 1)[1] if "ORDER BY" in query else ""


# ── Server: default ordering ────────────────────────────────────────────────

def test_default_sort_is_vencimento_not_manual_ordem(monkeypatch):
    """Opening the page (no sort param) orders by deadline, not drag order."""
    order_by = _order_by(_capture(monkeypatch, sort=""))
    assert "p.data_vencimento ASC" in order_by
    assert "COALESCE(p.ordem" not in order_by


def test_default_sort_breaks_ties_by_hora_vencimento(monkeypatch):
    """Same date → earlier hora_vencimento first (deterministic tiebreak)."""
    q = _capture(monkeypatch, sort="")
    order_by = q.split("ORDER BY", 1)[1]
    assert "p.hora_vencimento ASC" in order_by
    assert "p.id ASC" in order_by


def test_default_sort_puts_null_deadlines_last(monkeypatch):
    q = _capture(monkeypatch, sort="")
    assert "CASE WHEN p.data_vencimento IS NULL THEN 1 ELSE 0 END ASC" in q


def test_default_sort_postgres_uses_nulls_last(monkeypatch):
    q = _capture(monkeypatch, dialect="postgresql", sort="")
    assert "p.data_vencimento ASC NULLS LAST" in q
    # empty hora ('') treated as NULL so "sem hora" sorts last (parity w/ SQLite)
    assert "NULLIF(p.hora_vencimento, '') ASC NULLS LAST" in q


# ── Server: explicit vencimento sort is idempotent with default ─────────────

def test_explicit_vencimento_sort_includes_hora_tiebreak(monkeypatch):
    """sort=vencimento (the new handler default) matches the empty-default SQL."""
    order_by = _order_by(_capture(monkeypatch, sort="vencimento"))
    assert "p.data_vencimento" in order_by
    assert "p.hora_vencimento" in order_by
    assert "COALESCE(p.ordem" not in order_by


# ── Server: manual mode keeps drag order ────────────────────────────────────

def test_manual_sort_uses_ordem(monkeypatch):
    """Dragging switches to sort=manual where p.ordem governs (drag persists)."""
    q = _capture(monkeypatch, sort="manual")
    assert "ORDER BY COALESCE(p.ordem" in q


def test_manual_sort_keeps_vencimento_tiebreak(monkeypatch):
    """Same ordem + same date still tiebreaks by hora then id (contract parity)."""
    order_by = _order_by(_capture(monkeypatch, sort="manual"))
    assert order_by.index("COALESCE(p.ordem") < order_by.index("p.data_vencimento")
    assert "p.hora_vencimento" in order_by


# ── Server: concluidos DESC alias (latent bug fix) ──────────────────────────

def test_data_vencimento_alias_supports_desc(monkeypatch):
    """Concluidos pass sort=data_vencimento&direction=desc and must honor DESC."""
    order_by = _order_by(
        _capture(monkeypatch, dialect="postgresql", sort="data_vencimento", direction="desc")
    )
    assert "p.data_vencimento DESC" in order_by
    assert "COALESCE(p.ordem" not in order_by


def test_vencimento_sort_supports_desc(monkeypatch):
    """Clicking the Data final header again toggles to DESC (latest deadline first)."""
    order_by = _order_by(
        _capture(monkeypatch, dialect="postgresql", sort="vencimento", direction="desc")
    )
    assert "p.data_vencimento DESC" in order_by
    assert "COALESCE(p.ordem" not in order_by


# ── Handler default ─────────────────────────────────────────────────────────

def test_handler_default_sort_is_vencimento():
    sig = inspect.signature(controladoria.controladoria_dashboard)
    assert sig.parameters["sort"].default == "vencimento"


# ── Drag enable/disable toggle (org settings) ───────────────────────────────

def test_drag_enabled_read_from_org_settings():
    assert controladoria.DRAG_KEY == "controladoria_drag_enabled"
    helper_src = inspect.getsource(controladoria._get_drag_enabled)
    assert "DRAG_KEY" in helper_src and "_org_settings" in helper_src
    handler_src = inspect.getsource(controladoria.controladoria_dashboard)
    assert "drag_enabled" in handler_src


def test_drag_toggle_endpoint_exists():
    names = dir(controladoria)
    assert any("drag" in n and "toggle" in n.lower() for n in names), (
        "expected a drag-toggle handler in routes.controladoria"
    )


# ── Template: dynamic header state + URL-persistent sort ────────────────────

def test_vencimento_header_state_is_dynamic_not_hardcoded():
    html = _read_dashboard()
    # vencimento column rendered via the dynamic sort-header macro (not a static th)
    assert "ch_sort_th('vencimento'" in html
    # macro drives data-sort-key/aria-sort/arrow from the server sort_key
    assert 'data-sort-key="{{ key }}"' in html
    # the old hardcoded 'is-sorted' on the vencimento header must be gone
    assert 'ch-th-sort is-sorted" data-sort-key="vencimento"' not in html
    assert "sort_key ==" in html


def test_header_click_persists_sort_in_url():
    html = _read_dashboard()
    assert "searchParams.set('sort'" in html or 'searchParams.set("sort"' in html


# ── Template: drag toggle gating + mobile-capable drag ──────────────────────

def test_drag_listeners_gated_by_enabled_flag():
    html = _read_dashboard()
    # grip button rendered only when drag is enabled (org setting)
    assert "{% if drag_enabled %}" in html
    # SortableJS init is guarded by the server flag, not always-on
    assert "if (!dragEnabled) return;" in html


def test_drag_uses_touch_capable_mechanism():
    html = _read_dashboard()
    # SortableJS works on touch (mobile) and desktop; the old HTML5 drag events
    # never fire on touch devices.
    assert "Sortable" in html
    assert "touch-action" in html
