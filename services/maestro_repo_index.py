"""Maestro repo-aware RAG index — product/code knowledge retrieval.

WHAT THIS IS
------------
A *product knowledge* retrieval layer for the Maestro assistant. It indexes the
CaseHub **source code + documentation** (how the product works) so that when a
user asks about the PRODUCT ("como funciona o módulo de controladoria?", "onde
configuro o WhatsApp?") the assistant can answer with grounding — citing the
file/doc it pulled from — instead of hallucinating.

WHAT THIS IS NOT (Sentinela red-line boundary)
----------------------------------------------
This index holds ONLY the CaseHub product repo+docs, which are identical for
every tenant. It does **NOT** index tenant data (petitions, client PII, case
files). The multitenant/Maestro threat model
(agents/knowledge/sentinela/audits/multitenant-maestro-ia-2026-05-14.md, Sentinela
APPROVED 2026-05-15) governs tenant-data ingestion (anonymization, per-tenant
isolation, RLS, DPIA, consent) — that pipeline is GATED and NOT touched here.
Because product knowledge is the same for all tenants, there is no cross-tenant
leakage surface: A3/A4 ("Maestro cross-contamination", "pipeline poisoning") do
not apply to a read-only index of our own published code/docs.

SECRET / PII EXCLUSION (build-time, defence in depth)
-----------------------------------------------------
The indexer (scripts/maestro_index_repo.py) refuses to ingest .env, credentials,
keys, tokens, lockfiles, and other secret-bearing paths, and additionally runs a
line-level redaction pass. See INDEX_EXCLUDE_GLOBS / SECRET_LINE_RE below — both
the build script and this loader share them so the runtime never trusts an index
that smuggled a secret past the build step.

EMBEDDINGS (zero external transfer — F-8 of the spec)
-----------------------------------------------------
Vectors come from the local Ollama ``nomic-embed-text`` model (same container the
alpha already runs, docker-compose.alpha.yml). No document text ever leaves the
host. We reuse services.maestro_training.embeddings.embed().

STORAGE (regenerable, never committed)
--------------------------------------
The index is a single JSON file produced at build time and loaded read-only at
runtime. It lives under a runtime volume (default ``runtime/maestro/`` inside the
app, overridable via ``MAESTRO_REPO_INDEX_PATH``). It is **gitignored** and
**regenerable** from source — we never commit the index (it embeds file contents
and can be large). If absent, the assistant degrades gracefully to "no product
index" rather than crashing.

NO NUMPY DEPENDENCY
-------------------
Cosine similarity is implemented in pure Python on purpose: numpy is not a core
CaseHub-lite dependency (see requirements.txt), and an external lib must not
become a core runtime requirement (AGENTS.md). For a repo-sized index (low
thousands of chunks) the pure-Python dot product is well within latency budget.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared exclusion / redaction policy (imported by the build script too).
# ---------------------------------------------------------------------------
# Path fragments (case-insensitive substring match on the POSIX relative path)
# that must NEVER be indexed. Anything secret-bearing, credential-bearing, or
# tenant/PII-bearing is denied here as a hard gate. The build script also honours
# .gitignore, but this list is the authoritative blocklist even if .gitignore
# drifts.
INDEX_EXCLUDE_GLOBS: tuple[str, ...] = (
    ".env",
    ".env.",
    "/.git/",
    "/node_modules/",
    "/.venv/",
    "/venv/",
    "/__pycache__/",
    "secret",
    "secrets",
    "credential",
    "credentials",
    ".pem",
    ".key",
    "id_rsa",
    "id_ed25519",
    ".p12",
    ".pfx",
    "/.ssh/",
    ".keychain",
    "password",
    "passwd",
    ".sqlite",
    ".db",
    "/uploads/",          # tenant-uploaded files — out of scope (red line)
    "/data/",             # runtime/tenant data
    "/backups/",
    "/runtime/",          # the index volume itself
    ".pyc",
    ".min.js",
    ".min.css",
    ".map",
    ".lock",
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
)

# File extensions worth indexing as product knowledge (code + docs + config docs).
INDEX_INCLUDE_EXTS: tuple[str, ...] = (
    ".py", ".md", ".rst", ".txt",
    ".html", ".js", ".ts", ".css",
    ".yml", ".yaml", ".toml", ".ini", ".cfg",
    ".sql", ".sh",
)

# Line-level redaction. Any line that looks like it carries a secret is dropped
# before the chunk is stored — defence in depth so even an accidentally-indexed
# config-ish file cannot leak an assignment like ``SECRET_KEY=...``. This is a
# coarse heuristic (Maestro repo index is product knowledge, not a secret store);
# the path blocklist above is the primary control.
SECRET_LINE_RE = re.compile(
    r"""(?ix)
    (?:
        # A secret-ish keyword possibly followed by more identifier chars
        # (e.g. SECRET_KEY, API_KEY, client_secret), then : or = then a value.
        \b
        (?:api|access|client|secret|private|signing|encryption)?
        [_-]?
        (?:key|secret|token|password|passwd|hmac|bearer|authorization|credential)
        [a-z0-9_]*
        \s*[:=]\s*
        \S+
    )
    |
    (?:                       # high-entropy-ish assignment to an uppercase const
        \b[A-Z0-9_]{6,}\s*=\s*["']?[A-Za-z0-9+/=_\-]{16,}["']?
    )
    |
    # NOTE: VERBOSE mode ignores unescaped whitespace, so spaces here use \s.
    (?:-----BEGIN\s[A-Z\s]+PRIVATE\sKEY-----)
    """,
    re.VERBOSE,
)

# Index schema version — bumped if the on-disk format changes so a stale index is
# rejected rather than silently mis-read.
INDEX_SCHEMA_VERSION = 1

DEFAULT_INDEX_PATH = os.getenv(
    "MAESTRO_REPO_INDEX_PATH",
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "runtime", "maestro", "repo_index.json",
    ),
)


def should_index_path(rel_path: str) -> bool:
    """True if ``rel_path`` (POSIX, repo-relative) is eligible for indexing."""
    low = rel_path.lower()
    for frag in INDEX_EXCLUDE_GLOBS:
        if frag in low:
            return False
    _, ext = os.path.splitext(low)
    return ext in INDEX_INCLUDE_EXTS


def redact_secret_lines(text: str) -> str:
    """Drop lines that match the secret heuristic. Returns the scrubbed text."""
    kept: List[str] = []
    for line in text.splitlines():
        if SECRET_LINE_RE.search(line):
            kept.append("[REDACTED: possível segredo removido do índice]")
        else:
            kept.append(line)
    return "\n".join(kept)


def chunk_text(text: str, *, max_chars: int = 1200, overlap: int = 150) -> List[str]:
    """Split text into overlapping character windows on paragraph boundaries.

    Simple, dependency-free chunker. Prefers to break on blank lines so code
    blocks / doc sections stay coherent; falls back to hard windows for very long
    runs without blank lines.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    paragraphs = re.split(r"\n\s*\n", text)
    chunks: List[str] = []
    buf = ""
    for para in paragraphs:
        if len(buf) + len(para) + 2 <= max_chars:
            buf = f"{buf}\n\n{para}" if buf else para
            continue
        if buf:
            chunks.append(buf)
        if len(para) <= max_chars:
            buf = para
        else:
            # Hard-window an oversized paragraph.
            start = 0
            while start < len(para):
                chunks.append(para[start:start + max_chars])
                start += max_chars - overlap
            buf = ""
    if buf:
        chunks.append(buf)
    return chunks


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Pure-Python cosine similarity. Returns 0.0 on degenerate input."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


@dataclass
class RepoChunk:
    path: str          # repo-relative source path (the citation)
    title: str         # human label (path or doc heading)
    text: str          # chunk content (already secret-redacted at build time)
    embedding: List[float]


class RepoIndex:
    """Read-only in-memory product-knowledge index loaded from a JSON file.

    Lazy singleton: the JSON is read once per process and cached. ``get()`` is
    safe to call from request handlers; it never raises — a missing/corrupt index
    yields an *empty* index so the chat degrades to "no product grounding".
    """

    _instance: Optional["RepoIndex"] = None
    _loaded_path: Optional[str] = None

    def __init__(self, chunks: List[RepoChunk], *, source_commit: str = "", built_at: str = ""):
        self.chunks = chunks
        self.source_commit = source_commit
        self.built_at = built_at

    # -- construction --------------------------------------------------------
    @classmethod
    def get(cls, path: Optional[str] = None) -> "RepoIndex":
        target = path or DEFAULT_INDEX_PATH
        if cls._instance is not None and cls._loaded_path == target:
            return cls._instance
        cls._instance = cls._load(target)
        cls._loaded_path = target
        return cls._instance

    @classmethod
    def reset_cache(cls) -> None:
        """Drop the cached singleton (used by tests / after a rebuild)."""
        cls._instance = None
        cls._loaded_path = None

    @classmethod
    def _load(cls, path: str) -> "RepoIndex":
        if not os.path.exists(path):
            logger.info("maestro_repo_index: no index at %s (product grounding disabled)", path)
            return cls([])
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception as exc:  # noqa: BLE001 — never crash the chat on a bad index
            logger.warning("maestro_repo_index: failed to read %s: %s", path, exc)
            return cls([])

        if payload.get("schema_version") != INDEX_SCHEMA_VERSION:
            logger.warning(
                "maestro_repo_index: schema mismatch (got %s, want %s) — ignoring index",
                payload.get("schema_version"), INDEX_SCHEMA_VERSION,
            )
            return cls([])

        chunks: List[RepoChunk] = []
        for raw in payload.get("chunks", []):
            emb = raw.get("embedding")
            if not emb:
                continue
            # Defence in depth: re-redact at load time so a tampered index that
            # smuggled a secret line still gets scrubbed before it reaches a prompt.
            text = redact_secret_lines(raw.get("text", ""))
            chunks.append(RepoChunk(
                path=raw.get("path", ""),
                title=raw.get("title") or raw.get("path", ""),
                text=text,
                embedding=emb,
            ))
        logger.info(
            "maestro_repo_index: loaded %d chunks from %s (commit %s)",
            len(chunks), path, payload.get("source_commit", "?"),
        )
        return cls(
            chunks,
            source_commit=payload.get("source_commit", ""),
            built_at=payload.get("built_at", ""),
        )

    # -- query ---------------------------------------------------------------
    @property
    def available(self) -> bool:
        return bool(self.chunks)

    def search(self, query_embedding: Sequence[float], *, top_k: int = 4,
               min_score: float = 0.45) -> List[tuple[RepoChunk, float]]:
        """Return up to ``top_k`` (chunk, score) pairs above ``min_score``."""
        if not self.chunks or not query_embedding:
            return []
        scored = [
            (chunk, _cosine(query_embedding, chunk.embedding))
            for chunk in self.chunks
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [(c, s) for c, s in scored[:top_k] if s >= min_score]


def retrieve_repo_context(message: str, *, top_k: int = 4,
                          index_path: Optional[str] = None) -> Optional[str]:
    """Embed ``message`` locally, search the repo index, and format grounded context.

    Returns a citation-annotated context block ready to inject into the Maestro
    system context, or ``None`` when:
      - the index is absent/empty, or
      - Ollama embeddings are unavailable, or
      - nothing scores above the relevance floor.

    The caller (services/maestro_lite.py) treats ``None`` as "no product grounding
    found" and the system prompt then instructs the model to say it could not find
    the answer in the product knowledge — never to invent.
    """
    index = RepoIndex.get(index_path)
    if not index.available:
        return None

    # Local embedding (Ollama nomic-embed-text). Lazily imported so a missing
    # Ollama at import time never breaks the module.
    try:
        from services.maestro_training.embeddings import embed
    except Exception as exc:  # noqa: BLE001
        logger.warning("maestro_repo_index: embeddings module unavailable: %s", exc)
        return None

    embed_url = os.getenv("OLLAMA_EMBED_URL")
    embed_model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    kwargs = {"model": embed_model}
    if embed_url:
        kwargs["url"] = embed_url

    query_vec = embed(message, **kwargs)
    if not query_vec:
        logger.info("maestro_repo_index: no query embedding (Ollama embed offline?)")
        return None

    hits = index.search(query_vec, top_k=top_k)
    if not hits:
        return None

    blocks: List[str] = []
    for chunk, score in hits:
        snippet = chunk.text.strip()
        if len(snippet) > 1500:
            snippet = snippet[:1500] + "..."
        blocks.append(f"[Fonte do produto: {chunk.path}] (relevância {score:.2f})\n{snippet}")

    header = (
        "Conhecimento do PRODUTO CaseHub (código/documentação indexada). "
        "Use APENAS o que está abaixo para responder sobre como o produto "
        "funciona, e CITE o arquivo-fonte. Se a resposta não estiver aqui, "
        "diga que não encontrou na documentação do produto — não invente."
    )
    return header + "\n\n" + "\n\n---\n\n".join(blocks)
