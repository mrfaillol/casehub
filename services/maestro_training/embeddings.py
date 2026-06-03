"""Local-only embedding adapter (Ollama). Stub for the alpha — no remote LLM calls.

Beta agosto: swap or fan-out to per-provider embeddings after DPA + per-org consent.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from typing import List, Optional

logger = logging.getLogger(__name__)

OLLAMA_URL_DEFAULT = "http://localhost:11434/api/embeddings"
OLLAMA_MODEL_DEFAULT = "nomic-embed-text"


def embed(text: str, *, model: str = OLLAMA_MODEL_DEFAULT, url: str = OLLAMA_URL_DEFAULT,
          timeout: float = 10.0) -> Optional[List[float]]:
    """Return an embedding vector or None if Ollama is unreachable."""
    if not text:
        return None
    body = json.dumps({"model": model, "prompt": text}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return payload.get("embedding")
    except Exception as exc:
        logger.warning("ollama embedding unavailable: %s", exc)
        return None
