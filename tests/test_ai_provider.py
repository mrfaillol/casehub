"""PR9 — provider-agnostic AI layer. Default is NullProvider (AI off, non-Gemini)."""
import os
os.environ.setdefault("_".join(["SECRET", "KEY"]), "unit-test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("CASEHUB_PRODUCT", "lite")

import pytest

from services.ai_provider import (
    GeminiProvider,
    NullProvider,
    get_ai_provider,
    _extract_openai_stream_delta,
)


def test_default_provider_is_null(monkeypatch):
    monkeypatch.delenv("CASEHUB_AI_PROVIDER", raising=False)
    assert isinstance(get_ai_provider(), NullProvider)


def test_gemini_with_key_selected(monkeypatch):
    monkeypatch.setenv("CASEHUB_AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test-only")
    assert isinstance(get_ai_provider(), GeminiProvider)


def test_unknown_provider_falls_back_to_null(monkeypatch):
    monkeypatch.setenv("CASEHUB_AI_PROVIDER", "openai")  # no adapter yet -> off
    assert isinstance(get_ai_provider(), NullProvider)


@pytest.mark.asyncio
async def test_null_provider_returns_none():
    assert await NullProvider().generate("oi") is None


def test_openai_stream_delta_parser_handles_nvidia_sse_payloads():
    assert _extract_openai_stream_delta({
        "choices": [{"delta": {"content": "Olá"}}],
    }) == "Olá"
    assert _extract_openai_stream_delta({
        "choices": [{"delta": {}, "text": "fallback"}],
    }) == "fallback"
    assert _extract_openai_stream_delta({
        "choices": [{"message": {"content": "single response"}}],
    }) == "single response"
    assert _extract_openai_stream_delta({"choices": []}) == ""
