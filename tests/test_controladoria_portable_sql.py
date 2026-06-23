"""Controladoria portable SQL fix (issue #874).

`routes/controladoria._get_produtividade_setores` and the urgencia query in
`api_produtividade` used Postgres-only `CURRENT_DATE` / `CURRENT_DATE + INTERVAL
'7 days'`, which raises `sqlalchemy.exc.OperationalError: near "'7 days'": syntax
error` on SQLite. The controladoria dashboard therefore 500'd under SQLite and
could not enter the test suite. The fix binds Python date params (`:today` /
`:today_plus_7` via date.today()/timedelta) so the SQL is dialect-portable
(works identically on SQLite and Postgres).

These tests pin that `_get_produtividade_setores` runs on SQLite without raising
and computes vencidos/proximos correctly against :today / :today_plus_7.
"""
from datetime import date, timedelta

from sqlalchemy import text

from routes import controladoria


def _create_prazos_table(db):
    # prazos_processuais is raw-SQL (not an ORM model); conftest's drop_all does
    # not reset it under StaticPool, so drop-then-create per test.
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
            responsavel VARCHAR(255),
            responsavel_user_id INTEGER,
            processo_override VARCHAR(80)
        )
    """))
    db.commit()


def _ins(db, org_id, status, dias_offset, responsavel="Ana"):
    venc = (date.today() + timedelta(days=dias_offset)).isoformat()
    db.execute(
        text("INSERT INTO prazos_processuais (org_id, tipo, status, data_vencimento, responsavel) "
             "VALUES (:o, 'T', :s, :v, :r)"),
        {"o": org_id, "s": status, "v": venc, "r": responsavel},
    )
    db.commit()


def test_produtividade_setores_runs_on_sqlite_with_portable_dates(db):
    """Regression: Postgres-only CURRENT_DATE/INTERVAL raised OperationalError on
    SQLite. With :today/:today_plus_7 binds the query runs and counts are right."""
    _create_prazos_table(db)
    _ins(db, 7, "pendente", -2)    # vencido (2 dias atrás)
    _ins(db, 7, "pendente", 3)     # próximo 7 dias
    _ins(db, 7, "pendente", 30)    # fora da janela
    _ins(db, 7, "concluido", -2)   # vencido MAS concluido -> não conta

    # Antes do fix isto levantava sqlalchemy.exc.OperationalError (near "'7 days'").
    rows = controladoria._get_produtividade_setores(db, 7)

    assert isinstance(rows, list)
    setor = next(r for r in rows if r["setor"] == "Ana")
    assert setor["total"] == 4
    assert setor["vencidos"] == 1   # só o pendente vencido (concluido não conta)
    assert setor["proximos"] == 1   # só o pendente dentro de 7 dias


def test_produtividade_setores_org_scoped(db):
    """Prazos de outra org não vazam na produtividade."""
    _create_prazos_table(db)
    _ins(db, 7, "pendente", 0, responsavel="Ana")
    _ins(db, 99, "pendente", 0, responsavel="Outro")

    rows = controladoria._get_produtividade_setores(db, 7)
    setores = {r["setor"] for r in rows}
    assert "Ana" in setores
    assert "Outro" not in setores
