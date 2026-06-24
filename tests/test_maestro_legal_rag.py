from __future__ import annotations

import asyncio

from models import MaestroLegalSource
from services.maestro_legal_rag import (
    retrieve_legal_context,
    upsert_official_document,
)


CPC_FIXTURE = """
Lei n. 13.105, de 16 de março de 2015.
Código de Processo Civil.

Art. 212. Os atos processuais serão realizados em dias úteis, das 6 (seis) às 20 (vinte) horas.

Art. 219. Na contagem de prazo em dias, estabelecido por lei ou pelo juiz,
computar-se-ão somente os dias úteis.
"""

CF_FIXTURE = """
Constituição da República Federativa do Brasil de 1988.

Art. 5. Todos são iguais perante a lei, sem distinção de qualquer natureza.
O texto constitucional menciona processo legal e prazos em contexto geral.
"""


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def test_retrieves_only_verified_official_legal_context(db):
    doc = upsert_official_document(
        db,
        source_key="planalto-cpc-test",
        authority="Planalto",
        title="Código de Processo Civil",
        url="https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105compilada.htm",
        text=CPC_FIXTURE,
        document_type="norma",
    )

    result = retrieve_legal_context(db, "o que diz o art. 212 do CPC?")

    assert result.looks_legal is True
    assert result.has_context is True
    assert "Conhecimento JURIDICO OFICIAL" in result.context
    assert "Planalto" in result.context
    assert "sha256:" in result.context
    assert "Art. 212" in result.context
    assert result.citations[0].document_id == doc.id
    assert result.citations[0].url.startswith("https://www.planalto.gov.br/")


def test_cpc_question_prioritizes_cpc_source_over_constitution(db):
    upsert_official_document(
        db,
        source_key="planalto-cf-test",
        authority="Planalto",
        title="Constituição da República Federativa do Brasil de 1988",
        url="https://www.planalto.gov.br/ccivil_03/Constituicao/constituicaocompilado.htm",
        text=CF_FIXTURE,
        document_type="norma",
    )
    cpc_doc = upsert_official_document(
        db,
        source_key="planalto-cpc-ranking-test",
        authority="Planalto",
        title="Código de Processo Civil",
        url="https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105compilada.htm",
        text=CPC_FIXTURE,
        document_type="norma",
    )

    result = retrieve_legal_context(db, "o que diz o art. 212 do CPC?")

    assert result.has_context is True
    assert result.citations[0].document_id == cpc_doc.id
    assert "Código de Processo Civil" in result.citations[0].title


def test_cpc_source_is_not_starved_by_many_earlier_generic_chunks(db):
    noisy_cf = "\n\n".join(
        f"Art. {idx}. Texto constitucional generico sobre processo, prazo e garantias. "
        + ("conteudo publico " * 120)
        for idx in range(1, 230)
    )
    upsert_official_document(
        db,
        source_key="planalto-cf-large-test",
        authority="Planalto",
        title="Constituição da República Federativa do Brasil de 1988",
        url="https://www.planalto.gov.br/ccivil_03/Constituicao/constituicaocompilado.htm",
        text=noisy_cf,
        document_type="norma",
    )
    cpc_doc = upsert_official_document(
        db,
        source_key="planalto-cpc-large-ranking-test",
        authority="Planalto",
        title="Código de Processo Civil",
        url="https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105compilada.htm",
        text=CPC_FIXTURE,
        document_type="norma",
    )

    result = retrieve_legal_context(db, "o que diz o art. 212 do CPC sobre prazos?")

    assert result.has_context is True
    assert result.citations[0].document_id == cpc_doc.id


def test_unverified_or_non_official_sources_are_not_retrieved(db):
    upsert_official_document(
        db,
        source_key="planalto-cpc-pending-test",
        authority="Planalto",
        title="Código de Processo Civil",
        url="https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105compilada.htm",
        text=CPC_FIXTURE,
    )
    source = db.query(MaestroLegalSource).filter_by(source_key="planalto-cpc-pending-test").one()
    source.trust_status = "pending"
    db.commit()

    result = retrieve_legal_context(db, "art. 212 CPC")

    assert result.looks_legal is True
    assert result.has_context is False
    assert result.citations == []


def test_secret_like_lines_are_redacted_before_chunking(db):
    upsert_official_document(
        db,
        source_key="official-doc-with-secret-like-line",
        authority="CNJ",
        title="Documento Oficial de Teste",
        url="https://www.cnj.jus.br/sistemas/datajud/api-publica/",
        text="Documento oficial.\nAPI_KEY=leakedvalue123456789\nArt. 1. Texto público oficial.",
    )

    result = retrieve_legal_context(db, "art. 1 documento oficial")

    assert result.has_context is True
    assert "leakedvalue123456789" not in result.context
    assert "REDACTED" in result.context


def test_law_question_without_official_source_refuses_without_network(monkeypatch):
    from services.maestro_lite import LEGAL_SOURCE_REQUIRED_REFUSAL, MaestroLite, httpx

    class NoNetworkClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("network should not be touched without official legal source")

    monkeypatch.setattr(httpx, "AsyncClient", NoNetworkClient)

    result = _run_async(MaestroLite().chat("o que diz o art. 212 do CPC?"))

    assert result["response"] == LEGAL_SOURCE_REQUIRED_REFUSAL
    assert result["refusal_code"] == "no_official_legal_source"


def test_legal_context_is_injected_when_available(monkeypatch):
    from services.maestro_lite import MaestroLite, httpx

    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"message": {"content": "Resposta com base na fonte oficial."}}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    legal_context = "Conhecimento JURIDICO OFICIAL verificado\n[Fonte juridica oficial 1: Planalto — CPC]"
    result = _run_async(MaestroLite().chat(
        "o que diz o art. 212 do CPC?",
        legal_context=legal_context,
    ))

    assert result["status"] == "ok"
    messages = captured["json"]["messages"]
    rendered = "\n".join(item["content"] for item in messages)
    assert "Conhecimento JURIDICO OFICIAL verificado" in rendered
    assert "Responda APENAS com base" in rendered
