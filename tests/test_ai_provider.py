"""PR9 — provider-agnostic AI layer. Default is NullProvider (AI off, non-Gemini)."""
import os
os.environ.setdefault("SECRET_KEY", "test-secret-1234567890")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("CASEHUB_PRODUCT", "lite")

from services.ai_provider import get_ai_provider, NullProvider, GeminiProvider


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


async def test_null_provider_returns_none():
    assert await NullProvider().generate("oi") is None
