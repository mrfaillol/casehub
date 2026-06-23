"""Controladoria hero KPI fix (FB1, alpha UsuarioDemo 2026-06-16).

The hero card "Total ativos" historically showed COUNT(*) of all prazos
(cadastrados), so UsuarioDemo saw 75 when only 32 were still open. The card must
instead surface the PENDENTES (não concluídos) count, mirroring the carteira's
existing `pendentes = max(total - concluidos, 0)` derivation.

These tests pin:
  1. _get_stats returns a `pendentes` key == total - concluidos (org-scoped).
  2. `total` stays intact (eficiencia_geral uses it as denominator).
  3. The dashboard template renders s.pendentes (not s.total) in the hero card.
"""

from sqlalchemy import text

from routes import controladoria


# ── DB-backed: pendentes math is correct and org-scoped ─────────────────────

def _create_prazos_table(db):
    # prazos_processuais is raw-SQL (not an ORM model), so Base.metadata
    # drop_all in conftest does NOT reset it between tests and the StaticPool
    # keeps a single in-memory connection alive. Drop-then-create gives each
    # test a clean, isolated table.
    db.execute(text("DROP TABLE IF EXISTS prazos_processuais"))
    db.execute(text("""
        CREATE TABLE prazos_processuais (
            id INTEGER PRIMARY KEY,
            org_id INTEGER,
            case_id INTEGER,
            tipo VARCHAR(100),
            data_vencimento DATE,
            status VARCHAR(50),
            descricao TEXT,
            processo_override VARCHAR(80)
        )
    """))
    db.commit()


def _seed(db, org_id, *statuses):
    rows = ",".join(
        f"({org_id}, 'Tipo', '{st}', 'PROC-{i}')"
        for i, st in enumerate(statuses)
    )
    db.execute(text(
        "INSERT INTO prazos_processuais (org_id, tipo, status, processo_override) "
        f"VALUES {rows}"
    ))
    db.commit()


def test_get_stats_returns_pendentes_equal_total_minus_concluidos(db, monkeypatch):
    """pendentes must equal total - concluidos for seeded prazos."""
    # Isolate the COUNT math: skip the cases/clients-joined _get_prazos pass.
    monkeypatch.setattr(controladoria, "_get_prazos", lambda db, org_id: [])
    _create_prazos_table(db)
    # org 7: 5 prazos — 2 concluidos, 3 abertos (pendente/em_andamento/perdido).
    _seed(db, 7, "concluido", "concluido", "pendente", "em_andamento", "perdido")

    stats = controladoria._get_stats(db, 7)

    assert stats["total"] == 5
    assert stats["concluidos"] == 2
    assert "pendentes" in stats
    assert stats["pendentes"] == stats["total"] - stats["concluidos"] == 3


def test_get_stats_pendentes_is_org_scoped(db, monkeypatch):
    """Another org's prazos must not leak into the pendentes count."""
    monkeypatch.setattr(controladoria, "_get_prazos", lambda db, org_id: [])
    _create_prazos_table(db)
    _seed(db, 7, "pendente", "concluido")          # org 7: total 2, concl 1 -> pend 1
    _seed(db, 99, "pendente", "pendente", "pendente")  # noise from a different org

    stats = controladoria._get_stats(db, 7)

    assert stats["total"] == 2
    assert stats["concluidos"] == 1
    assert stats["pendentes"] == 1


def test_get_stats_pendentes_never_negative(db, monkeypatch):
    """Defensive: pendentes floors at 0 even if concluidos ever exceeds total."""
    monkeypatch.setattr(controladoria, "_get_prazos", lambda db, org_id: [])
    _create_prazos_table(db)  # clean table → no rows
    # No rows at all → total 0, concluidos 0, pendentes 0 (not negative).
    stats = controladoria._get_stats(db, 7)
    assert stats["pendentes"] == 0
    assert stats["pendentes"] >= 0


# ── Template: hero card renders pendentes, not total ────────────────────────

def _read_dashboard():
    with open("templates/app/controladoria/dashboard.html", "r", encoding="utf-8") as fh:
        return fh.read()


def test_hero_kpi_renders_pendentes_not_total():
    html = _read_dashboard()
    hero = html.split("ch-kpi--hero", 1)[1].split("</article>", 1)[0]
    assert "s.pendentes" in hero
    # the hero value must no longer be the raw cadastrados total
    assert "ch-kpi__value\">{{ s.total" not in hero


def test_hero_kpi_label_says_pendentes():
    html = _read_dashboard()
    hero = html.split("ch-kpi--hero", 1)[1].split("</article>", 1)[0]
    assert "Prazos pendentes" in hero
    assert "Total ativos" not in hero
