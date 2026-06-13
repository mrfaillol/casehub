"""Regression tests for manual deadline party context in Controladoria."""

import inspect

import routes.controladoria as ctrl


def test_manual_deadline_accepts_client_and_opposing_party_context():
    source = inspect.getsource(ctrl.criar_prazo)
    ensure_source = inspect.getsource(ctrl._ensure_controladoria_schema)
    with open("templates/app/controladoria/dashboard.html", "r", encoding="utf-8") as fh:
        html = fh.read()
    with open("migrations/2026-06-12_controladoria_manual_parties.sql", "r", encoding="utf-8") as fh:
        sql = fh.read()

    assert 'name="cliente_manual"' in html
    assert 'name="parte_contraria_manual"' in html
    assert "togglePrazoPartesManuais" in html
    assert "parte_contraria_manual" in source
    assert "parte_contraria_override" in source
    assert "parte_contraria_override" in ensure_source
    assert "ADD COLUMN IF NOT EXISTS cliente_override" in sql
    assert "ADD COLUMN IF NOT EXISTS parte_contraria_override" in sql
