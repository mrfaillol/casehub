"""
CaseHub.md — Editor markdown WYSIWYG (TipTap)

Rotas isoladas sob /casehub-md/*. Branch paralela ao alpha (25/05).

Fatia 1 (2026-05-22): POC standalone, markdown round-trip via ESM CDN.
Próximas fatias: "folha" Google Docs, embeds, export DOCX, Drive sync, OCR, Maestro.

Documentação: docs/casehub-md/README.md
"""
from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from html import escape as html_escape

import os
import tempfile
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_current_user
from config import settings
from core.template_config import inject_org_context, templates
from models import get_db
from services.casehub_md.docx_export import (
    MarkdownTooLarge,
    PandocFailure,
    PandocUnavailable,
    convert_markdown_to_docx,
    get_template_path,
    pandoc_available,
)
from services.casehub_md.drive_sync import (
    DriveUnavailable,
    MarkdownTooLarge as DriveMarkdownTooLarge,
    default_sync,
)
from services.casehub_md.ocr_pdf import (
    FileTooLarge as OcrFileTooLarge,
    OcrUnavailable,
    TooManyPages,
    extract_text as ocr_extract_text,
    poppler_available,
    tesseract_available,
)
from services.casehub_md.maestro import (
    MaestroTimeout,
    MaestroUnavailable,
    ParagraphTooLarge,
    suggest as maestro_suggest,
)

logger = logging.getLogger(__name__)

PREFIX = settings.PREFIX

router = APIRouter(tags=["casehub-md"])


# Postel: aceita várias formas truthy para o toggle do ruler.
_TRUTHY = {"1", "true", "on", "yes", "y", "sim"}


def _ruler_on(request: Request) -> bool:
    """Whether the user opted into the horizontal ruler at the top of the sheet."""
    raw = (request.query_params.get("ruler") or "").strip().lower()
    return raw in _TRUTHY


@router.get("/casehub-md/poc", response_class=HTMLResponse)
async def casehub_md_poc(request: Request, db: Session = Depends(get_db)):
    """Fatia 1 — POC TipTap + Fatia 2 — folha Google Docs dentro do shell.

    Autenticação obrigatória (mesma do CaseHub). Sem persistência: editor
    vive no DOM, painel lateral espelha o markdown serializado em tempo real.
    Shell visual respeita design system Basic (data-theme="neuromorphic").

    Query params:
        ruler  — Postel-friendly truthy ("1", "true", "on", "yes"); default OFF.
    """
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Postel: aceita ?doc=, ?doc_id=, ?d= como sinônimos para o doc carregado on mount.
    initial_doc_id = (
        request.query_params.get("doc")
        or request.query_params.get("doc_id")
        or request.query_params.get("d")
        or ""
    ).strip()[:120]

    return templates.TemplateResponse(
        "app/casehub_md/index.html",
        {
            "request": request,
            "user": user,
            **inject_org_context(request, user),
            "PREFIX": PREFIX,
            "page_title": "CaseHub.md — Editor",
            "ruler_on": _ruler_on(request),
            "initial_doc_id": initial_doc_id,
            "active_module": "md",
        },
    )


# ---------------------------------------------------------------------------
# Fatia 4 — DOCX export (Pandoc backend)
# ---------------------------------------------------------------------------

class _DocxExportPayload(BaseModel):
    markdown: str = Field(..., description="Markdown source to convert to DOCX.")
    filename: Optional[str] = Field(
        None,
        max_length=120,
        description="Optional download filename (without .docx extension). "
                    "Default: casehub-md-<UTC-timestamp>.docx.",
    )
    template: Optional[str] = Field(
        None,
        max_length=24,
        description="Optional reference.docx template. Currently supported: 'oab'. "
                    "Default: Pandoc built-in (neutral typography).",
    )


def _safe_filename(name: Optional[str]) -> str:
    """Strip path separators / dangerous chars; cap length; ensure .docx suffix."""
    base = (name or "").strip()
    if not base:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
        base = f"casehub-md-{ts}"
    # Keep only safe ASCII basename chars — defense against header injection.
    cleaned = "".join(c for c in base if c.isalnum() or c in ("-", "_", "."))[:100]
    if not cleaned:
        cleaned = "casehub-md"
    if not cleaned.lower().endswith(".docx"):
        cleaned += ".docx"
    return cleaned


@router.post("/casehub-md/export/docx")
async def export_docx(
    request: Request,
    payload: _DocxExportPayload,
    db: Session = Depends(get_db),
):
    """Convert the given markdown to DOCX via Pandoc and stream as attachment.

    Auth-gated (cookie). 503 if Pandoc not installed on the VPS — operator
    must `apt install pandoc` on the host. 413 if markdown exceeds the
    server-side cap. 504 if Pandoc takes longer than the timeout.
    """
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="authentication required")

    if not pandoc_available():
        raise HTTPException(
            status_code=503,
            detail="pandoc-not-available",
        )

    try:
        result = convert_markdown_to_docx(
            payload.markdown,
            reference_docx=get_template_path(payload.template),
        )
    except MarkdownTooLarge as e:
        raise HTTPException(status_code=413, detail=str(e))
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="pandoc-timeout")
    except PandocUnavailable:
        # Race: pandoc was on PATH at startup but vanished mid-request.
        raise HTTPException(status_code=503, detail="pandoc-not-available")
    except PandocFailure as e:
        logger.exception("Pandoc DOCX export failed: %s", e)
        raise HTTPException(status_code=500, detail="pandoc-failed")

    filename = _safe_filename(payload.filename)
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-CaseHub-Md-Pandoc-Stderr-Bytes": str(len(result.pandoc_stderr_tail)),
    }
    return Response(
        content=result.data,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Fatia 5 — Drive sync
# ---------------------------------------------------------------------------

class _DriveSavePayload(BaseModel):
    doc_id: str = Field(..., min_length=1, max_length=120)
    markdown: str
    filename: Optional[str] = Field(None, max_length=120)


class _GoogleDocExportPayload(BaseModel):
    doc_id: str = Field(..., min_length=1, max_length=120)
    markdown: str
    html: Optional[str] = Field(None, max_length=4 * 1024 * 1024)
    filename: Optional[str] = Field(None, max_length=120)


def _require_user(request: Request, db: Session):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="authentication required")
    return user


@router.post("/casehub-md/drive/save")
async def drive_save(
    request: Request,
    payload: _DriveSavePayload,
    db: Session = Depends(get_db),
):
    """Create-or-update `<doc_id>` markdown file in `/CaseHubMD/` on Drive.

    503 if Drive is offline (no credentials/token). 413 if markdown exceeds
    the 4MB server cap. Otherwise 200 with file_id/drive_url/updated_at.
    """
    _require_user(request, db)
    sync = default_sync(org_id=request.state.org_id)
    if not sync.is_available():
        raise HTTPException(status_code=503, detail="drive-offline")
    try:
        result = sync.save_markdown(
            payload.doc_id,
            payload.markdown,
            filename=payload.filename,
        )
    except DriveMarkdownTooLarge as e:
        raise HTTPException(status_code=413, detail=str(e))
    except DriveUnavailable:
        raise HTTPException(status_code=503, detail="drive-offline")
    except Exception as e:  # noqa: BLE001 — surface unexpected Drive failures
        logger.exception("Drive save failed: %s", e)
        raise HTTPException(status_code=502, detail="drive-save-failed")

    return {
        "file_id": result.file_id,
        "drive_url": result.drive_url,
        "updated_at": result.updated_at,
        "was_created": result.was_created,
    }


@router.post("/casehub-md/drive/export-google-doc")
async def drive_export_google_doc(
    request: Request,
    payload: _GoogleDocExportPayload,
    db: Session = Depends(get_db),
):
    """Create-or-update an editable Google Docs copy for this CaseHub.md doc.

    This imports HTML into Drive as a native Google Docs document. It is
    auth-gated and returns 503 when Drive credentials/token are not available.
    """
    _require_user(request, db)
    sync = default_sync(org_id=request.state.org_id)
    if not sync.is_available():
        raise HTTPException(status_code=503, detail="drive-offline")

    html_body = (payload.html or "").strip()
    if not html_body:
        html_body = "<pre>" + html_escape(payload.markdown or "") + "</pre>"
    html_doc = (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<title>" + html_escape(payload.filename or "CaseHub.md") + "</title>"
        "</head><body>" + html_body + "</body></html>"
    )

    try:
        result = sync.save_google_doc(
            payload.doc_id,
            html_doc,
            filename=payload.filename,
        )
    except DriveMarkdownTooLarge as e:
        raise HTTPException(status_code=413, detail=str(e))
    except DriveUnavailable:
        raise HTTPException(status_code=503, detail="drive-offline")
    except Exception as e:  # noqa: BLE001
        logger.exception("Google Docs export failed: %s", e)
        raise HTTPException(status_code=502, detail="google-doc-export-failed")

    return {
        "file_id": result.file_id,
        "google_doc_url": result.drive_url,
        "updated_at": result.updated_at,
        "was_created": result.was_created,
    }


@router.get("/casehub-md/drive/list")
async def drive_list(request: Request, db: Session = Depends(get_db)):
    """List the 100 most-recently-modified docs in /CaseHubMD/."""
    _require_user(request, db)
    sync = default_sync(org_id=request.state.org_id)
    if not sync.is_available():
        return {"items": [], "unavailable": True, "detail": "drive-offline"}
    try:
        items = sync.list_recent(limit=100)
    except DriveUnavailable:
        return {"items": [], "unavailable": True, "detail": "drive-offline"}
    except Exception as e:  # noqa: BLE001
        logger.exception("Drive list failed: %s", e)
        raise HTTPException(status_code=502, detail="drive-list-failed")
    return {
        "items": [
            {
                "doc_id": d.doc_id,
                "file_id": d.file_id,
                "filename": d.filename,
                "updated_at": d.updated_at,
            }
            for d in items
        ]
    }


@router.get("/casehub-md/drive/{doc_id}")
async def drive_load(request: Request, doc_id: str, db: Session = Depends(get_db)):
    """Fetch markdown content for `doc_id`, or 404 if not found."""
    _require_user(request, db)
    if not doc_id or len(doc_id) > 120:
        raise HTTPException(status_code=400, detail="invalid doc_id")
    sync = default_sync(org_id=request.state.org_id)
    if not sync.is_available():
        raise HTTPException(status_code=503, detail="drive-offline")
    try:
        result = sync.load_markdown(doc_id)
    except DriveUnavailable:
        raise HTTPException(status_code=503, detail="drive-offline")
    except Exception as e:  # noqa: BLE001
        logger.exception("Drive load failed: %s", e)
        raise HTTPException(status_code=502, detail="drive-load-failed")

    if result is None:
        raise HTTPException(status_code=404, detail="doc-not-found")
    return {
        "doc_id": doc_id,
        "file_id": result.file_id,
        "updated_at": result.updated_at,
        "markdown": result.markdown,
    }


# ---------------------------------------------------------------------------
# Fatia 6 — PDF/image OCR via Tesseract + Poppler
# ---------------------------------------------------------------------------

_SUPPORTED_OCR_TYPES = (
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/tiff",
    "image/webp",
    "image/bmp",
)


@router.post("/casehub-md/ocr")
async def ocr_extract(
    request: Request,
    file: UploadFile = File(...),
    lang: str = Query("por+eng", max_length=40),
    db: Session = Depends(get_db),
):
    """Run OCR over a PDF or image and return extracted markdown.

    Hybrid PDF heuristic: tries pdftotext first; falls back to pdftoppm+tesseract
    when the text layer is empty/short. 503 if the underlying binaries are missing.
    """
    _require_user(request, db)
    ct = (file.content_type or "").lower()
    if ct not in _SUPPORTED_OCR_TYPES and not (ct.startswith("image/") and ct != "image/svg+xml"):
        raise HTTPException(status_code=415, detail=f"unsupported content type: {ct}")

    # Lang allow-list (avoid passing arbitrary user input to tesseract -l).
    if not all(part.isalpha() for part in lang.replace("+", "").split() if part):
        raise HTTPException(status_code=400, detail="invalid lang")

    if not tesseract_available() and not (ct == "application/pdf" and poppler_available()):
        # Neither binary present — endpoint is offline.
        raise HTTPException(status_code=503, detail="ocr-unavailable")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename or "")[1])
    try:
        try:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                tmp.write(chunk)
        finally:
            tmp.close()

        try:
            result = ocr_extract_text(tmp.name, ct, lang=lang)
        except OcrFileTooLarge as e:
            raise HTTPException(status_code=413, detail=str(e))
        except TooManyPages as e:
            raise HTTPException(status_code=422, detail=str(e))
        except OcrUnavailable:
            raise HTTPException(status_code=503, detail="ocr-unavailable")
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="ocr-timeout")
        except ValueError as e:
            raise HTTPException(status_code=415, detail=str(e))
        except Exception as e:  # noqa: BLE001
            logger.exception("OCR extract failed: %s", e)
            raise HTTPException(status_code=500, detail="ocr-failed")

        return {
            "markdown": result.markdown,
            "source": result.source,
            "pages": result.pages,
            "took_ms": result.took_ms,
        }
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Fatia 7 — Maestro AI bridge
# ---------------------------------------------------------------------------

class _MaestroPayload(BaseModel):
    paragraph: str = Field(..., min_length=1, max_length=16_384)
    case_id: Optional[str] = Field(None, max_length=120)
    kind: str = Field("suggest_continuation", max_length=64)


@router.post("/casehub-md/maestro/suggest")
async def maestro_suggest_endpoint(
    request: Request,
    payload: _MaestroPayload,
    db: Session = Depends(get_db),
):
    """Proxy the user's paragraph to the Maestro backend and return a suggestion.

    503 if Maestro is unreachable (still in development). 504 if it times out.
    Postel-friendly: accepts paragraph trailing whitespace / case_id case-sensitive.
    """
    _require_user(request, db)
    try:
        result = await maestro_suggest(
            payload.paragraph,
            case_id=payload.case_id,
            kind=payload.kind,
        )
    except ParagraphTooLarge as e:
        raise HTTPException(status_code=413, detail=str(e))
    except MaestroTimeout:
        raise HTTPException(status_code=504, detail="maestro-timeout")
    except MaestroUnavailable as e:
        raise HTTPException(status_code=503, detail=f"maestro-unavailable: {e}")
    except Exception as e:  # noqa: BLE001
        logger.exception("Maestro suggest failed: %s", e)
        raise HTTPException(status_code=502, detail="maestro-proxy-failed")

    return {
        "suggestion": result.suggestion,
        "model": result.model,
        "took_ms": result.took_ms,
    }
