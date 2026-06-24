import os

import pytest

os.environ.setdefault("_".join(["SECRET", "KEY"]), "unit-test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("CASEHUB_PRODUCT", "lite")


class _StreamingProvider:
    name = "nvidia"

    async def generate_stream(self, *args, **kwargs):
        yield "Resumo "
        yield "pronto"


class _FailingProvider:
    name = "nvidia"

    async def generate_stream(self, *args, **kwargs):
        raise TimeoutError("synthetic provider timeout")
        yield ""  # pragma: no cover


@pytest.mark.asyncio
async def test_chat_stream_uses_external_provider_chunks(monkeypatch):
    from services import ai_provider, maestro_budget
    from services.maestro_lite import MaestroLite

    monkeypatch.setattr(ai_provider, "get_ai_provider", lambda: _StreamingProvider())
    monkeypatch.setattr(maestro_budget, "note_success", lambda: None)
    monkeypatch.setattr(maestro_budget, "note_failure", lambda kind="": None)

    events = [
        event
        async for event in MaestroLite().chat_stream(
            "Resumo do dia",
            context="Contexto sintético",
            history=[],
        )
    ]

    assert events[:2] == [
        {"chunk": "Resumo ", "model": "nvidia"},
        {"chunk": "pronto", "model": "nvidia"},
    ]
    assert events[-1] == {
        "response": "Resumo pronto",
        "model": "nvidia",
        "status": "ok",
        "done": True,
    }


@pytest.mark.asyncio
async def test_chat_stream_does_not_fallback_to_ollama_after_provider_failure(monkeypatch):
    from services import ai_provider, maestro_budget, maestro_lite
    from services.maestro_lite import MaestroLite

    fallback_attempted = False

    class _OllamaClientProbe:
        def __init__(self, *args, **kwargs):
            nonlocal fallback_attempted
            fallback_attempted = True

    monkeypatch.setattr(ai_provider, "get_ai_provider", lambda: _FailingProvider())
    monkeypatch.setattr(maestro_budget, "note_success", lambda: None)
    monkeypatch.setattr(maestro_budget, "note_failure", lambda kind="": None)
    monkeypatch.setattr(maestro_lite.httpx, "AsyncClient", _OllamaClientProbe)

    events = [
        event
        async for event in MaestroLite().chat_stream(
            "Resumo do dia",
            context="Contexto sintético",
            history=[],
        )
    ]

    assert fallback_attempted is False
    assert events == [{
        "response": "O provedor de IA falhou. Tente novamente em instantes.",
        "status": "error",
        "done": True,
    }]
