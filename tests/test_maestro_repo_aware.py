"""Tests for the Maestro repo-aware (product knowledge) grounding — Fase 1.

Pins the load-bearing contracts:

1. **Secret/PII exclusion** — the path blocklist refuses .env/credentials/keys/
   uploads/lockfiles; the line-level redactor scrubs secret assignments and
   private-key headers. This is the primary control that keeps secrets out of the
   index (and therefore out of any prompt).
2. **Graceful degradation** — a missing/corrupt index yields an empty index and
   retrieve_repo_context() returns None, so the chat never breaks on a
   missing/offline index.
3. **Jurisprudence refusal** — with no active case-law source, a jurisprudence
   question is refused deterministically (no model call), while a bare law-article
   citation keeps its existing calibrated behaviour.
4. **Repo-aware flag** — OFF by default.

Run: pytest tests/test_maestro_repo_aware.py
"""
from __future__ import annotations

import asyncio
import json
import os

import pytest

from services.maestro_repo_index import (
    INDEX_SCHEMA_VERSION,
    RepoIndex,
    _cosine,
    chunk_text,
    redact_secret_lines,
    retrieve_repo_context,
    should_index_path,
)


# --- 1. exclusion / redaction (security control) ---------------------------
@pytest.mark.parametrize("path,expected", [
    ("routes/assistente.py", True),
    ("docs/maestro/pipeline-treinamento.md", True),
    ("migrations/2026-03-28_ai_sources.sql", True),
    ("deploy.sh", True),
    (".env", False),
    ("config/.env.alpha", False),
    ("services/whatsapp-bot/credentials.json", False),
    ("certs/server.key", False),
    ("certs/server.pem", False),
    ("uploads/org_4/petition.pdf", False),      # tenant data — red line
    ("data/casehub.sqlite", False),
    ("package-lock.json", False),
    ("static/app.min.js", False),
    ("logo.png", False),                         # binary ext not included
])
def test_should_index_path(path, expected):
    assert should_index_path(path) is expected


@pytest.mark.parametrize("line,secret", [
    ("SECRET" + "_KEY=" + "supersecret" + "value123", "supersecret" + "value123"),
    ("API" + "_KEY: " + "abcdef" + "123456", "abcdef" + "123456"),
    ('client_secret = "' + "ghp_" + "AkY4aN7v" + "XXXXXXXXXXXX" + '"', "ghp_" + "AkY4aN7v" + "XXXXXXXXXXXX"),
    ("CASEHUB_INBOUND_HMAC" + "_SECRET=" + "deadbeef" + "cafe1234", "deadbeef" + "cafe1234"),
    ("password=" + "hunter2" + "hunter2", "hunter2" + "hunter2"),
    ('AUTH' + '_TOKEN="' + "abc123" + "def456" + "ghi789" + '"', "abc123" + "def456" + "ghi789"),
])
def test_redact_secret_lines_scrubs_secrets(line, secret):
    out = redact_secret_lines(line)
    assert secret not in out, f"secret leaked into index: {line!r}"
    assert "REDACTED" in out


def test_redact_private_key_header():
    assert "BEGIN RSA PRIVATE KEY" not in redact_secret_lines(
        "-----BEGIN RSA PRIVATE KEY-----"
    )


def test_redact_does_not_over_redact_normal_code():
    code = "def get_user(request, db):\n    return db.query(User).first()\nx = 1 + 2"
    out = redact_secret_lines(code)
    assert "get_user" in out
    assert "REDACTED" not in out


# --- helpers ---------------------------------------------------------------
def test_chunking_and_cosine():
    assert chunk_text("hi") == ["hi"]
    big = chunk_text(("A" * 500 + "\n\n") * 5, max_chars=600)
    assert len(big) >= 4
    assert abs(_cosine([1, 0, 0], [1, 0, 0]) - 1.0) < 1e-9
    assert _cosine([1, 0], [0, 1]) == 0.0
    assert _cosine([], [1, 2]) == 0.0


# --- 2. graceful degradation ----------------------------------------------
def test_missing_index_degrades(tmp_path):
    RepoIndex.reset_cache()
    idx = RepoIndex.get(str(tmp_path / "nope.json"))
    assert idx.available is False
    assert idx.search([1, 2, 3]) == []
    RepoIndex.reset_cache()
    assert retrieve_repo_context("q", index_path=str(tmp_path / "nope.json")) is None


def test_corrupt_index_degrades(tmp_path):
    bad = tmp_path / "repo_index.json"
    bad.write_text("{not valid json")
    RepoIndex.reset_cache()
    assert RepoIndex.get(str(bad)).available is False


def test_schema_mismatch_rejected(tmp_path):
    p = tmp_path / "repo_index.json"
    p.write_text(json.dumps({
        "schema_version": INDEX_SCHEMA_VERSION + 99,
        "chunks": [{"path": "x.py", "text": "y", "embedding": [1.0]}],
    }))
    RepoIndex.reset_cache()
    assert RepoIndex.get(str(p)).available is False


def test_index_reredacts_on_load(tmp_path):
    """Even a tampered index that smuggled a secret line is scrubbed at load."""
    p = tmp_path / "repo_index.json"
    p.write_text(json.dumps({
        "schema_version": INDEX_SCHEMA_VERSION,
        "chunks": [{
            "path": "evil.py",
            "title": "evil.py",
            "text": "ok line\nSECRET_KEY=leakedvalue123456\nok",
            "embedding": [0.1, 0.2, 0.3],
        }],
    }))
    RepoIndex.reset_cache()
    idx = RepoIndex.get(str(p))
    assert idx.available
    assert "leakedvalue123456" not in idx.chunks[0].text


# --- 3. jurisprudence refusal ---------------------------------------------
def test_jurisprudence_refused_without_source():
    from services.maestro_lite import MaestroLite, JURISPRUDENCE_REFUSAL
    m = MaestroLite(org_name="Escritorio Demo")
    res = asyncio.run(m.chat("Tem algum acórdão do STJ sobre usucapião?"))
    # Deterministic refusal — must not have called Ollama.
    assert res["status"] == "ok"
    assert res["response"] == JURISPRUDENCE_REFUSAL


def test_law_article_not_treated_as_jurisprudence():
    from services.maestro_lite import JURISPRUDENCE_RE, LAW_CITATION_RE
    q = "o que diz o art. 212 do CPC"
    # A bare law-article ask must NOT trigger the jurisprudence-only refusal path.
    assert not (JURISPRUDENCE_RE.search(q) and not LAW_CITATION_RE.search(q))


# --- 4. flag ---------------------------------------------------------------
def test_repo_aware_flag_off_by_default(monkeypatch):
    from services import maestro_lite
    monkeypatch.delenv("CASEHUB_MAESTRO_REPO_AWARE_ENABLED", raising=False)
    # config default is False
    assert maestro_lite.repo_aware_enabled() is False
    monkeypatch.setenv("CASEHUB_MAESTRO_REPO_AWARE_ENABLED", "true")
    assert maestro_lite.repo_aware_enabled() is True
