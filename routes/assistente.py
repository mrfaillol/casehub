"""
CaseHub Lite — Maestro Lite (Maestro IA)
Chatbot local via Ollama com contexto do escritório.

Routes:
    GET  /assistente                        — Chat UI
    POST /assistente/api/chat               — Enviar mensagem (JSON)
    GET  /assistente/config                 — Página de configuração (admin)
    POST /assistente/config/contexto        — Salvar contexto customizado
    GET  /assistente/api/status             — Status do Ollama (JSON)
    POST /assistente/config/upload-fonte    — Upload knowledge source
    DELETE /assistente/config/fonte/{id}    — Remove knowledge source
    GET  /assistente/config/fontes          — List knowledge sources (JSON)
    POST /assistente/config/sincronizar     — Sync firm context from DB
    GET  /assistente/config/historico       — Chat history (JSON)
    DELETE /assistente/config/historico     — Clear chat history
    POST /assistente/config/personalidade   — Save personality config
    GET  /assistente/config/personalidade   — Get personality config (JSON)
    GET  /assistente/config/analytics       — Chat analytics (JSON)
"""
from fastapi import APIRouter, Depends, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging
import json
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

from core.template_config import templates, PREFIX, inject_org_context
from auth import get_current_user
from models import get_db
from services.maestro_lite import MaestroLite

# Soft import — MaestroLearningEntry ships in PR #575. If that PR hasn't
# merged yet (e.g. fresh checkout off main pre-merge), the chat falls
# back to "no user corpus" silently rather than crashing on import.
try:
    from models import MaestroLearningEntry  # noqa: WPS433
except ImportError:
    MaestroLearningEntry = None  # type: ignore[assignment]

router = APIRouter(prefix="/assistente", tags=["assistente"])

# Sentinela T11: ai_sources now live under uploads/org_<id>/ai_sources/.
# Legacy flat dir kept as read-fallback in the auth-gated /uploads route.
UPLOADS_BASE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
UPLOAD_DIR = os.path.join(UPLOADS_BASE, "ai_sources")


def _ai_sources_dir(org_id) -> str:
    if org_id is None:
        return UPLOAD_DIR
    return os.path.join(UPLOADS_BASE, f"org_{org_id}", "ai_sources")


def _get_maestro(request: Request) -> MaestroLite:
    """Create MaestroLite instance with org name."""
    org_ctx = inject_org_context(request)
    org_name = org_ctx.get("org_name", "CaseHub")
    return MaestroLite(org_name=org_name)


# Per-entry size cap when assembling the chat context. Keeps any single
# learning entry from monopolising the system prompt and lets the chat
# tokenize the rest of the firm context. Mirrors MAX_CONTENT_BYTES from
# routes/maestro_learn.py (16 KiB on write) but is more conservative at
# 4 KiB on read — large entries are summarised by truncation; the user
# still sees the full content in the learning surface.
_MAX_ENTRY_BYTES_FOR_CHAT_CTX = 4 * 1024
# Cap total entries pulled into one chat call. Even with 200 entries per
# user (the write cap), pulling them all on every chat request would burn
# the token budget. The chat surface gets the most-recently-touched 20 —
# good enough for working memory; the rest sit in the corpus surface.
_MAX_ENTRIES_FOR_CHAT_CTX = 20


def _maestro_learning_enabled() -> bool:
    """Mirror of routes.maestro_learn._feature_enabled — same flag.

    Duplicated (rather than imported) on purpose: keeps this module
    importable even if routes.maestro_learn fails to load for any
    reason, and keeps the chat flow's flag check inlined here for the
    next reader of this file.
    """
    raw = os.getenv("CASEHUB_MAESTRO_LEARNING_ENABLED")
    if raw is None:
        try:
            from config import settings as _settings
            raw = getattr(_settings, "CASEHUB_MAESTRO_LEARNING_ENABLED", "")
        except Exception:  # noqa: BLE001 — keep the chat alive even if config broken
            raw = ""
    return (raw or "").lower() in {"1", "true", "yes", "on"}


def _get_user_learning_context(db: Session, org_id, user) -> str:
    """Assemble the user's enabled Maestro learning corpus for the chat.

    Gated by ``CASEHUB_MAESTRO_LEARNING_ENABLED`` (default OFF — matches
    docs/casehub-alpha/primeiros-passos.md). Returns an empty string
    when the flag is off, the model is absent (PR #575 not merged
    yet), the user is anonymous, or the query fails — the chat should
    never break on a learning-corpus issue.

    The block is appended as a labelled section of the system context
    so the assistant treats it as "user-authored notes" rather than
    firm-canonical knowledge — matters when entries contradict the
    firm context.
    """
    if not _maestro_learning_enabled():
        return ""
    if MaestroLearningEntry is None:
        return ""
    user_id = getattr(user, "id", None)
    if not user_id:
        return ""

    try:
        entries = (
            db.query(MaestroLearningEntry)
            .filter(
                MaestroLearningEntry.user_id == user_id,
                MaestroLearningEntry.org_id == org_id,
                MaestroLearningEntry.enabled.is_(True),
            )
            .order_by(MaestroLearningEntry.updated_at.desc())
            .limit(_MAX_ENTRIES_FOR_CHAT_CTX)
            .all()
        )
    except Exception as exc:  # noqa: BLE001 — degrade silently
        logger.warning(
            "[MAESTRO LEARN CTX] failed to load entries for user_id=%s: %s",
            user_id, exc,
        )
        try:
            db.rollback()
        except Exception:
            pass
        return ""

    if not entries:
        return ""

    formatted_blocks = []
    for entry in entries:
        title = (entry.title or "Sem título").strip()
        content = (entry.content or "")[:_MAX_ENTRY_BYTES_FOR_CHAT_CTX]
        tags = ", ".join(entry.tags or []) if entry.tags else ""
        header = f"### {title}"
        if tags:
            header += f"  _(tags: {tags})_"
        formatted_blocks.append(f"{header}\n{content}")

    body = "\n\n".join(formatted_blocks)
    return (
        "\n\nAnotações do usuário (Maestro learning — fonte autoral, "
        "use como preferência mas valide contra o contexto do "
        "escritório quando houver conflito):\n" + body
    )


def _get_custom_context(db: Session, org_id) -> str:
    """Get custom context text from org settings."""
    try:
        result = db.execute(
            text("SELECT value FROM org_settings WHERE org_id = :oid AND key = 'maestro_context'"),
            {"oid": org_id}
        )
        row = result.fetchone()
        if row:
            return row[0]
    except Exception:
        pass
    return ""


def _is_maestro_enabled(db: Session, org_id) -> bool:
    """Check if Maestro is enabled for this org."""
    try:
        result = db.execute(
            text("SELECT value FROM org_settings WHERE org_id = :oid AND key = 'maestro_enabled'"),
            {"oid": org_id}
        )
        row = result.fetchone()
        if row:
            return row[0].lower() in ("true", "1", "yes")
    except Exception:
        pass
    return True  # Enabled by default


def _get_personality(db: Session, org_id) -> dict:
    """Get personality/system prompt config from org settings."""
    try:
        result = db.execute(
            text("SELECT value FROM org_settings WHERE org_id = :oid AND key = 'maestro_personality'"),
            {"oid": org_id}
        )
        row = result.fetchone()
        if row:
            return json.loads(row[0])
    except Exception:
        pass
    return {}


def _extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """Extract text content from uploaded file."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "txt":
        return file_bytes.decode("utf-8", errors="replace")

    if ext == "pdf":
        # Basic PDF text extraction
        try:
            import io
            # Try PyPDF2 first
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(io.BytesIO(file_bytes))
                text_parts = []
                for page in reader.pages:
                    t = page.extract_text()
                    if t:
                        text_parts.append(t)
                return "\n".join(text_parts)
            except ImportError:
                pass
            # Fallback: try pdfminer
            try:
                from pdfminer.high_level import extract_text as pdf_extract
                return pdf_extract(io.BytesIO(file_bytes))
            except ImportError:
                pass
            return "[PDF importado - instale PyPDF2 para extração de texto]"
        except Exception as e:
            logger.error("PDF extraction error: %s", e)
            return f"[Erro ao extrair texto do PDF: {e}]"

    if ext == "docx":
        try:
            import io
            from docx import Document
            doc = Document(io.BytesIO(file_bytes))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            return "[DOCX importado - instale python-docx para extração de texto]"
        except Exception as e:
            logger.error("DOCX extraction error: %s", e)
            return f"[Erro ao extrair texto do DOCX: {e}]"

    return file_bytes.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Chat UI
# ---------------------------------------------------------------------------
@router.get("", response_class=HTMLResponse)
async def chat_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_ctx = inject_org_context(request)
    maestro = _get_maestro(request)
    status = await maestro.get_status()

    # Embed mode: minimal standalone chat without sidebar/topbar
    embed = request.query_params.get("embed") == "1"
    template_name = "assistente/chat_embed.html" if embed else "assistente/chat.html"

    return templates.TemplateResponse(template_name, {
        "request": request,
        "PREFIX": PREFIX,
        "user": user,
        "ollama_status": status,
        **org_ctx,
    })


# ---------------------------------------------------------------------------
# Chat API (with history saving)
# ---------------------------------------------------------------------------
@router.post("/api/chat")
async def chat_api(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Não autenticado")

    org_id = getattr(request.state, "org_id", None)

    if not _is_maestro_enabled(db, org_id):
        return JSONResponse({"response": "O assistente está desativado.", "status": "disabled"})

    data = await request.json()
    message = data.get("message", "").strip()
    history = data.get("history", [])

    if not message:
        return JSONResponse({"response": "Mensagem vazia.", "status": "error"})

    maestro = _get_maestro(request)

    # Check for custom personality/system prompt
    personality = _get_personality(db, org_id)
    if personality.get("system_prompt"):
        maestro.system_prompt = personality["system_prompt"]

    # Build context from knowledge sources
    sources_context = ""
    try:
        result = db.execute(
            text("SELECT content FROM ai_knowledge_sources WHERE org_id = :oid AND content IS NOT NULL"),
            {"oid": org_id}
        )
        source_texts = [row[0] for row in result if row[0]]
        if source_texts:
            # Truncate each source to avoid exceeding context window
            truncated = [s[:2000] for s in source_texts]
            sources_context = "\n\nFontes de conhecimento:\n" + "\n---\n".join(truncated)
    except Exception as e:
        logger.warning("Error loading knowledge sources: %s", e)

    # Build context (org-scoped firm data — get_firm_context filters by org_id)
    firm_context = maestro.get_firm_context(db, org_id)
    custom_context = _get_custom_context(db, org_id)
    user_learning_context = _get_user_learning_context(db, org_id, user)
    full_context = firm_context
    if custom_context:
        full_context += f"\n\nInformações adicionais do escritório:\n{custom_context}"
    if sources_context:
        full_context += sources_context
    if user_learning_context:
        full_context += user_learning_context

    # Repo-aware product grounding (flagged OFF by default). The repo index holds
    # CaseHub product code/docs — identical for every tenant, contains no tenant
    # data or secrets — so it is NOT org-scoped. Retrieval is local (Ollama
    # nomic-embed-text); a missing index / offline embed simply yields None and
    # the chat proceeds with firm context only.
    repo_context = None
    try:
        from services.maestro_lite import repo_aware_enabled
        if repo_aware_enabled():
            from services.maestro_repo_index import retrieve_repo_context
            repo_context = retrieve_repo_context(message)
    except Exception as e:  # noqa: BLE001 — grounding is best-effort, never fatal
        logger.warning("repo-aware retrieval failed (non-fatal): %s", e)

    result = await maestro.chat(message, context=full_context, history=history,
                                repo_context=repo_context)

    # Save to ai_chat_history
    try:
        tokens = result.get("tokens_used", 0)
        model = result.get("model", "")
        response_text = result.get("response", "")
        db.execute(text("""
            INSERT INTO ai_chat_history (org_id, user_id, message, response, tokens_used, model)
            VALUES (:org_id, :user_id, :message, :response, :tokens, :model)
        """), {
            "org_id": org_id,
            "user_id": getattr(user, "id", None),
            "message": message,
            "response": response_text,
            "tokens": tokens,
            "model": model,
        })
        db.commit()
    except Exception as e:
        logger.warning("Error saving chat history: %s", e)
        try:
            db.rollback()
        except Exception:
            pass

    return JSONResponse(result)


# ---------------------------------------------------------------------------
# Status API
# ---------------------------------------------------------------------------
@router.get("/api/status")
async def status_api(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Não autenticado")

    maestro = _get_maestro(request)
    status = await maestro.get_status()
    return JSONResponse(status)


# ---------------------------------------------------------------------------
# Config Page (Admin only)
# ---------------------------------------------------------------------------
@router.get("/config", response_class=HTMLResponse)
async def config_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    if user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")

    org_id = getattr(request.state, "org_id", None)
    org_ctx = inject_org_context(request)
    maestro = _get_maestro(request)
    status = await maestro.get_status()
    custom_context = _get_custom_context(db, org_id)
    enabled = _is_maestro_enabled(db, org_id)
    personality = _get_personality(db, org_id)

    # Get sources count
    sources_count = 0
    try:
        result = db.execute(
            text("SELECT COUNT(*) FROM ai_knowledge_sources WHERE org_id = :oid"),
            {"oid": org_id}
        )
        sources_count = result.scalar() or 0
    except Exception:
        pass

    # Get today's token count
    tokens_today = 0
    try:
        result = db.execute(
            text("SELECT COALESCE(SUM(tokens_used), 0) FROM ai_chat_history WHERE org_id = :oid AND created_at >= CURRENT_DATE"),
            {"oid": org_id}
        )
        tokens_today = result.scalar() or 0
    except Exception:
        pass

    return templates.TemplateResponse("app/assistente/config.html", {
        "request": request,
        "PREFIX": PREFIX,
        "user": user,
        "ollama_status": status,
        "custom_context": custom_context,
        "maestro_enabled": enabled,
        "personality": personality,
        "sources_count": sources_count,
        "tokens_today": tokens_today,
        **org_ctx,
    })


# ---------------------------------------------------------------------------
# Save Custom Context
# ---------------------------------------------------------------------------
@router.post("/config/contexto")
async def save_context(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito")

    org_id = getattr(request.state, "org_id", None)
    data = await request.json()
    context_text = data.get("contexto", "")
    enabled = data.get("enabled", True)

    try:
        # Upsert context
        db.execute(text("""
            INSERT INTO org_settings (org_id, key, value)
            VALUES (:oid, 'maestro_context', :val)
            ON CONFLICT (org_id, key) DO UPDATE SET value = :val
        """), {"oid": org_id, "val": context_text})

        # Upsert enabled
        db.execute(text("""
            INSERT INTO org_settings (org_id, key, value)
            VALUES (:oid, 'maestro_enabled', :enabled)
            ON CONFLICT (org_id, key) DO UPDATE SET value = :enabled
        """), {"oid": org_id, "enabled": str(enabled).lower()})

        db.commit()
        return JSONResponse({"success": True, "message": "Configurações salvas"})
    except Exception as e:
        logger.error("Error saving maestro config: %s", e)
        db.rollback()
        return JSONResponse({"success": False, "message": f"Erro: {e}"}, status_code=500)


# ---------------------------------------------------------------------------
# Upload Knowledge Source
# ---------------------------------------------------------------------------
@router.post("/config/upload-fonte")
async def upload_source(
    request: Request,
    file: UploadFile = File(None),
    name: str = Form(None),
    content: str = Form(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito")

    org_id = getattr(request.state, "org_id", None)

    try:
        if file and file.filename:
            # File upload
            file_bytes = await file.read()
            file_size = len(file_bytes)
            filename = file.filename
            source_name = name or filename

            # Extract text
            extracted = _extract_text_from_file(file_bytes, filename)

            # Save file to disk (Sentinela T11: per-tenant subdirectory).
            ai_dir = _ai_sources_dir(org_id)
            os.makedirs(ai_dir, exist_ok=True)
            safe_name = f"{org_id}_{int(datetime.now().timestamp())}_{filename}"
            save_path = os.path.join(ai_dir, safe_name)
            with open(save_path, "wb") as f:
                f.write(file_bytes)

            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
            source_type = ext if ext in ("pdf", "txt", "docx") else "file"

            db.execute(text("""
                INSERT INTO ai_knowledge_sources (org_id, name, source_type, content, file_path, file_size, indexed)
                VALUES (:org_id, :name, :stype, :content, :fpath, :fsize, TRUE)
            """), {
                "org_id": org_id,
                "name": source_name,
                "stype": source_type,
                "content": extracted,
                "fpath": save_path,
                "fsize": file_size,
            })
            db.commit()
            return JSONResponse({"success": True, "message": f"Fonte '{source_name}' adicionada"})

        elif content:
            # Manual text source
            source_name = name or "Texto manual"
            db.execute(text("""
                INSERT INTO ai_knowledge_sources (org_id, name, source_type, content, file_size, indexed)
                VALUES (:org_id, :name, 'manual', :content, :fsize, TRUE)
            """), {
                "org_id": org_id,
                "name": source_name,
                "content": content,
                "fsize": len(content.encode("utf-8")),
            })
            db.commit()
            return JSONResponse({"success": True, "message": f"Fonte '{source_name}' adicionada"})

        else:
            return JSONResponse({"success": False, "message": "Nenhum arquivo ou texto fornecido"}, status_code=400)

    except Exception as e:
        logger.error("Error uploading source: %s", e)
        db.rollback()
        return JSONResponse({"success": False, "message": f"Erro: {e}"}, status_code=500)


# ---------------------------------------------------------------------------
# List Knowledge Sources
# ---------------------------------------------------------------------------
@router.get("/config/fontes")
async def list_sources(request: Request, db: Session = Depends(get_db)):
    # NOTE (403 fix 2026-05-29): the chat sidebar (templates/.../assistente/chat.html
    # → loadFontes()) is served to EVERY authenticated user, not just admins, and
    # calls this endpoint on page load. Requiring user_type == "admin" here made
    # non-admin firm staff get a 403 in the console on every chat open. Listing the
    # org's own knowledge-source names/previews to an authenticated member of that
    # org is a read scoped by org_id (WHERE org_id = :oid below) — not a privilege
    # escalation — so this is auth-only. Write/delete/config endpoints below stay
    # admin-gated. Org isolation is unchanged (every query filters by org_id).
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Não autenticado")

    org_id = getattr(request.state, "org_id", None)

    try:
        result = db.execute(text("""
            SELECT id, name, source_type, file_size, chunks_count, indexed,
                   created_at, LEFT(content, 200) as preview
            FROM ai_knowledge_sources
            WHERE org_id = :oid
            ORDER BY created_at DESC
        """), {"oid": org_id})
        sources = []
        for row in result:
            sources.append({
                "id": row[0],
                "name": row[1],
                "source_type": row[2],
                "file_size": row[3],
                "chunks_count": row[4],
                "indexed": row[5],
                "created_at": row[6].isoformat() if row[6] else None,
                "preview": row[7] or "",
            })
        return JSONResponse({"sources": sources})
    except Exception as e:
        logger.error("Error listing sources: %s", e)
        return JSONResponse({"sources": [], "error": str(e)})


# ---------------------------------------------------------------------------
# Delete Knowledge Source
# ---------------------------------------------------------------------------
@router.delete("/config/fonte/{source_id}")
async def delete_source(source_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito")

    org_id = getattr(request.state, "org_id", None)

    try:
        # Get file path before deleting
        result = db.execute(text(
            "SELECT file_path FROM ai_knowledge_sources WHERE id = :sid AND org_id = :oid"
        ), {"sid": source_id, "oid": org_id})
        row = result.fetchone()

        if not row:
            return JSONResponse({"success": False, "message": "Fonte não encontrada"}, status_code=404)

        # Delete file from disk if exists
        if row[0] and os.path.exists(row[0]):
            try:
                os.remove(row[0])
            except Exception:
                pass

        db.execute(text(
            "DELETE FROM ai_knowledge_sources WHERE id = :sid AND org_id = :oid"
        ), {"sid": source_id, "oid": org_id})
        db.commit()
        return JSONResponse({"success": True, "message": "Fonte removida"})
    except Exception as e:
        logger.error("Error deleting source: %s", e)
        db.rollback()
        return JSONResponse({"success": False, "message": f"Erro: {e}"}, status_code=500)


# ---------------------------------------------------------------------------
# Sync Firm Context (auto-generate source from DB)
# ---------------------------------------------------------------------------
@router.post("/config/sincronizar")
async def sync_context(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito")

    org_id = getattr(request.state, "org_id", None)

    try:
        stats = {}
        context_parts = []

        # Clients
        try:
            r = db.execute(text("SELECT COUNT(*) FROM clients WHERE org_id = :oid"), {"oid": org_id})
            stats["clientes"] = r.scalar() or 0
            context_parts.append(f"Total de clientes cadastrados: {stats['clientes']}")
        except Exception:
            stats["clientes"] = 0

        # Cases
        try:
            r = db.execute(text("SELECT COUNT(*) FROM cases WHERE org_id = :oid"), {"oid": org_id})
            total = r.scalar() or 0
            r2 = db.execute(text("SELECT COUNT(*) FROM cases WHERE org_id = :oid AND status = 'active'"), {"oid": org_id})
            active = r2.scalar() or 0
            stats["processos"] = total
            stats["processos_ativos"] = active
            context_parts.append(f"Total de processos: {total} ({active} ativos)")
        except Exception:
            stats["processos"] = 0
            stats["processos_ativos"] = 0

        # Prazos
        try:
            r = db.execute(text("SELECT COUNT(*) FROM prazos_processuais WHERE org_id = :oid AND status = 'pendente'"), {"oid": org_id})
            stats["prazos"] = r.scalar() or 0
            context_parts.append(f"Prazos pendentes: {stats['prazos']}")
        except Exception:
            stats["prazos"] = 0

        # Tasks
        try:
            r = db.execute(text("SELECT COUNT(*) FROM tasks WHERE org_id = :oid AND status != 'completed'"), {"oid": org_id})
            stats["tarefas"] = r.scalar() or 0
            context_parts.append(f"Tarefas pendentes: {stats['tarefas']}")
        except Exception:
            stats["tarefas"] = 0

        # Documents
        try:
            r = db.execute(text("SELECT COUNT(*) FROM documents WHERE org_id = :oid"), {"oid": org_id})
            stats["documentos"] = r.scalar() or 0
            context_parts.append(f"Documentos: {stats['documentos']}")
        except Exception:
            stats["documentos"] = 0

        summary = f"Contexto do escritório (sincronizado em {datetime.now().strftime('%d/%m/%Y %H:%M')}):\n" + "\n".join(context_parts)

        # Upsert auto_sync source
        db.execute(text("""
            DELETE FROM ai_knowledge_sources WHERE org_id = :oid AND source_type = 'auto_sync'
        """), {"oid": org_id})
        db.execute(text("""
            INSERT INTO ai_knowledge_sources (org_id, name, source_type, content, file_size, indexed)
            VALUES (:oid, 'Contexto do Escritório (Auto)', 'auto_sync', :content, :fsize, TRUE)
        """), {
            "oid": org_id,
            "content": summary,
            "fsize": len(summary.encode("utf-8")),
        })
        db.commit()

        return JSONResponse({
            "success": True,
            "stats": stats,
            "synced_at": datetime.now().isoformat(),
            "message": "Contexto sincronizado com sucesso"
        })
    except Exception as e:
        logger.error("Error syncing context: %s", e)
        db.rollback()
        return JSONResponse({"success": False, "message": f"Erro: {e}"}, status_code=500)


# ---------------------------------------------------------------------------
# Chat History
# ---------------------------------------------------------------------------
@router.get("/config/historico")
async def get_history(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito")

    org_id = getattr(request.state, "org_id", None)
    page = int(request.query_params.get("page", 1))
    limit = 50
    offset = (page - 1) * limit

    try:
        result = db.execute(text("""
            SELECT id, user_id, message, response, tokens_used, model, created_at
            FROM ai_chat_history
            WHERE org_id = :oid
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """), {"oid": org_id, "limit": limit, "offset": offset})

        history = []
        for row in result:
            history.append({
                "id": row[0],
                "user_id": row[1],
                "message": row[2],
                "response": row[3],
                "tokens_used": row[4],
                "model": row[5],
                "created_at": row[6].isoformat() if row[6] else None,
            })

        # Total count
        count_result = db.execute(text(
            "SELECT COUNT(*) FROM ai_chat_history WHERE org_id = :oid"
        ), {"oid": org_id})
        total = count_result.scalar() or 0

        return JSONResponse({"history": history, "total": total, "page": page})
    except Exception as e:
        logger.error("Error getting history: %s", e)
        return JSONResponse({"history": [], "total": 0, "error": str(e)})


@router.delete("/config/historico")
async def clear_history(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito")

    org_id = getattr(request.state, "org_id", None)

    try:
        db.execute(text("DELETE FROM ai_chat_history WHERE org_id = :oid"), {"oid": org_id})
        db.commit()
        return JSONResponse({"success": True, "message": "Histórico limpo"})
    except Exception as e:
        logger.error("Error clearing history: %s", e)
        db.rollback()
        return JSONResponse({"success": False, "message": f"Erro: {e}"}, status_code=500)


# ---------------------------------------------------------------------------
# Save Personality Config
# ---------------------------------------------------------------------------
@router.post("/config/personalidade")
async def save_personality(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito")

    org_id = getattr(request.state, "org_id", None)
    data = await request.json()

    personality = {
        "system_prompt": data.get("system_prompt", ""),
        "cite_laws": data.get("cite_laws", False),
        "include_reasoning": data.get("include_reasoning", False),
        "ask_clarification": data.get("ask_clarification", True),
        "suggest_next_steps": data.get("suggest_next_steps", True),
    }

    try:
        db.execute(text("""
            INSERT INTO org_settings (org_id, key, value)
            VALUES (:oid, 'maestro_personality', :val)
            ON CONFLICT (org_id, key) DO UPDATE SET value = :val
        """), {"oid": org_id, "val": json.dumps(personality)})
        db.commit()
        return JSONResponse({"success": True, "message": "Personalidade salva"})
    except Exception as e:
        logger.error("Error saving personality: %s", e)
        db.rollback()
        return JSONResponse({"success": False, "message": f"Erro: {e}"}, status_code=500)


@router.get("/config/personalidade")
async def get_personality_api(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito")

    org_id = getattr(request.state, "org_id", None)
    personality = _get_personality(db, org_id)
    return JSONResponse(personality)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
@router.get("/config/analytics")
async def analytics_api(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito")

    org_id = getattr(request.state, "org_id", None)

    try:
        # Messages per day (last 7 days)
        daily = []
        for i in range(6, -1, -1):
            day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            result = db.execute(text("""
                SELECT COUNT(*), COALESCE(SUM(tokens_used), 0)
                FROM ai_chat_history
                WHERE org_id = :oid AND created_at::date = :day
            """), {"oid": org_id, "day": day})
            row = result.fetchone()
            daily.append({
                "date": day,
                "count": row[0] if row else 0,
                "tokens": row[1] if row else 0,
            })

        # Totals
        result = db.execute(text("""
            SELECT COUNT(*), COALESCE(SUM(tokens_used), 0)
            FROM ai_chat_history WHERE org_id = :oid
        """), {"oid": org_id})
        totals = result.fetchone()

        return JSONResponse({
            "daily": daily,
            "total_conversations": totals[0] if totals else 0,
            "total_tokens": totals[1] if totals else 0,
        })
    except Exception as e:
        logger.error("Error getting analytics: %s", e)
        return JSONResponse({"daily": [], "total_conversations": 0, "total_tokens": 0, "error": str(e)})
