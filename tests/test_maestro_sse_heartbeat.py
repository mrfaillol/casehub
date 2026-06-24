import asyncio
import json
import re
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


class _FakeDB:
    def __init__(self):
        self.executed = False
        self.commits = 0
        self.rollbacks = 0

    def execute(self, *args, **kwargs):
        self.executed = True

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _FakeMaestro:
    model = "fake-model"
    provider = "fake-provider"

    async def chat_stream(self, *args, **kwargs):
        await asyncio.sleep(0.03)
        yield {"chunk": "ola"}
        yield {"response": "ola", "model": self.model, "status": "ok", "done": True}


class _FakeRequest:
    state = SimpleNamespace(org_id=4)

    async def json(self):
        return {"message": "Resumo do dia", "history": []}


@pytest.mark.asyncio
async def test_maestro_stream_sends_immediate_thinking_and_prefill_ping(monkeypatch):
    import routes.assistente as assistente

    fake_legal_module = types.ModuleType("services.maestro_legal_rag")
    fake_legal_module.retrieve_legal_context = lambda db, message: SimpleNamespace(
        context="",
        looks_legal=False,
        citations=[],
    )
    monkeypatch.setitem(sys.modules, "services.maestro_legal_rag", fake_legal_module)

    monkeypatch.setattr(assistente, "MAESTRO_STREAM_HEARTBEAT_SECONDS", 0.01)
    monkeypatch.setattr(assistente, "get_current_user", lambda request, db: SimpleNamespace(id=7))
    monkeypatch.setattr(assistente, "_is_maestro_enabled", lambda db, org_id: True)
    monkeypatch.setattr(assistente, "_get_maestro", lambda request, db, org_id: _FakeMaestro())
    monkeypatch.setattr(assistente, "_effective_personality", lambda db, org_id, user_id: {})
    monkeypatch.setattr(assistente, "_personality_style_block", lambda personality: "")
    monkeypatch.setattr(
        assistente,
        "build_maestro_context",
        lambda *args, **kwargs: SimpleNamespace(prompt_context="", repo_context=""),
    )
    monkeypatch.setattr(assistente, "_record_maestro_inference", lambda *args, **kwargs: None)

    db = _FakeDB()
    response = await assistente.chat_api_stream(_FakeRequest(), db)

    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)

    first_event = json.loads(chunks[0].removeprefix("data: ").strip())
    assert first_event == {"status": "thinking", "done": False}
    assert ": ping\n\n" in chunks
    assert any('"chunk": "ola"' in chunk for chunk in chunks)
    assert any('"done": true' in chunk and '"response": "ola"' in chunk for chunk in chunks)
    assert db.executed is True
    assert db.commits == 1


@pytest.mark.parametrize(
    "template_path,false_hide",
    [
        ("templates/app/assistente/chat.html", "thinkingIndicator.classList.remove('active')"),
        ("templates/assistente/chat_embed.html", "thinkingIndicator.setAttribute('data-active', 'false')"),
    ],
)
def test_maestro_frontend_keeps_thinking_until_real_stream_content(template_path, false_hide):
    text = Path(template_path).read_text()
    stream_idx = text.index("/assistente/api/chat/stream")
    fetch_idx = text.rfind("fetch", 0, stream_idx)
    reader_idx = text.index("getReader()", stream_idx)
    after_headers_block = text[fetch_idx:reader_idx]

    assert false_hide not in after_headers_block
    assert "firstContentSeen" in text
    assert "hideThinkingOnce" in text
    assert "if (!trimmed.startsWith('data: ')) continue;" in text
    assert re.search(r"if \(evt\.chunk\) \{\s+hideThinkingOnce\(\);", text)
    assert re.search(r"\} else if \(evt\.done\) \{\s+hideThinkingOnce\(\);", text)
