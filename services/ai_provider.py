"""Provider-agnostic AI assist layer (PR9 — per ruling 2026-05-31 + Sentinela).

Default is NullProvider (AI OFF) — non-Gemini per Equipe CaseHub's decision. A real
provider activates ONLY when CASEHUB_AI_PROVIDER selects it AND its key is present,
so "no key → no provider → no call" is the built-in cost/secret circuit-breaker.
Adds NO new secret and commits NO key. Every call is live + EPHEMERAL (persists
nothing — Council training-data VETO). To plug a different provider later, add an
adapter + a branch in get_ai_provider(); the full Sentinela gate runs before a
second real key (e.g. OPENAI_API_KEY) is ever introduced.
"""
from __future__ import annotations

import json
import logging
import os
from typing import AsyncIterator, Optional

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

    async def generate_stream(self, prompt: str, *, temperature: float = 0.7,
                              max_tokens: int = 300) -> AsyncIterator[str]:
        """Yield text chunks when the provider supports streaming.

        Providers without a native stream still satisfy the contract by yielding
        their single full response once. Callers can therefore avoid falling back
        to a different backend just because the UI is using SSE.
        """
        text = await self.generate(prompt, temperature=temperature, max_tokens=max_tokens)
        if text:
            yield text


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
                     "HTTP-Referer": "https://demo.casehub.example",
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


def _extract_openai_stream_delta(data: dict) -> str:
    """Return the text delta from an OpenAI-compatible stream payload."""
    choices = data.get("choices") or []
    if not choices:
        return ""
    choice = choices[0] or {}
    delta = choice.get("delta") or {}
    text = delta.get("content")
    if text is None:
        text = choice.get("text")
    if text is None:
        message = choice.get("message") or {}
        text = message.get("content")
    return text or ""


class NvidiaProvider(AIProvider):
    """NVIDIA NIM adapter (build.nvidia.com - OpenAI-compatible, GPU-hosted).

    Live, best-effort, 45s timeout, persists NOTHING locally. Activated by
    CASEHUB_AI_PROVIDER=nvidia + NVIDIA_API_KEY. The key is held only in memory
    and is NEVER logged. NOTE: prompts (incl. firm context) leave the VPS to the
    NVIDIA API on activation -> egress must be reviewed by Sentinela before prod.
    """

    name = "nvidia"
    _URL = "https://integrate.api.nvidia.com/v1/chat/completions"

    def __init__(self, api_key: str, model: str = "meta/llama-3.3-70b-instruct"):
        self._api_key = api_key  # held only in memory; NEVER logged
        self._model = model

    async def generate(self, prompt: str, *, temperature: float = 0.7,
                       max_tokens: int = 300):
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
                resp = await client.post(
                    self._URL,
                    headers={"Authorization": f"Bearer {self._api_key}",
                             "Accept": "application/json"},
                    json=payload,
                )
            if resp.status_code != 200:
                logger.warning("[wa-crm-ai] NVIDIA HTTP %s (model=%s)", resp.status_code, self._model)
                return None
            data = resp.json()
            text = (data.get("choices", [{}])[0].get("message", {}).get("content"))
            return text.strip() if text else None
        except httpx.TimeoutException:
            logger.warning("[wa-crm-ai] NVIDIA timeout")
            return None
        except Exception as e:  # noqa: BLE001
            logger.warning("[wa-crm-ai] NVIDIA error: %s", e)
            return None

    async def generate_stream(self, prompt: str, *, temperature: float = 0.7,
                              max_tokens: int = 300) -> AsyncIterator[str]:
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
                async with client.stream(
                    "POST",
                    self._URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Accept": "text/event-stream",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                ) as resp:
                    if resp.status_code != 200:
                        logger.warning("[wa-crm-ai] NVIDIA stream HTTP %s (model=%s)", resp.status_code, self._model)
                        return
                    async for raw_line in resp.aiter_lines():
                        line = (raw_line or "").strip()
                        if not line or line.startswith(":"):
                            continue
                        if line.startswith("data:"):
                            line = line[5:].strip()
                        if line == "[DONE]":
                            return
                        try:
                            chunk = _extract_openai_stream_delta(json.loads(line))
                        except (json.JSONDecodeError, TypeError, ValueError):
                            continue
                        if chunk:
                            yield chunk
        except httpx.TimeoutException:
            logger.warning("[wa-crm-ai] NVIDIA stream timeout")
            return
        except Exception as e:  # noqa: BLE001
            logger.warning("[wa-crm-ai] NVIDIA stream error: %s", e)
            return


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
    if choice == "nvidia":
        key = os.getenv("NVIDIA_API_KEY", "")
        if not key:
            try:
                from config import settings
                key = getattr(settings, "NVIDIA_API_KEY", "") or ""
            except Exception:  # noqa: BLE001
                key = ""
        _default_model = "meta/llama-3.3-70b-instruct"
        _raw_model = os.getenv("CASEHUB_AI_MODEL", _default_model)
        model = _raw_model if "/" in _raw_model else _default_model
        if key:
            return NvidiaProvider(key, model)
        logger.info("[wa-crm-ai] CASEHUB_AI_PROVIDER=nvidia but no NVIDIA_API_KEY - disabled")
    # Unset / unknown / keyless -> AI off.
    return NullProvider()
