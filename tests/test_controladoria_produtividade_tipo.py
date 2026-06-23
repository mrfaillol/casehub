"""Regression tests for Controladoria productivity by petition type."""

import inspect
from types import SimpleNamespace

import routes.controladoria as ctrl


def test_produtividade_tipo_taxonomy_matches_usuario_demo_spreadsheet_order():
    assert ctrl.TIPOS_PRODUTIVIDADE == (
        "Pet. Simples",
        "Impugnação/decote RPV",
        "Manif. Laudo",
        "Informa perícia/audiência",
        "Pet. Complexa",
        "Defesas",
        "Réplicas",
        "Recursos",
        "C.razões",
        "Outros",
    )


def test_produtividade_tipo_normalizes_legacy_and_no_accent_labels():
    assert ctrl.normalizar_tipo_produtividade("Peticao simples") == "Pet. Simples"
    assert ctrl.normalizar_tipo_produtividade("Impugnacao ou decote RPV") == "Impugnação/decote RPV"
    assert ctrl.normalizar_tipo_produtividade("Manif. Laudo/Quesitos") == "Manif. Laudo"
    assert ctrl.normalizar_tipo_produtividade("Informa pericia ou audiencia") == "Informa perícia/audiência"
    assert ctrl.normalizar_tipo_produtividade("Contrarrazoes de Apelacao") == "C.razões"
    assert ctrl.normalizar_tipo_produtividade("Algo especifico do escritorio") == "Outros"


def test_produtividade_tipo_maps_cpc_fallback_types():
    assert ctrl.normalizar_tipo_produtividade(None, "contestacao") == "Defesas"
    assert ctrl.normalizar_tipo_produtividade("", "replica") == "Réplicas"
    assert ctrl.normalizar_tipo_produtividade("Sem tipo", "replica") == "Réplicas"
    assert ctrl.normalizar_tipo_produtividade(None, "recurso_apelacao") == "Recursos"
    assert ctrl.normalizar_tipo_produtividade(None, "contrarrazoes") == "C.razões"


def test_produtividade_tipo_aggregation_merges_aliases_in_taxonomy_order():
    rows = [
        SimpleNamespace(tipo_peticao="Pet. Simples", tipo="", qtd=2),
        SimpleNamespace(tipo_peticao="Peticao simples", tipo="", qtd=3),
        SimpleNamespace(tipo_peticao="", tipo="replica", qtd=4),
        SimpleNamespace(tipo_peticao="Contrarrazoes de Apelacao", tipo="", qtd=1),
        SimpleNamespace(tipo_peticao="", tipo="tipo livre sem mapa", qtd=5),
    ]

    dist, order, total = ctrl._aggregate_tipos_produtividade(rows)

    assert total == 15
    assert dist == {
        "Pet. Simples": 5,
        "Réplicas": 4,
        "C.razões": 1,
        "Outros": 5,
    }
    assert order == ["Pet. Simples", "Réplicas", "C.razões", "Outros"]


def test_concluir_and_update_contracts_preserve_tipo_peticao_pipeline():
    concluir_source = inspect.getsource(ctrl.concluir_prazo)
    update_source = inspect.getsource(ctrl.update_prazo)
    bulk_source = inspect.getsource(ctrl.bulk_concluir)

    assert "normalizar_tipo_produtividade" in concluir_source
    assert "tipo_peticao = :tipo_peticao" in concluir_source
    assert "data_conclusao = :data_conclusao" in concluir_source
    assert "Data de conclusao invalida" in concluir_source
    assert "Use /controladoria/{id}/concluir" in update_source
    assert "Tipo de peticao obrigatorio" in bulk_source
    assert '"Pet. Simples"' not in bulk_source


def test_active_dashboard_template_uses_native_concluir_modal():
    with open("templates/app/controladoria/dashboard.html", encoding="utf-8") as fh:
        template = fh.read()

    assert 'id="ch-concluir-modal"' in template
    assert "CH_TIPOS_PRODUTIVIDADE" in template
    assert "data-tipo-peticao" in template
    assert "Tipo de petições (mês)" in template
    assert "pct.toFixed(0)" in template
    assert " · " in template
    assert "postPrazo(id, '/concluir'" in template
    assert "field: 'status', value: 'concluido'" not in template
