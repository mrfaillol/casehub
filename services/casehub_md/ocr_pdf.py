"""CaseHub.md — PDF / image OCR via Tesseract + Poppler (Fatia 6).

Binários system (não vendorizados):
  - `pdftotext`  (Poppler, GPL-2) — text-layer extraction (PDF digital)
  - `pdftoppm`   (Poppler, GPL-2) — PDF → PNG per page
  - `tesseract`  (Apache 2.0)     — OCR engine

Heurística PDF híbrida: `pdftotext` primeiro (rápido p/ PDFs digitais);
fallback para `pdftoppm` + `tesseract` se o text-layer vier vazio/curto.

Sem upload streaming nem worker assíncrono — POC síncrono. Timeout total
30s + rejeição de file >10MB cobrem o uso típico (PDF jurídico <10 págs).
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DIGITAL_TEXT_MIN_CHARS = 80    # below this → fall back to OCR
PER_PAGE_OCR_TIMEOUT = 12       # seconds
PDFTOTEXT_TIMEOUT = 5
PDFTOPPM_TIMEOUT = 20
MAX_PAGES = 50                  # 422 if PDF has more

DEFAULT_LANG = "por+eng"        # Tesseract language packs


class OcrUnavailable(RuntimeError):
    """Tesseract or Poppler binaries missing on PATH."""


class FileTooLarge(ValueError):
    pass


class TooManyPages(ValueError):
    pass


@dataclass(frozen=True)
class OcrResult:
    markdown: str
    source: str             # 'pdftotext' | 'tesseract' | 'tesseract-pdf'
    pages: Optional[int]
    took_ms: int


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def poppler_available() -> bool:
    return shutil.which("pdftotext") is not None and shutil.which("pdftoppm") is not None


def _run(cmd: list[str], timeout: float, *, capture: bool = True) -> subprocess.CompletedProcess:
    """Thin wrapper enforcing shell=False + timeout for audit-grep clarity."""
    return subprocess.run(cmd, check=False, capture_output=capture, timeout=timeout)


def _pdftotext(path: str) -> str:
    completed = _run(["pdftotext", "-layout", path, "-"], timeout=PDFTOTEXT_TIMEOUT)
    if completed.returncode != 0:
        logger.warning("pdftotext returned %s: %s", completed.returncode, completed.stderr[:200])
        return ""
    return (completed.stdout or b"").decode("utf-8", errors="replace")


def _pdftoppm(path: str, out_prefix: str) -> list[str]:
    """Convert PDF to PNGs (300dpi). Returns sorted list of generated PNG paths."""
    _run(
        [
            "pdftoppm",
            "-png",
            "-r",
            "300",
            path,
            out_prefix,
        ],
        timeout=PDFTOPPM_TIMEOUT,
    )
    out_dir = os.path.dirname(out_prefix)
    base = os.path.basename(out_prefix)
    pages = sorted(
        os.path.join(out_dir, name)
        for name in os.listdir(out_dir)
        if name.startswith(base) and name.endswith(".png")
    )
    return pages


def _tesseract_image(path: str, lang: str) -> str:
    completed = _run(
        ["tesseract", path, "stdout", "-l", lang],
        timeout=PER_PAGE_OCR_TIMEOUT,
    )
    if completed.returncode != 0:
        logger.warning(
            "tesseract returned %s on %s: %s",
            completed.returncode,
            path,
            (completed.stderr or b"")[:200],
        )
    return (completed.stdout or b"").decode("utf-8", errors="replace")


def _count_pdf_pages(path: str) -> int:
    completed = _run(["pdfinfo", path], timeout=PDFTOTEXT_TIMEOUT)
    if completed.returncode != 0:
        return -1
    for line in (completed.stdout or b"").decode("utf-8", errors="replace").splitlines():
        if line.lower().startswith("pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
    return -1


def _markdownify(raw: str) -> str:
    """Light cleanup: collapse runs of blank lines; trim trailing spaces.

    No paragraph reflow — Fatia 6.2 layout-aware. Goal here: editable in CaseHub.md
    without garbage characters.
    """
    lines = [line.rstrip() for line in raw.splitlines()]
    cleaned: list[str] = []
    blank = False
    for ln in lines:
        if not ln:
            if not blank:
                cleaned.append("")
            blank = True
        else:
            cleaned.append(ln)
            blank = False
    return "\n".join(cleaned).strip() + "\n"


def extract_text(
    file_path: str,
    content_type: str,
    *,
    lang: str = DEFAULT_LANG,
) -> OcrResult:
    """Extract markdown from a PDF or image file. See module docstring."""
    size = os.path.getsize(file_path)
    if size > MAX_BYTES:
        raise FileTooLarge(f"{size} bytes > {MAX_BYTES} bytes limit")

    start = time.monotonic()
    ct = (content_type or "").lower()
    is_pdf = ct == "application/pdf" or file_path.lower().endswith(".pdf")
    is_image = ct.startswith("image/") or file_path.lower().endswith(
        (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".webp", ".bmp")
    )

    if not (is_pdf or is_image):
        raise ValueError(f"unsupported content_type: {content_type}")

    if is_image:
        if not tesseract_available():
            raise OcrUnavailable("tesseract not found on PATH")
        text = _tesseract_image(file_path, lang)
        took_ms = int((time.monotonic() - start) * 1000)
        return OcrResult(
            markdown=_markdownify(text),
            source="tesseract",
            pages=1,
            took_ms=took_ms,
        )

    # PDF path
    if not poppler_available():
        raise OcrUnavailable("poppler (pdftotext/pdftoppm) not found on PATH")

    # Try digital text first.
    digital = _pdftotext(file_path)
    if len(digital.strip()) >= DIGITAL_TEXT_MIN_CHARS:
        took_ms = int((time.monotonic() - start) * 1000)
        return OcrResult(
            markdown=_markdownify(digital),
            source="pdftotext",
            pages=None,
            took_ms=took_ms,
        )

    if not tesseract_available():
        raise OcrUnavailable("tesseract not found on PATH (PDF needs OCR fallback)")

    pages = _count_pdf_pages(file_path)
    if pages > MAX_PAGES:
        raise TooManyPages(f"{pages} pages > {MAX_PAGES} limit")

    tmp_dir = tempfile.mkdtemp(prefix="casehub-md-ocr-")
    try:
        out_prefix = os.path.join(tmp_dir, "p")
        page_pngs = _pdftoppm(file_path, out_prefix)
        if not page_pngs:
            # pdftoppm produced nothing — degrade gracefully.
            return OcrResult(
                markdown="",
                source="tesseract-pdf",
                pages=0,
                took_ms=int((time.monotonic() - start) * 1000),
            )
        ocr_parts: list[str] = []
        for idx, png in enumerate(page_pngs, start=1):
            ocr_parts.append(_tesseract_image(png, lang))
            # Soft cap: keep cumulative wall-clock under ~30s for the request.
            if time.monotonic() - start > 28:
                logger.warning("OCR hit soft 28s cap at page %d/%d", idx, len(page_pngs))
                break
        text = "\n\n".join(part.strip() for part in ocr_parts if part.strip())
        took_ms = int((time.monotonic() - start) * 1000)
        return OcrResult(
            markdown=_markdownify(text),
            source="tesseract-pdf",
            pages=len(page_pngs),
            took_ms=took_ms,
        )
    finally:
        # Best-effort cleanup.
        for name in os.listdir(tmp_dir):
            try:
                os.remove(os.path.join(tmp_dir, name))
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass
