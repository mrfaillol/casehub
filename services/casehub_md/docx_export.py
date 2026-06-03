"""CaseHub.md — DOCX export via Pandoc (Fatia 4).

Conversão markdown→DOCX usando Pandoc instalado no sistema (GPL-2 binário,
chamado via subprocess; não vendoriza no repo). Mesma filosofia da Fatia 6
(Tesseract OCR).

Red lines:
  - sem shell=True (sem injection)
  - markdown via arquivo temp, NÃO via argv
  - timeout obrigatório (10s default)
  - cleanup garantido em try/finally
  - tamanho máximo 2MB do markdown (defesa em profundidade contra DoS)
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MAX_MARKDOWN_BYTES = 2 * 1024 * 1024  # 2 MB
PANDOC_TIMEOUT_SECONDS = 10
PANDOC_FORMAT_FROM = "gfm+pipe_tables+task_lists+strikeout"
PANDOC_FORMAT_TO = "docx"

# Templates DOCX disponíveis. Path absoluto resolvido relativo a este arquivo.
# Fatia 4.1 — `oab` é o template canônico de petição brasileira:
#   - Times New Roman 12pt corpo (16/14/13pt headings)
#   - Margens 3/3/2/2 cm (top/left/bottom/right) — ABNT NBR 14724 / praxe OAB
#   - Espaçamento 1.5; alinhamento body justify
_TEMPLATES_DIR = (Path(__file__).resolve().parent.parent.parent
                  / "docs" / "casehub-md" / "templates")
TEMPLATES: dict[str, Path] = {
    "oab": _TEMPLATES_DIR / "oab.docx",
}


def get_template_path(name: Optional[str]) -> Optional[Path]:
    """Resolve template name to a path on disk; None if not found / unset."""
    if not name:
        return None
    template = TEMPLATES.get(name.strip().lower())
    if template is None:
        return None
    return template if template.is_file() else None


class PandocUnavailable(RuntimeError):
    """Pandoc binary not found on PATH."""


class MarkdownTooLarge(ValueError):
    """Markdown payload exceeds MAX_MARKDOWN_BYTES."""


class PandocFailure(RuntimeError):
    """Pandoc returned non-zero exit. Includes stderr tail for debug."""


@dataclass(frozen=True)
class DocxExportResult:
    """Bytes of the generated DOCX plus the Pandoc stderr tail (for logging)."""
    data: bytes
    pandoc_stderr_tail: str


def pandoc_available() -> bool:
    """Return True if `pandoc` is on PATH. Cheap probe — used by startup check."""
    return shutil.which("pandoc") is not None


def convert_markdown_to_docx(
    markdown: str,
    *,
    reference_docx: Optional[Path] = None,
    timeout: float = PANDOC_TIMEOUT_SECONDS,
) -> DocxExportResult:
    """Convert markdown text to DOCX bytes via Pandoc.

    Args:
        markdown: source text (GFM with pipe-tables, task-lists, strikethrough).
        reference_docx: optional path to a Pandoc reference.docx for styling.
            Fatia 4 ships without one; Fatia 4.1 commits `docs/casehub-md/templates/oab.docx`.
        timeout: hard wall-clock limit for the Pandoc subprocess.

    Raises:
        PandocUnavailable: pandoc binary not installed on the VPS.
        MarkdownTooLarge: markdown exceeds MAX_MARKDOWN_BYTES.
        PandocFailure: subprocess exited non-zero (stderr included in message).
        subprocess.TimeoutExpired: Pandoc took longer than `timeout` seconds.
    """
    if not pandoc_available():
        raise PandocUnavailable(
            "pandoc not found on PATH. Install with `apt install pandoc` on the VPS."
        )

    encoded = markdown.encode("utf-8")
    if len(encoded) > MAX_MARKDOWN_BYTES:
        raise MarkdownTooLarge(
            f"markdown is {len(encoded)} bytes; limit is {MAX_MARKDOWN_BYTES}"
        )

    # Use a dedicated temp dir we control (easier cleanup, no race with NamedTemporaryFile
    # delete-on-close quirks across platforms).
    tmp_dir = tempfile.mkdtemp(prefix="casehub-md-docx-")
    src_path = os.path.join(tmp_dir, "in.md")
    out_path = os.path.join(tmp_dir, "out.docx")
    try:
        with open(src_path, "wb") as f:
            f.write(encoded)

        cmd = [
            "pandoc",
            src_path,
            "-o",
            out_path,
            f"--from={PANDOC_FORMAT_FROM}",
            f"--to={PANDOC_FORMAT_TO}",
            "--standalone",
        ]
        if reference_docx is not None:
            cmd += [f"--reference-doc={reference_docx}"]

        try:
            completed = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                timeout=timeout,
                # shell=False (default) — explicit to make audit-grep obvious
            )
        except subprocess.TimeoutExpired:
            logger.warning("pandoc DOCX export exceeded %.1fs timeout", timeout)
            raise

        if completed.returncode != 0:
            stderr_tail = (completed.stderr or b"").decode("utf-8", errors="replace")[-2000:]
            logger.error("pandoc exit=%s stderr_tail=%s", completed.returncode, stderr_tail)
            raise PandocFailure(
                f"pandoc returned {completed.returncode}. stderr tail: {stderr_tail}"
            )

        try:
            with open(out_path, "rb") as f:
                data = f.read()
        except OSError as e:
            raise PandocFailure(f"pandoc claimed success but {out_path} is missing: {e}")

        stderr_tail = (completed.stderr or b"").decode("utf-8", errors="replace")[-500:]
        return DocxExportResult(data=data, pandoc_stderr_tail=stderr_tail)
    finally:
        # Best-effort cleanup; safe even if files don't exist.
        for p in (src_path, out_path):
            try:
                os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass
