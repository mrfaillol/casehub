"""Provider-agnostic AI assist layer (PR9 — per ruling 2026-05-31 + Sentinela).

Default is NullProvider (AI OFF) — non-Gemini per Victor's decision. A real
provider activates ONLY when CASEHUB_AI_PROVIDER selects it AND its key is present,
so "no key → no provider → no call" is the built-in cost/secret circuit-breaker.
Adds NO new secret and commits NO key. Every call is live + EPHEMERAL (persists
nothing — Council training-data VETO). To plug a different provider later, add an
adapter + a branch in get_ai_provider(); the full Sentinela gate runs before a
second real key (e.g. OPENAI_API_KEY) is ever introduced.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_GEMINI_MODEL = os.getenv("CASEHUB_AI_MODEL", "gemini-1.5-flash")
_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{_GEMINI_MODEL}:generateContent"
)


class AIProvider:
    """Stable async contract for ephemeral AI text generation."""

    name = "base"

    async def generate(self, prompt: str, *, temperature: float = 0.7,
                       max_tokens: int = 300) -> Optional[str]:
        raise NotImplementedError


class NullProvider(AIProvider):
    """AI assist disabled — the safe, zero-secret default. Always returns None."""

    name = "null"

    async def generate(self, prompt: str, *, temperature: float = 0.7,
                       max_tokens: int = 300) -> Optional[str]:
        logger.info("[wa-crm-ai] AI provider disabled (NullProvider) — returning None")
        return None


class GeminiProvider(AIProvider):
    """Google Gemini adapter. Live, best-effort, 30s timeout, persists NOTHING."""

    name = "gemini"

    def __init__(self, api_key: str):
        self._api_key = api_key  # held only in memory; NEVER logged

    async def generate(self, prompt: str, *, temperature: float = 0.7,
                       max_tokens: int = 300) -> Optional[str]:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "topP": 0.8,
                "topK": 40,
            },
            "safetySettings": [
                {"category": c, "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
                for c in (
                    "HARM_CATEGORY_HARASSMENT",
                    "HARM_CATEGORY_HATE_SPEECH",
                    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "HARM_CATEGORY_DANGEROUS_CONTENT",
                )
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(_GEMINI_URL, params={"key": self._api_key}, json=payload)
            if resp.status_code != 200:
                logger.warning("[wa-crm-ai] Gemini HTTP %s", resp.status_code)  # status only, never the key
                return None
            data = resp.json()
            text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text")
            )
            if not text:
                return None
            text = text.strip()
            if (text.startswith('"') and text.endswith('"')) or (
                text.startswith("'") and text.endswith("'")
            ):
                text = text[1:-1]
            return text
        except httpx.TimeoutException:
            logger.warning("[wa-crm-ai] Gemini timeout")
            return None
        except Exception as e:  # noqa: BLE001 — AI assist is best-effort
            logger.warning("[wa-crm-ai] Gemini error: %s", e)
            return None




# Fallback list for OpenRouter free models — tried in order, skipped on 429/503.
_OPENROUTER_FREE_FALLBACKS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-4-31b-it:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "moonshotai/kimi-k2.6:free",
    "meta-llama/llama-3.2-3b-instruct:free",
]


class OpenRouterProvider(AIProvider):
    """OpenRouter adapter (OpenAI-compatible). Tries primary model then free fallbacks on 429."""

    name = "openrouter"
    _URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str, model: str = "meta-llama/llama-3.3-70b-instruct:free"):
        self._api_key = api_key
        self._model = model

    async def _try_model(self, client: "httpx.AsyncClient", model: str,
                         payload: dict) -> Optional[str]:
        """Attempt a single model call. Returns text or None; raises on 429/503 to signal skip."""
        payload = {**payload, "model": model}
        resp = await client.post(
            self._URL,
            headers={"Authorization": f"Bearer {self._api_key}",
                     "HTTP-Referer": "https://casehub.sampletenantadvogados.com.br",
                     "X-Title": "CaseHub"},
            json=payload,
        )
        if resp.status_code in (429, 503):
            logger.info("[wa-crm-ai] OpenRouter model %s rate-limited (%s), trying next", model, resp.status_code)
            raise httpx.HTTPStatusError("rate-limited", request=resp.request, response=resp)
        if resp.status_code != 200:
            logger.warning("[wa-crm-ai] OpenRouter HTTP %s (model=%s)", resp.status_code, model)
            return None
        data = resp.json()
        text = (data.get("choices", [{}])[0].get("message", {}).get("content"))
        return text.strip() if text else None

    async def generate(self, prompt: str, *, temperature: float = 0.7,
                       max_tokens: int = 300) -> Optional[str]:
        base_payload = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        models = [self._model] + [m for m in _OPENROUTER_FREE_FALLBACKS if m != self._model]
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for model in models:
                    try:
                        result = await self._try_model(client, model, base_payload)
                        if result is not None:
                            if model != self._model:
                                logger.info("[wa-crm-ai] OpenRouter fallback used: %s", model)
                            return result
                    except httpx.HTTPStatusError:
                        continue
                    except Exception as e:  # noqa: BLE001
                        logger.warning("[wa-crm-ai] OpenRouter model %s error: %s", model, e)
                        continue
            logger.warning("[wa-crm-ai] OpenRouter: all models exhausted / rate-limited")
            return None
        except httpx.TimeoutException:
            logger.warning("[wa-crm-ai] OpenRouter timeout")
            return None
        except Exception as e:  # noqa: BLE001
            logger.warning("[wa-crm-ai] OpenRouter error: %s", e)
            return None

def _provider_choice() -> str:
    return (os.getenv("CASEHUB_AI_PROVIDER", "") or "").strip().lower()


def get_ai_provider() -> AIProvider:
    """Resolve the active AI provider from env. Default = NullProvider (AI off).

    Only an explicitly-selected provider WITH its key present becomes active.
    """
    choice = _provider_choice()
    if choice == "gemini":
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            try:
                from config import settings
                key = getattr(settings, "GEMINI_API_KEY", "") or ""
            except Exception:  # noqa: BLE001
                key = ""
        if key:
            return GeminiProvider(key)
        logger.info("[wa-crm-ai] CASEHUB_AI_PROVIDER=gemini but no GEMINI_API_KEY — disabled")
    if choice == "openrouter":
        key = os.getenv("OPENROUTER_API_KEY", "")
        _default_model = "meta-llama/llama-3.3-70b-instruct"
        _raw_model = os.getenv("CASEHUB_AI_MODEL", _default_model)
        model = _raw_model if "/" in _raw_model else _default_model
        if key:
            return OpenRouterProvider(key, model)
        logger.info("[wa-crm-ai] CASEHUB_AI_PROVIDER=openrouter but no OPENROUTER_API_KEY — disabled")
    # Unset / unknown / keyless -> AI off.
    return NullProvider()
