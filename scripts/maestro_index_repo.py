#!/usr/bin/env python3
"""Build the Maestro repo-aware RAG index from the CaseHub source tree.

Indexes the CaseHub PRODUCT (code + docs) so the Maestro assistant can answer
questions about how the product works WITH grounding (cites the source file) and
refuse to invent. See services/maestro_repo_index.py for the full rationale and
the Sentinela red-line boundary (this indexes product knowledge ONLY — never
tenant data, secrets, .env, credentials, or PII).

USAGE
-----
    # Build into the default runtime path (runtime/maestro/repo_index.json):
    python scripts/maestro_index_repo.py

    # Custom root / output / ollama:
    python scripts/maestro_index_repo.py \
        --root . \
        --out runtime/maestro/repo_index.json \
        --ollama-url http://localhost:11434/api/embeddings \
        --model nomic-embed-text

In the alpha container, Ollama is reachable at http://ollama:11434 — pass
``--ollama-url http://ollama:11434/api/embeddings``.

The output index is REGENERABLE and must NOT be committed (it embeds file
contents and can be large). ``runtime/`` is gitignored. Re-run after meaningful
code/doc changes (e.g. as a post-deploy step or a periodic job).

SAFETY
------
- Hard path blocklist (services.maestro_repo_index.INDEX_EXCLUDE_GLOBS): .env,
  credentials, keys, uploads/, data/, lockfiles, minified assets, etc.
- Honours .gitignore via ``git ls-files`` when run inside a git repo (so only
  tracked, non-ignored files are even considered).
- Line-level secret redaction on every chunk before embedding.
- Prints a summary of what was included/excluded; never embeds an excluded path.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import List, Optional

# Make the repo importable when run as a script from anywhere.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from services.maestro_repo_index import (  # noqa: E402
    INDEX_SCHEMA_VERSION,
    chunk_text,
    redact_secret_lines,
    should_index_path,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("maestro_index_repo")

# Per-file size ceiling (bytes). Skip huge generated/vendored files — product
# knowledge lives in source + docs, not multi-MB blobs.
MAX_FILE_BYTES = 256 * 1024


def _git_tracked_files(root: str) -> Optional[List[str]]:
    """Return git-tracked, non-ignored files (repo-relative POSIX), or None."""
    try:
        out = subprocess.check_output(
            ["git", "-C", root, "ls-files", "--cached", "--exclude-standard"],
            stderr=subprocess.DEVNULL,
        )
        files = [line for line in out.decode("utf-8").splitlines() if line.strip()]
        return files or None
    except Exception:
        return None


def _walk_files(root: str) -> List[str]:
    """Fallback filesystem walk (repo-relative POSIX paths) when not a git repo."""
    collected: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune obviously-excluded directories early for speed.
        dirnames[:] = [
            d for d in dirnames
            if d not in {".git", "node_modules", "__pycache__", ".venv", "venv",
                         "runtime", "uploads", "backups"}
        ]
        for name in filenames:
            abs_path = os.path.join(dirpath, name)
            rel = os.path.relpath(abs_path, root).replace(os.sep, "/")
            collected.append(rel)
    return collected


def _git_commit(root: str) -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", root, "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return out.decode("utf-8").strip()
    except Exception:
        return ""


def build_index(root: str, out_path: str, *, ollama_url: str, model: str) -> dict:
    from services.maestro_training.embeddings import embed

    root = os.path.abspath(root)
    candidates = _git_tracked_files(root)
    source = "git ls-files"
    if candidates is None:
        candidates = _walk_files(root)
        source = "filesystem walk"
    logger.info("Discovered %d candidate files via %s", len(candidates), source)

    eligible = [rel for rel in candidates if should_index_path(rel)]
    logger.info("Eligible after blocklist + extension filter: %d", len(eligible))

    chunks_out: List[dict] = []
    files_indexed = 0
    files_skipped_size = 0
    embed_failures = 0

    for rel in sorted(eligible):
        abs_path = os.path.join(root, rel)
        try:
            size = os.path.getsize(abs_path)
        except OSError:
            continue
        if size > MAX_FILE_BYTES:
            files_skipped_size += 1
            continue
        try:
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as fh:
                raw = fh.read()
        except Exception:
            continue

        scrubbed = redact_secret_lines(raw)
        pieces = chunk_text(scrubbed)
        if not pieces:
            continue

        any_chunk = False
        for idx, piece in enumerate(pieces):
            vec = embed(piece, model=model, url=ollama_url)
            if not vec:
                embed_failures += 1
                continue
            title = rel if len(pieces) == 1 else f"{rel} (parte {idx + 1}/{len(pieces)})"
            chunks_out.append({
                "path": rel,
                "title": title,
                "text": piece,
                "embedding": vec,
            })
            any_chunk = True
        if any_chunk:
            files_indexed += 1
            if files_indexed % 25 == 0:
                logger.info("  ...embedded %d files (%d chunks)", files_indexed, len(chunks_out))

    payload = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "source_commit": _git_commit(root),
        "built_at": datetime.now(tz=timezone.utc).isoformat(),
        "model": model,
        "chunk_count": len(chunks_out),
        "chunks": chunks_out,
    }

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)

    logger.info("-" * 60)
    logger.info("Index written: %s", out_path)
    logger.info("  files indexed     : %d", files_indexed)
    logger.info("  chunks            : %d", len(chunks_out))
    logger.info("  skipped (too big) : %d", files_skipped_size)
    logger.info("  embed failures    : %d", embed_failures)
    logger.info("  source commit     : %s", payload["source_commit"] or "(not a git repo)")
    if embed_failures and not chunks_out:
        logger.error("No chunks embedded — is Ollama running at %s with model %s?",
                     ollama_url, model)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=_REPO_ROOT, help="Repo root to index")
    parser.add_argument(
        "--out",
        default=os.path.join(_REPO_ROOT, "runtime", "maestro", "repo_index.json"),
        help="Output index path (gitignored; do NOT commit)",
    )
    parser.add_argument("--ollama-url",
                        default=os.getenv("OLLAMA_EMBED_URL",
                                          "http://localhost:11434/api/embeddings"))
    parser.add_argument("--model",
                        default=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"))
    args = parser.parse_args()

    build_index(args.root, args.out, ollama_url=args.ollama_url, model=args.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
