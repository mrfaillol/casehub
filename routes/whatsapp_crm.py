"""
CaseHub - WhatsApp Web Clone: Tier-3 power-features (CRM / AI assist / pipeline).

Workstream WS-D. This router is the "Chrome-extension layer" of the WhatsApp Web
clone: it adds CRM linking, a lead pipeline/funnel, ephemeral AI assist and
quick-reply templates ON TOP of the chat clone served by routes/whatsapp_chat.py.

Routing / prefix
----------------
This router MUST share the SAME prefix as routes/whatsapp_chat.py so that
static/js/chat.js (and static/js/whatsapp-crm.js) reach it via the single
WA_API_BASE = PREFIX + <page-router-prefix>:

  * flag CASEHUB_WHATSAPP_CLONE_ENABLED ON  -> prefix is "/whatsapp"
  * flag OFF (default)                      -> prefix is "/whatsapp-chat"

The flag logic is read with os.getenv (config.py is owned by another workstream)
and replicates whatsapp_chat.whatsapp_clone_enabled() exactly.

Path discipline (no collisions with whatsapp_chat.py)
-----------------------------------------------------
whatsapp_chat.py already owns: /api/conversations, /api/messages/{phone},
/api/send, /api/bot-control, /api/suggest-response, /api/leads, /api/lead/{phone},
/api/followup/*, /api/status, /api/qr, /api/events/*, etc.

THIS router only adds NEW paths under the shared prefix:

  Page fragments (loaded by whatsapp-crm.js, so chat.html is never edited):
    GET  /crm/contact-panel/{phone}   -> _contact_panel.html fragment
    GET  /crm/pipeline                -> _pipeline.html fragment (kanban)

  CRM:
    GET  /api/crm/contact/{phone}     -> contact CRM card (client/case link, tags, stage)
    POST /api/crm/link/{phone}        -> link/unlink a Client / Case
    POST /api/crm/tags/{phone}        -> set wa_contacts.tags
    POST /api/crm/stage/{phone}       -> set wa_contacts.lead_stage
    GET  /api/crm/clients             -> client picker (search)
    GET  /api/crm/cases/{client_id}   -> case picker for a client

  Pipeline / funnel:
    GET  /api/crm/pipeline            -> conversations grouped by lead_stage
    POST /api/crm/pipeline/move       -> move a contact between stages

  AI assist (EPHEMERAL — see the ephemerality guarantee below):
    POST /api/crm/ai/suggest          -> live response suggestion
    POST /api/crm/ai/summary          -> live conversation summary
    POST /api/crm/ai/draft            -> live draft from an instruction

  Quick-reply templates (ported from the 30+ legacy agent-templates.js):
    GET  /api/crm/templates           -> list quick-reply templates (lang-aware)
    GET  /api/crm/template/{tid}      -> one template, personalized for a contact

  The 3 endpoints chat.js currently 404s on (implemented here, same prefix):
    GET  /api/config                  -> clone/settings config JSON
    GET  /api/lead-summary/{phone}    -> AI lead summary (ephemeral)
    POST /api/leads/{phone}/bot-settings -> per-lead bot settings

AI-assist ephemerality guarantee
--------------------------------
Every AI endpoint here calls the model LIVE and returns the result in the HTTP
response ONLY. Nothing is written to any table. In particular this module never
imports or writes services/maestro_training nor the maestro_training_samples
table (Council VETO in force). The model context is built in-memory from
wa_messages that already exist; no derived/generated text is persisted.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone, date
from typing import Optional

import httpx

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from models import get_db, Client
from models.case import Case
from models.tenant import tenant_query
from models.whatsapp_clone import WaContact, WaConversation, WaMessage
from models.user import User
from auth import get_current_user
from i18n import get_translations
from config import settings
from core.template_config import templates, PREFIX, inject_org_context
from services import whatsapp_clone_service
from services.whatsapp_bot_client import get_bot_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routing — same flag-aware prefix as routes/whatsapp_chat.py
# ---------------------------------------------------------------------------
def whatsapp_clone_enabled() -> bool:
    """True when the clone owns the /whatsapp root (default: False).

    Mirrors routes.whatsapp_chat.whatsapp_clone_enabled() so this router and the
    page router always resolve to the SAME prefix.
    """
    raw = os.getenv("CASEHUB_WHATSAPP_CLONE_ENABLED", "")
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


ROUTER_PREFIX = "/whatsapp" if whatsapp_clone_enabled() else "/whatsapp-chat"

router = APIRouter(prefix=ROUTER_PREFIX, tags=["whatsapp-crm"])

WHATSAPP_BOT_URL = settings.WHATSAPP_BOT_URL

# Canonical lead-stage vocab lives in whatsapp_clone_service (shared with the
# sidebar so the funnel labels match everywhere). Re-exported here so every
# existing reference (_ctx, pipeline, stage-set) uses the new intake funnel.
LEAD_STAGES = whatsapp_clone_service.LEAD_STAGES
LEAD_STAGE_LABELS = whatsapp_clone_service.LEAD_STAGE_LABELS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _request_org_id(request: Request) -> Optional[int]:
    """Resolve the tenant org_id from request state (set by tenancy middleware)."""
    return getattr(getattr(request, "state", None), "org_id", None)


def _ctx(request: Request, db: Session, **kwargs) -> dict:
    """Build a minimal Jinja2 context for the fragment templates."""
    product_state = getattr(getattr(request, "app", None), "state", None)
    lang = request.cookies.get("lang") or (
        "pt" if product_state and getattr(product_state, "product", None) == "lite" else "en"
    )
    user = get_current_user(request, db)
    org_ctx = inject_org_context(request, user=user)
    return {
        "request": request,
        "PREFIX": PREFIX,
        "lang": lang,
        "t": get_translations(lang),
        "user": user,
        "wa_router_prefix": ROUTER_PREFIX,
        "lead_stages": LEAD_STAGES,
        "lead_stage_labels": LEAD_STAGE_LABELS,
        **org_ctx,
        **kwargs,
    }


def _get_contact(db: Session, org_id: int, phone: str) -> Optional[WaContact]:
    """Fetch a tenant-scoped WaContact by phone (normalized)."""
    e164 = whatsapp_clone_service.normalize_phone(phone)
    if not e164:
        return None
    return (
        db.query(WaContact)
        .filter(WaContact.org_id == org_id, WaContact.phone == e164)
        .first()
    )


def _client_to_dict(client: Optional[Client]) -> Optional[dict]:
    if client is None:
        return None
    return {
        "id": client.id,
        "name": client.full_name,
        "email": client.email,
        "phone": client.phone or client.whatsapp,
        "status": client.status,
    }


def _case_to_dict(case: Optional[Case]) -> Optional[dict]:
    if case is None:
        return None
    return {
        "id": case.id,
        "case_number": case.case_number or case.numero_processo,
        "case_name": case.case_name or case.tipo_acao,
        "status": case.status,
        "visa_type": case.visa_type,
    }


def _contact_crm_payload(db: Session, org_id: int, contact: WaContact) -> dict:
    """Assemble the CRM card for one contact: client/case link, tags, stage, stats."""
    # Refresh the materialized lead score on PANEL view (per-contact, cheap — never
    # in the sidebar hot path). lead_score defaults to 0 (not None), so an is-None
    # gate never fired for existing contacts; recompute here so the panel is fresh.
    whatsapp_clone_service.recalc_lead_score(db, org_id, contact, commit=True)
    client = None
    if contact.client_id:
        client = (
            tenant_query(db, Client, org_id)
            .filter(Client.id == contact.client_id)
            .first()
        )

    cases = []
    if client is not None:
        cases = (
            tenant_query(db, Case, org_id)
            .filter(Case.client_id == client.id)
            .order_by(Case.created_at.desc())
            .all()
        )

    conv = (
        db.query(WaConversation)
        .filter(
            WaConversation.org_id == org_id,
            WaConversation.contact_id == contact.id,
        )
        .first()
    )

    msg_count = 0
    first_at = None
    last_at = None
    if conv is not None:
        msg_count = (
            db.query(WaMessage)
            .filter(
                WaMessage.org_id == org_id,
                WaMessage.conversation_id == conv.id,
            )
            .count()
        )
        first_msg = (
            db.query(WaMessage)
            .filter(
                WaMessage.org_id == org_id,
                WaMessage.conversation_id == conv.id,
            )
            .order_by(WaMessage.sent_at.asc())
            .first()
        )
        if first_msg and first_msg.sent_at:
            first_at = first_msg.sent_at.isoformat()
        if conv.last_message_at:
            last_at = conv.last_message_at.isoformat()

    return {
        "phone": contact.phone,
        "display_name": contact.display_name or contact.phone,
        "profile_pic_url": contact.profile_pic_url,
        "is_business": bool(contact.is_business),
        "is_group": bool(contact.is_group),
        "tags": contact.tags or [],
        "lead_stage": whatsapp_clone_service.normalize_stage(contact.lead_stage),
        "owner": whatsapp_clone_service.resolve_owner(db, org_id, contact.owner_user_id),
        "lead_score": contact.lead_score or 0,
        "suggested_stage": whatsapp_clone_service.suggest_next_stage(contact),
        "follow_up_date": contact.follow_up_date.isoformat() if contact.follow_up_date else None,
        "follow_up_note": contact.follow_up_note,
        "client": _client_to_dict(client),
        "cases": [_case_to_dict(c) for c in cases],
        "stats": {
            "message_count": msg_count,
            "first_contact_at": first_at,
            "last_message_at": last_at,
            "unread": conv.unread_count if conv else 0,
            "bot_enabled": bool(conv.bot_enabled) if conv else True,
            "human_takeover": bool(conv.human_takeover) if conv else False,
        },
    }


# ===========================================================================
# Quick-reply templates — ported from the legacy services/whatsapp-bot/
# agent-templates.js (30+ templates). Stored as a table-less config (Tier-3 v1
# per the plan); a wa_templates table can replace this later without API change.
# ===========================================================================
def _org_brand(request: Request) -> dict:
    """Resolve org branding tokens for template placeholder substitution."""
    org_ctx = inject_org_context(request)
    org_name = org_ctx.get("org_name") or "CaseHub"
    return {
        "ORG_NAME": org_name,
        "ORG_WEBSITE": os.getenv("ORG_WEBSITE", "https://casehub.app"),
    }


# Each template: id, category, name, and {en,pt,es} bodies. Placeholders use the
# same [NOME]/[NAME] convention as the legacy personalizeTemplate().
# Templates de resposta rápida — advocacia BR (substitui o set ILC imigração-EUA).
from services.wa_quick_replies_br import QUICK_REPLY_TEMPLATES  # noqa: E402

# Variable placeholders honored by personalize_template (legacy [NOME] convention).
_PLACEHOLDER_GROUPS = {
    "name": (r"\[NOME\]|\[NAME\]|\[NOMBRE\]",),
    "agent": (r"\[AGENTE\]|\[AGENT\]",),
    "interest": (r"\[INTERESSE\]|\[INTEREST\]|\[INTERES\]",),
    "date": (r"\[DATA\]|\[DATE\]|\[FECHA\]",),
    "time": (r"\[HORARIO\]|\[HORÁRIO\]|\[TIME\]|\[HORA\]",),
    "amount": (r"\[VALOR\]|\[AMOUNT\]|\[MONTO\]",),
    "link": (r"\[LINK\]|\[LINK_REUNIÃO\]|\[MEETING_LINK\]|\[LINK_PAGAMENTO\]|\[PAYMENT_LINK\]",),
}


def _render_template_body(body: str, brand: dict) -> str:
    """Substitute {ORG_NAME}/{ORG_WEBSITE} brand tokens in a template body."""
    out = body
    for key, val in brand.items():
        out = out.replace("{" + key + "}", str(val))
    return out


def personalize_template(text: str, contact_payload: Optional[dict], agent_name: str = "") -> str:
    """Replace [NOME]/[DATA]/etc placeholders with contact data (best-effort).

    Unknown placeholders are left intact so the operator can fill them manually.
    """
    if not text:
        return ""
    name = ""
    interest = ""
    if contact_payload:
        name = contact_payload.get("display_name") or ""
        client = contact_payload.get("client") or {}
        if client.get("name"):
            name = client["name"]
        cases = contact_payload.get("cases") or []
        if cases and cases[0].get("visa_type"):
            interest = cases[0]["visa_type"]
    values = {"name": name, "agent": agent_name, "interest": interest}
    for key, patterns in _PLACEHOLDER_GROUPS.items():
        replacement = values.get(key)
        if not replacement:
            continue
        for pat in patterns:
            text = re.sub(pat, replacement, text, flags=re.IGNORECASE)
    return text


# ===========================================================================
# Ephemeral AI assist — live Gemini calls, ZERO persistence.
# ===========================================================================
# Modelo Gemini dos assists efêmeros. Configurável por env para o Equipe CaseHub
# subir para um modelo mais forte (ex.: gemini-2.0-pro) sem alterar código.
_GEMINI_MODEL = os.getenv("WHATSAPP_AI_MODEL", "gemini-2.0-flash")
_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{_GEMINI_MODEL}:generateContent"
)

_AI_SYSTEM_PROMPT = (
    "Voce e um assistente de um escritorio de advocacia brasileiro. Ajuda a "
    "equipe a responder mensagens de WhatsApp de clientes e potenciais "
    "clientes, no contexto do Direito brasileiro (trabalhista, civel, do "
    "consumidor, de familia, previdenciario, criminal, empresarial, entre "
    "outros).\n"
    "Diretrizes:\n"
    "- Respostas profissionais, acolhedoras e concisas (2-3 frases), em "
    "portugues do Brasil.\n"
    "- Use o idioma da conversa do cliente.\n"
    "- Foque em empatia, no proximo passo pratico e em coletar os dados e "
    "documentos necessarios.\n"
    "- NAO prometa resultados de processos nem estime valores de indenizacao.\n"
    "- NAO emita parecer juridico definitivo pelo WhatsApp; para a analise do "
    "caso, oriente a agendar uma consulta com o advogado.\n"
    "- Respeite o Codigo de Etica da OAB: sem captacao de clientela, sem "
    "mercantilizacao da advocacia e sem garantia de exito."
)


async def _gemini_generate(prompt: str, *, temperature: float = 0.7,
                           max_tokens: int = 300) -> Optional[str]:
    """Single live AI call via the configured provider (PR9 — provider-agnostic).

    Delegates to services.ai_provider.get_ai_provider(). The DEFAULT provider is
    NullProvider (AI OFF, non-Gemini per Equipe CaseHub's decision), so this returns None
    unless a provider is explicitly selected via CASEHUB_AI_PROVIDER and its key is
    present. Persists NOTHING (Council training-data VETO). Kept as a thin wrapper
    so the existing AI-assist call sites stay unchanged.
    """
    from services.ai_provider import get_ai_provider
    return await get_ai_provider().generate(prompt, temperature=temperature, max_tokens=max_tokens)


async def _maestro_generate(prompt: str, *, temperature: float = 0.4,
                            max_tokens: int = 300) -> Optional[str]:
    """IA do bloco CRM via MAESTRO LOCAL (Ollama hermes3) — Equipe CaseHub 10/06: o resumo
    da conversa e a sugestão das próximas mensagens devem sair do Maestro local,
    não de um provider externo (chaves Gemini esgotadas; zero transferência).
    Cai pro provider configurado (OpenRouter/etc.) só se o Ollama estiver fora.
    """
    try:
        from services.maestro_lite import generate_text
        out = await generate_text(prompt, temperature=temperature, max_tokens=max_tokens)
        if out and out.strip():
            return out.strip()
    except Exception as e:  # noqa: BLE001
        logger.warning("[wa-crm] maestro local indisponivel (%s) -> fallback provider", e)
    try:
        from services.ai_provider import get_ai_provider
        return await get_ai_provider().generate(prompt, temperature=temperature, max_tokens=max_tokens)
    except Exception:  # noqa: BLE001
        return None


def _conversation_history(db: Session, org_id: int, phone: str, limit: int = 20) -> str:
    """Build an in-memory transcript for the AI prompt. Read-only; persists nothing."""
    msgs = whatsapp_clone_service.list_messages(db, org_id=org_id, phone=phone, limit=limit)
    lines = []
    for m in msgs:
        sender = "Atendente" if m.get("role") == "assistant" else "Cliente"
        body = (m.get("content") or "").strip()
        if body:
            lines.append(f"{sender}: {body}")
    return "\n".join(lines)


# ===========================================================================
# PAGE FRAGMENTS — loaded by static/js/whatsapp-crm.js (chat.html untouched)
# ===========================================================================
@router.get("/crm/contact-panel/{phone}", response_class=HTMLResponse)
async def crm_contact_panel(request: Request, phone: str, db: Session = Depends(get_db)):
    """Render the CRM contact-info side panel as an HTML fragment."""
    user = get_current_user(request, db)
    if not user:
        return HTMLResponse("", status_code=401)
    org_id = _request_org_id(request)
    contact_payload = None
    if org_id:
        contact = _get_contact(db, org_id, phone)
        if contact is not None:
            try:
                contact_payload = _contact_crm_payload(db, org_id, contact)
            except Exception as e:  # noqa: BLE001
                logger.error("crm_contact_panel payload failed: %s", e)
                db.rollback()
    return templates.TemplateResponse(
        "whatsapp/_contact_panel.html",
        _ctx(request, db, phone=phone, contact=contact_payload),
    )


@router.get("/crm/pipeline", response_class=HTMLResponse)
async def crm_pipeline_fragment(request: Request, db: Session = Depends(get_db)):
    """Render the lead-pipeline kanban as an HTML fragment."""
    user = get_current_user(request, db)
    if not user:
        return HTMLResponse("", status_code=401)
    return templates.TemplateResponse(
        "whatsapp/_pipeline.html",
        _ctx(request, db),
    )


# ===========================================================================
# CRM — client/case linking, tags, lead stage
# ===========================================================================
@router.get("/api/crm/contact/{phone}")
async def api_crm_contact(request: Request, phone: str, db: Session = Depends(get_db)):
    """Return the CRM card for a contact (client/case link, tags, stage, stats)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"}, status_code=400)

    contact = _get_contact(db, org_id, phone)
    if contact is None:
        # Contact not yet persisted — return an empty-but-valid card.
        return JSONResponse({
            "phone": whatsapp_clone_service.normalize_phone(phone),
            "display_name": phone,
            "tags": [],
            "lead_stage": "novo",
            "owner": None,
            "client": None,
            "cases": [],
            "stats": {"message_count": 0},
            "exists": False,
        })
    try:
        payload = _contact_crm_payload(db, org_id, contact)
        payload["exists"] = True
    except Exception as e:  # noqa: BLE001
        logger.error("api_crm_contact failed: %s", e)
        db.rollback()
        return JSONResponse({"error": "internal error"}, status_code=500)
    return JSONResponse(payload)


@router.post("/api/crm/link/{phone}")
async def api_crm_link(request: Request, phone: str, db: Session = Depends(get_db)):
    """Link (or unlink) a WhatsApp contact to a CaseHub Client.

    Body: {"client_id": <int|null>}. A null/0 client_id unlinks. The optional
    case is not stored on wa_contacts (no column); the UI uses client_id and
    fetches that client's cases on demand.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"}, status_code=400)

    body = await request.json()
    raw_client = body.get("client_id")
    try:
        client_id = int(raw_client) if raw_client not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        return JSONResponse({"error": "client_id must be an integer or null"}, status_code=400)

    if client_id is not None:
        # Verify the client belongs to this tenant before linking.
        client = tenant_query(db, Client, org_id).filter(Client.id == client_id).first()
        if client is None:
            return JSONResponse({"error": "client not found"}, status_code=404)

    contact = _get_contact(db, org_id, phone)
    if contact is None:
        # Create the contact so the link can persist even before first message.
        contact = whatsapp_clone_service.upsert_contact(
            db, org_id=org_id, phone=phone, commit=False,
        )
    contact.client_id = client_id
    contact.updated_at = datetime.now(tz=timezone.utc)
    whatsapp_clone_service.recalc_lead_score(db, org_id, contact, commit=False)
    try:
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.error("api_crm_link commit failed: %s", e)
        db.rollback()
        return JSONResponse({"error": "internal error"}, status_code=500)
    return JSONResponse({"success": True, "client_id": client_id})


@router.post("/api/crm/tags/{phone}")
async def api_crm_tags(request: Request, phone: str, db: Session = Depends(get_db)):
    """Set the tag list on a contact. Body: {"tags": ["...", ...]}."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"}, status_code=400)

    body = await request.json()
    raw_tags = body.get("tags", [])
    if not isinstance(raw_tags, list):
        return JSONResponse({"error": "tags must be a list"}, status_code=400)
    # Normalize: trim, drop empties, dedupe, cap length (defensive).
    tags = []
    for t in raw_tags:
        s = str(t).strip()[:48]
        if s and s not in tags:
            tags.append(s)
        if len(tags) >= 20:
            break

    contact = _get_contact(db, org_id, phone)
    if contact is None:
        contact = whatsapp_clone_service.upsert_contact(
            db, org_id=org_id, phone=phone, commit=False,
        )
    contact.tags = tags
    contact.updated_at = datetime.now(tz=timezone.utc)
    try:
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.error("api_crm_tags commit failed: %s", e)
        db.rollback()
        return JSONResponse({"error": "internal error"}, status_code=500)
    return JSONResponse({"success": True, "tags": tags})


@router.post("/api/crm/stage/{phone}")
async def api_crm_stage(request: Request, phone: str, db: Session = Depends(get_db)):
    """Set the lead stage on a contact. Body: {"stage": "cold|warm|qualified|hot"}."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"}, status_code=400)

    body = await request.json()
    raw_stage = str(body.get("stage", "")).strip().lower()
    if not raw_stage:
        return JSONResponse({"error": "stage required"}, status_code=400)
    # normalize_stage maps legacy aliases (cold/warm/...) onto the intake funnel.
    stage = whatsapp_clone_service.normalize_stage(raw_stage)

    contact = _get_contact(db, org_id, phone)
    if contact is None:
        contact = whatsapp_clone_service.upsert_contact(
            db, org_id=org_id, phone=phone, commit=False,
        )
    prev_stage = whatsapp_clone_service.normalize_stage(contact.lead_stage) if contact.lead_stage else None
    contact.lead_stage = stage
    contact.updated_at = datetime.now(tz=timezone.utc)
    whatsapp_clone_service.recalc_lead_score(db, org_id, contact, commit=False)
    try:
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.error("api_crm_stage commit failed: %s", e)
        db.rollback()
        return JSONResponse({"error": "internal error"}, status_code=500)
    try:
        whatsapp_clone_service.record_stage_change(
            db, org_id, contact.id, prev_stage, stage, user.id, reason="manual",
        )
    except Exception:  # noqa: BLE001 — history is best-effort, never break the stage write.
        db.rollback()
    return JSONResponse({"success": True, "stage": stage})


@router.post("/api/crm/owner/{phone}")
async def api_crm_owner(request: Request, phone: str, db: Session = Depends(get_db)):
    """Assign (or clear) the owner team-member of a contact.

    Body: {"owner_user_id": int|null}. The owner MUST be an enabled member of the
    caller's org (tenant safety); null/0 clears the owner.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"}, status_code=400)

    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
    if not whatsapp_clone_service.normalize_phone(phone):
        return JSONResponse({"error": "invalid phone"}, status_code=400)
    raw = body.get("owner_user_id", None)
    owner_user_id = None
    if raw not in (None, "", 0, "0"):
        try:
            owner_user_id = int(raw)
        except (TypeError, ValueError):
            return JSONResponse({"error": "owner_user_id must be an integer or null"}, status_code=400)
        member = (
            db.query(User)
            .filter(User.id == owner_user_id, User.org_id == org_id, User.enabled.is_(True))
            .first()
        )
        if member is None:
            return JSONResponse({"error": "owner_user_id is not a member of this org"}, status_code=400)

    contact = _get_contact(db, org_id, phone)
    if contact is None:
        contact = whatsapp_clone_service.upsert_contact(
            db, org_id=org_id, phone=phone, commit=False,
        )
    contact.owner_user_id = owner_user_id
    contact.updated_at = datetime.now(tz=timezone.utc)
    try:
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.error("api_crm_owner commit failed: %s", e)
        db.rollback()
        return JSONResponse({"error": "internal error"}, status_code=500)
    return JSONResponse({
        "success": True,
        "owner": whatsapp_clone_service.resolve_owner(db, org_id, owner_user_id),
    })


@router.get("/api/crm/org-users")
async def api_crm_org_users(request: Request, db: Session = Depends(get_db)):
    """Org members for the owner dropdown: {"users": [{id, name, color}]}. Tenant-scoped."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"}, status_code=400)
    members = (
        tenant_query(db, User, org_id)
        .filter(User.enabled.is_(True))
        .order_by(User.name)
        .all()
    )
    return JSONResponse({
        "users": [
            {"id": u.id, "user_id": u.id, "name": u.name, "color": whatsapp_clone_service.owner_color(u)}
            for u in members
        ]
    })


@router.get("/api/crm/notes/{phone}")
async def api_crm_notes_list(request: Request, phone: str, db: Session = Depends(get_db)):
    """List the CRM notes of a contact (newest-first). Tenant-scoped."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"}, status_code=400)
    contact = _get_contact(db, org_id, phone)
    if contact is None:
        return JSONResponse({"notes": []})
    return JSONResponse({"notes": whatsapp_clone_service.list_notes(db, org_id, contact.id)})


@router.post("/api/crm/notes/{phone}")
async def api_crm_notes_add(request: Request, phone: str, db: Session = Depends(get_db)):
    """Append a CRM note to a contact. Body: {"body": "...", "note_type"?: "..."}."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"}, status_code=400)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
    text = str(body.get("body", "")).strip()
    if not text:
        return JSONResponse({"error": "note body required"}, status_code=400)
    if not whatsapp_clone_service.normalize_phone(phone):
        return JSONResponse({"error": "invalid phone"}, status_code=400)
    note_type = str(body.get("note_type", "note")).strip()[:32] or "note"
    contact = _get_contact(db, org_id, phone)
    if contact is None:
        contact = whatsapp_clone_service.upsert_contact(
            db, org_id=org_id, phone=phone, commit=True,
        )
    try:
        note = whatsapp_clone_service.add_note(
            db, org_id, contact.id, user.id, text, note_type=note_type,
        )
    except Exception as e:  # noqa: BLE001
        logger.error("api_crm_notes_add failed: %s", e)
        db.rollback()
        return JSONResponse({"error": "internal error"}, status_code=500)
    return JSONResponse({"success": True, "note": note})


@router.delete("/api/crm/notes/{phone}/{note_id}")
async def api_crm_notes_delete(request: Request, phone: str, note_id: int,
                               db: Session = Depends(get_db)):
    """Delete a CRM note within the caller's org."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"}, status_code=400)
    try:
        ok = whatsapp_clone_service.delete_note(db, org_id, note_id)
    except Exception as e:  # noqa: BLE001
        logger.error("api_crm_notes_delete failed: %s", e)
        db.rollback()
        return JSONResponse({"error": "internal error"}, status_code=500)
    return JSONResponse({"success": ok})


@router.post("/api/crm/follow-up/{phone}")
async def api_crm_follow_up(request: Request, phone: str, db: Session = Depends(get_db)):
    """Schedule (or clear) a follow-up. Body: {"date": "YYYY-MM-DD"|null, "note"?: "..."}."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"}, status_code=400)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
    raw_date = str(body.get("date", "")).strip()
    note = str(body.get("note", "")).strip()[:1000] or None
    fdate = None
    if raw_date:
        try:
            fdate = date.fromisoformat(raw_date)
        except ValueError:
            return JSONResponse({"error": "date must be YYYY-MM-DD"}, status_code=400)
    contact = _get_contact(db, org_id, phone)
    if contact is None:
        if not fdate:
            return JSONResponse({"success": True, "follow_up": None})
        if not whatsapp_clone_service.normalize_phone(phone):
            return JSONResponse({"error": "invalid phone"}, status_code=400)
        contact = whatsapp_clone_service.upsert_contact(db, org_id=org_id, phone=phone, commit=True)
    res = whatsapp_clone_service.schedule_follow_up(db, org_id, contact.id, fdate, note)
    return JSONResponse({"success": True, "follow_up": res})


@router.get("/api/crm/follow-ups/overdue")
async def api_crm_follow_ups_overdue(request: Request, db: Session = Depends(get_db)):
    """List contacts with an overdue/due follow-up (org-scoped, most-overdue first)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"}, status_code=400)
    return JSONResponse({"overdue": whatsapp_clone_service.get_overdue_follow_ups(db, org_id, date.today())})


@router.get("/api/crm/duplicates/{phone}")
async def api_crm_duplicates(request: Request, phone: str, db: Session = Depends(get_db)):
    """Other contacts in this org that may be the same person (last-10 phone match)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"}, status_code=400)
    contact = _get_contact(db, org_id, phone)
    exclude = contact.id if contact else None
    return JSONResponse({"duplicates": whatsapp_clone_service.check_duplicates(db, org_id, phone, exclude)})


@router.get("/api/crm/clients")
async def api_crm_clients(request: Request, q: str = "", db: Session = Depends(get_db)):
    """Tenant-scoped client picker for the CRM link UI. Optional ?q= search."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse([])

    query = tenant_query(db, Client, org_id)
    term = q.strip()
    if term:
        like = f"%{term}%"
        query = query.filter(
            (Client.first_name.ilike(like))
            | (Client.last_name.ilike(like))
            | (Client.email.ilike(like))
            | (Client.phone.ilike(like))
            | (Client.whatsapp.ilike(like))
        )
    rows = query.order_by(Client.first_name).limit(25).all()
    return JSONResponse([_client_to_dict(c) for c in rows])


@router.get("/api/crm/cases/{client_id}")
async def api_crm_cases(request: Request, client_id: int, db: Session = Depends(get_db)):
    """Tenant-scoped case list for a client (used by the CRM case picker)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse([])
    rows = (
        tenant_query(db, Case, org_id)
        .filter(Case.client_id == client_id)
        .order_by(Case.created_at.desc())
        .limit(50)
        .all()
    )
    return JSONResponse([_case_to_dict(c) for c in rows])


# ===========================================================================
# PIPELINE / FUNNEL — conversations grouped by lead_stage
# ===========================================================================
@router.get("/api/crm/analytics")
async def api_crm_analytics(request: Request, db: Session = Depends(get_db)):
    """Funnel analytics (org-scoped): conversion, avg score, overdue, velocity."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"}, status_code=400)
    return JSONResponse(whatsapp_clone_service.compute_funnel_analytics(db, org_id, date.today()))


@router.get("/api/crm/pipeline")
async def api_crm_pipeline(request: Request, db: Session = Depends(get_db)):
    """Return conversations grouped by lead_stage, newest-first within each stage.

    Shape: {"stages": [{"key","label","count","cards":[...]}], "total": N}.
    Each card carries phone, name, profilePic, lastMessage, lastMessageTime,
    tags, client_id, client_name, unread.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"stages": [], "total": 0})

    try:
        conversations = whatsapp_clone_service.list_conversations(db, org_id=org_id)
    except Exception as e:  # noqa: BLE001
        logger.error("api_crm_pipeline list_conversations failed: %s", e)
        db.rollback()
        conversations = []

    # Resolve client display names in one pass (avoid N+1).
    client_ids = {c["client_id"] for c in conversations if c.get("client_id")}
    client_names: dict = {}
    if client_ids:
        for cli in (
            tenant_query(db, Client, org_id)
            .filter(Client.id.in_(client_ids))
            .all()
        ):
            client_names[cli.id] = cli.full_name

    buckets: dict = {s: [] for s in LEAD_STAGES}
    for conv in conversations:
        stage = whatsapp_clone_service.normalize_stage(conv.get("lead_stage"))
        if stage not in buckets:
            stage = "novo"
        buckets[stage].append({
            "phone": conv.get("phone"),
            "name": conv.get("name"),
            "profilePic": conv.get("profilePic"),
            "lastMessage": conv.get("lastMessage"),
            "lastMessageTime": conv.get("lastMessageTime"),
            "tags": conv.get("tags") or [],
            "unread": conv.get("unread") or 0,
            "client_id": conv.get("client_id"),
            "client_name": client_names.get(conv.get("client_id")),
            "lead_stage": stage,
        })

    stages = [
        {
            "key": s,
            "label": LEAD_STAGE_LABELS[s],
            "count": len(buckets[s]),
            "cards": buckets[s],
        }
        for s in LEAD_STAGES
    ]
    return JSONResponse({"stages": stages, "total": len(conversations)})


@router.post("/api/crm/pipeline/move")
async def api_crm_pipeline_move(request: Request, db: Session = Depends(get_db)):
    """Move a contact between pipeline stages. Body: {"phone","stage"}."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"}, status_code=400)

    body = await request.json()
    phone = body.get("phone", "")
    stage = str(body.get("stage", "")).strip().lower()
    if not phone:
        return JSONResponse({"error": "phone required"}, status_code=400)
    if stage not in LEAD_STAGES:
        return JSONResponse(
            {"error": f"stage must be one of {LEAD_STAGES}"}, status_code=400
        )

    contact = _get_contact(db, org_id, phone)
    if contact is None:
        return JSONResponse({"error": "contact not found"}, status_code=404)
    prev_stage = whatsapp_clone_service.normalize_stage(contact.lead_stage) if contact.lead_stage else None
    contact.lead_stage = stage
    contact.updated_at = datetime.now(tz=timezone.utc)
    try:
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.error("api_crm_pipeline_move commit failed: %s", e)
        db.rollback()
        return JSONResponse({"error": "internal error"}, status_code=500)
    try:
        whatsapp_clone_service.record_stage_change(
            db, org_id, contact.id, prev_stage, stage, user.id, reason="pipeline",
        )
    except Exception:  # noqa: BLE001 — history best-effort.
        db.rollback()
    whatsapp_clone_service.recalc_lead_score(db, org_id, contact, commit=True)  # stage change -> rescore
    return JSONResponse({"success": True, "phone": contact.phone, "stage": stage})


# ===========================================================================
# QUICK-REPLY TEMPLATES
# ===========================================================================
@router.get("/api/crm/templates")
async def api_crm_templates(request: Request, lang: str = "", db: Session = Depends(get_db)):
    """List quick-reply templates for the operator (lang-aware, brand-substituted)."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    use_lang = (lang or request.cookies.get("lang") or "pt").lower()
    if use_lang not in ("pt", "en", "es"):
        use_lang = "pt"
    brand = _org_brand(request)

    items = []
    for tpl in QUICK_REPLY_TEMPLATES:
        body = tpl["bodies"].get(use_lang) or tpl["bodies"].get("en", "")
        items.append({
            "id": tpl["id"],
            "category": tpl["category"],
            "name": tpl["name"],
            "text": _render_template_body(body, brand),
            "is_custom": False,
        })
    # Org-owned custom templates (PR4) — merged after the in-code global defaults.
    org_id = _request_org_id(request)
    if org_id:
        for t in whatsapp_clone_service.list_org_templates(db, org_id):
            items.append({
                "id": "c%d" % t.id,
                "category": t.category or "custom",
                "name": t.name,
                "text": _render_template_body(t.body_for(use_lang), brand),
                "is_custom": True,
            })
    return JSONResponse({"lang": use_lang, "count": len(items), "templates": items})


@router.get("/api/crm/template/{tid}")
async def api_crm_template_one(
    request: Request, tid: str, phone: str = "", lang: str = "",
    db: Session = Depends(get_db),
):
    """Return one quick-reply template, personalized for ?phone= when supplied."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    use_lang = (lang or request.cookies.get("lang") or "pt").lower()
    if use_lang not in ("pt", "en", "es"):
        use_lang = "pt"
    brand = _org_brand(request)
    org_id = _request_org_id(request)

    if tid.startswith("c") and tid[1:].isdigit():
        ct = whatsapp_clone_service.get_org_template(db, org_id, int(tid[1:])) if org_id else None
        if ct is None:
            return JSONResponse({"error": "template not found"}, status_code=404)
        text = _render_template_body(ct.body_for(use_lang), brand)
        tpl_id, tpl_name, tpl_cat = tid, ct.name, ct.category or "custom"
    else:
        tpl = next((t for t in QUICK_REPLY_TEMPLATES if t["id"] == tid), None)
        if tpl is None:
            return JSONResponse({"error": "template not found"}, status_code=404)
        text = _render_template_body(
            tpl["bodies"].get(use_lang) or tpl["bodies"].get("en", ""), brand
        )
        tpl_id, tpl_name, tpl_cat = tpl["id"], tpl["name"], tpl["category"]

    contact_payload = None
    if phone and org_id:
        contact = _get_contact(db, org_id, phone)
        if contact is not None:
            try:
                contact_payload = _contact_crm_payload(db, org_id, contact)
            except Exception:  # noqa: BLE001
                db.rollback()
    agent_name = getattr(user, "full_name", None) or getattr(user, "username", "") or ""
    personalized = personalize_template(text, contact_payload, agent_name)

    return JSONResponse({
        "id": tpl_id,
        "name": tpl_name,
        "category": tpl_cat,
        "text": personalized,
        "raw": text,
    })


def _parse_template_fields(body: dict, partial: bool) -> dict:
    """Extract template fields from a request body (partial=True for PUT)."""
    fields = {}
    for k in ("name", "body_pt", "category"):
        if k in body or not partial:
            fields[k] = str(body.get(k, "") or "").strip()
    for k in ("body_en", "body_es"):
        if k in body:
            fields[k] = (str(body.get(k, "") or "").strip() or None)
    return fields


@router.post("/api/crm/templates")
async def api_crm_template_create(request: Request, db: Session = Depends(get_db)):
    """Create an org-owned quick-reply template. Body: {name, body_pt, category?, body_en?, body_es?}."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"}, status_code=400)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
    f = _parse_template_fields(body, partial=False)
    if not f.get("name") or not f.get("body_pt"):
        return JSONResponse({"error": "name and body_pt are required"}, status_code=400)
    t = whatsapp_clone_service.create_template(
        db, org_id, f["name"], f["body_pt"],
        category=f.get("category") or "custom",
        body_en=f.get("body_en"), body_es=f.get("body_es"),
    )
    return JSONResponse({"success": True, "template": t.to_dict()})


@router.put("/api/crm/templates/{tid}")
async def api_crm_template_update(request: Request, tid: str, db: Session = Depends(get_db)):
    """Update an org-owned custom template (tid = 'c<id>'). Global defaults are read-only."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"}, status_code=400)
    if not (tid.startswith("c") and tid[1:].isdigit()):
        return JSONResponse({"error": "only custom templates can be edited"}, status_code=400)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
    t = whatsapp_clone_service.update_template(db, org_id, int(tid[1:]), **_parse_template_fields(body, partial=True))
    if t is None:
        return JSONResponse({"error": "template not found"}, status_code=404)
    return JSONResponse({"success": True, "template": t.to_dict()})


@router.delete("/api/crm/templates/{tid}")
async def api_crm_template_delete(request: Request, tid: str, db: Session = Depends(get_db)):
    """Delete an org-owned custom template (tid = 'c<id>')."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"}, status_code=400)
    if not (tid.startswith("c") and tid[1:].isdigit()):
        return JSONResponse({"error": "only custom templates can be deleted"}, status_code=400)
    ok = whatsapp_clone_service.delete_template(db, org_id, int(tid[1:]))
    return JSONResponse({"success": ok})


# ===========================================================================
# AI ASSIST — all ephemeral, zero persistence
# ===========================================================================
@router.post("/api/crm/ai/suggest")
async def api_crm_ai_suggest(request: Request, db: Session = Depends(get_db)):
    """Live response suggestion. Body: {"phone"}. Persists NOTHING."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"suggestion": None, "error": "No org context"})

    body = await request.json()
    phone = body.get("phone", "")
    if not phone:
        return JSONResponse({"suggestion": None, "error": "phone required"})

    history = _conversation_history(db, org_id, phone, limit=20)
    if not history:
        return JSONResponse({"suggestion": None, "error": "no conversation history"})
    last_line = history.rsplit("\n", 1)[-1]
    prompt = (
        f"{_AI_SYSTEM_PROMPT}\n\nHistorico da conversa:\n{history}\n\n"
        f"Ultima mensagem: {last_line}\n\n"
        "Sugira uma resposta apropriada para o atendente enviar:"
    )
    # Release the DB session before the slow external AI call (Ollama, up to
    # ~90s, plus a further ~30-45s external-provider fallback on timeout/
    # circuit-open) — otherwise this request sits idle-in-transaction holding
    # a lock on `users`/`wa_messages` for the whole round-trip, which can
    # queue behind a concurrent schema-ensure ALTER TABLE and take down the
    # whole site (2026-07-01 incident class).
    db.close()
    suggestion = await _maestro_generate(prompt, temperature=0.7, max_tokens=250)
    return JSONResponse({"suggestion": suggestion, "ephemeral": True})


@router.post("/api/crm/ai/summary")
async def api_crm_ai_summary(request: Request, db: Session = Depends(get_db)):
    """Live conversation summary. Body: {"phone"}. Persists NOTHING."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"summary": None, "error": "No org context"})

    body = await request.json()
    phone = body.get("phone", "")
    if not phone:
        return JSONResponse({"summary": None, "error": "phone required"})

    history = _conversation_history(db, org_id, phone, limit=30)
    if not history:
        return JSONResponse({"summary": None, "error": "no conversation history"})
    prompt = (
        "Voce e um advogado triador de um escritorio brasileiro. Resuma a "
        "conversa de WhatsApp abaixo em portugues do Brasil, em 2-4 frases, "
        "cobrindo: a area juridica provavel, o resumo do problema do cliente, "
        "a urgencia (prazos ou audiencias, se houver) e o proximo passo "
        "recomendado para a equipe. Seja conciso e factual; nao prometa "
        "resultado nem estime valores.\n\n"
        f"Conversa:\n{history}\n\nResumo:"
    )
    # Release the DB session before the slow external AI call — see the
    # incident note in api_crm_ai_suggest above (2026-07-01 prod outage).
    db.close()
    summary = await _maestro_generate(prompt, temperature=0.3, max_tokens=300)
    return JSONResponse({"summary": summary, "ephemeral": True})


@router.post("/api/crm/ai/draft")
async def api_crm_ai_draft(request: Request, db: Session = Depends(get_db)):
    """Live draft from an operator instruction. Body: {"phone","instruction"}.

    Persists NOTHING — the draft is returned for the operator to edit and send.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"draft": None, "error": "No org context"})

    body = await request.json()
    phone = body.get("phone", "")
    instruction = str(body.get("instruction", "")).strip()
    if not instruction:
        return JSONResponse({"draft": None, "error": "instruction required"})

    history = _conversation_history(db, org_id, phone, limit=15) if phone else ""
    history_block = f"Historico da conversa:\n{history}\n\n" if history else ""
    prompt = (
        f"{_AI_SYSTEM_PROMPT}\n\n{history_block}"
        f"Instrucao do atendente: {instruction}\n\n"
        "Escreva uma mensagem de WhatsApp pronta para enviar ao cliente "
        "seguindo a instrucao:"
    )
    # Release the DB session before the slow external AI call — see the
    # incident note in api_crm_ai_suggest above (2026-07-01 prod outage).
    db.close()
    draft = await _maestro_generate(prompt, temperature=0.7, max_tokens=350)
    return JSONResponse({"draft": draft, "ephemeral": True})


# ===========================================================================
# THE 3 MISSING ENDPOINTS chat.js calls (currently 404)
# ===========================================================================
@router.get("/api/config")
async def api_config(request: Request, db: Session = Depends(get_db)):
    """Clone / settings config consumed by chat.js loadSettings().

    chat.js reads businessHoursStart / businessHoursEnd; the rest is provided
    so the Settings tab has a sane, non-secret config object.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    def _hour(env_name: str, default: int) -> int:
        try:
            return max(0, min(23, int(os.getenv(env_name, str(default)))))
        except (TypeError, ValueError):
            return default

    return JSONResponse({
        "clone_enabled": whatsapp_clone_enabled(),
        "router_prefix": ROUTER_PREFIX,
        "businessHoursStart": _hour("WHATSAPP_BUSINESS_HOURS_START", 9),
        "businessHoursEnd": _hour("WHATSAPP_BUSINESS_HOURS_END", 18),
        "humanTimeout": _hour("WHATSAPP_HUMAN_TIMEOUT_MIN", 5),
        "lead_stages": [
            {"key": s, "label": LEAD_STAGE_LABELS[s]} for s in LEAD_STAGES
        ],
        "ai_assist_enabled": bool(
            getattr(settings, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
        ),
        "ai_assist_ephemeral": True,
        "features": {
            "crm": True,
            "pipeline": True,
            "quick_reply_templates": True,
        },
    })


@router.get("/api/lead-summary/{phone}")
async def api_lead_summary(request: Request, phone: str, db: Session = Depends(get_db)):
    """AI lead summary consumed by chat.js loadConversationSummary().

    Returns {lead:{score,status,urgent}, summary:{currentSituation, history[],
    nextSteps[], pendingQuestions[], status, minutesSinceLastActivity}}.
    The AI text is generated LIVE and persisted NOWHERE (Council training VETO).
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"})

    contact = _get_contact(db, org_id, phone)
    if contact is None:
        return JSONResponse({"error": "no conversation"})

    conv = (
        db.query(WaConversation)
        .filter(
            WaConversation.org_id == org_id,
            WaConversation.contact_id == contact.id,
        )
        .first()
    )
    minutes_since = None
    if conv and conv.last_message_at:
        last = conv.last_message_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        minutes_since = int(
            (datetime.now(tz=timezone.utc) - last).total_seconds() // 60
        )

    history = _conversation_history(db, org_id, phone, limit=30)

    # Lead block — intake-funnel stage maps to a coarse score so the UI badge works.
    stage = whatsapp_clone_service.normalize_stage(contact.lead_stage)
    score_by_stage = {
        "novo": 20, "triagem": 40, "reuniao": 60,
        "proposta": 80, "cliente": 100, "descartado": 0,
    }
    lead = {
        "score": score_by_stage.get(stage, 20),
        "status": stage,
        "urgent": "urgent" in (contact.tags or []) or "urgente" in (contact.tags or []),
    }

    summary = {
        "currentSituation": "Resumo nao disponivel",
        "history": [],
        "nextSteps": [],
        "pendingQuestions": [],
        "status": "pending" if (minutes_since is None or minutes_since > 30) else "responded",
        "minutesSinceLastActivity": minutes_since,
    }

    # Release the DB session before the slow external AI call (Ollama, up to
    # ~90s, plus a further ~30-45s external-provider fallback on timeout/
    # circuit-open) — see the incident note in api_crm_ai_suggest above
    # (2026-07-01 prod outage). This endpoint is the highest-frequency
    # offender: chat.js loadConversationSummary() calls it on EVERY
    # conversation open. Everything needed below (stage/lead/summary/history)
    # is already a plain local value — no further ORM attribute access
    # happens past this point, so closing here is safe.
    db.close()

    if history:
        prompt = (
            "Voce e um advogado triador de um escritorio brasileiro. Analise a "
            "conversa de WhatsApp abaixo e produza um resumo objetivo para a "
            "equipe juridica. Considere as areas do Direito brasileiro "
            "(trabalhista, civel, do consumidor, de familia, previdenciario, "
            "criminal, empresarial, etc.), a urgencia (prazos, audiencias, "
            "prescricao) e os documentos necessarios.\n"
            "Responda APENAS com JSON valido neste formato exato, sem texto "
            "extra:\n"
            '{"currentSituation": "area juridica provavel + resumo do problema '
            'em 1-2 frases", '
            '"history": [{"time": "momento aproximado", "event": "fato ou evento relevante da conversa"}], '
            '"nextSteps": ["proximo passo pratico para a equipe", "..."], '
            '"pendingQuestions": ["dado ou documento que ainda falta", "..."]}\n\n'
            "Nao prometa resultado nem estime valores. Use portugues do Brasil.\n\n"
            f"Conversa:\n{history}\n\nJSON:"
        )
        ai_text = await _maestro_generate(prompt, temperature=0.3, max_tokens=400)
        if ai_text:
            match = re.search(r"\{[\s\S]*\}", ai_text)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                    if parsed.get("currentSituation"):
                        summary["currentSituation"] = str(parsed["currentSituation"])
                    if isinstance(parsed.get("history"), list):
                        history_items = []
                        for item in parsed["history"]:
                            if isinstance(item, dict):
                                event = (
                                    item.get("event")
                                    or item.get("text")
                                    or item.get("description")
                                    or item.get("summary")
                                    or ""
                                )
                                time = (
                                    item.get("time")
                                    or item.get("timestamp")
                                    or item.get("when")
                                    or "Conversa"
                                )
                            else:
                                event = item
                                time = "Conversa"
                            if event:
                                history_items.append({
                                    "time": str(time),
                                    "event": str(event),
                                })
                        summary["history"] = history_items[:6]
                    if isinstance(parsed.get("nextSteps"), list):
                        summary["nextSteps"] = [str(s) for s in parsed["nextSteps"]][:5]
                    if isinstance(parsed.get("pendingQuestions"), list):
                        summary["pendingQuestions"] = [
                            str(q) for q in parsed["pendingQuestions"]
                        ][:5]
                except (ValueError, TypeError) as e:
                    logger.debug("lead-summary JSON parse failed: %s", e)

    return JSONResponse({"lead": lead, "summary": summary, "ephemeral": True})


@router.post("/api/leads/{phone}/bot-settings")
async def api_lead_bot_settings(request: Request, phone: str, db: Session = Depends(get_db)):
    """Per-lead bot settings consumed by chat.js toggleNeverContact() (~line 1094).

    Body: {"never_contact": bool, "bot_enabled": bool, "human_takeover": 0|1}.
    Persists into wa_conversations via whatsapp_clone_service; also proxies the
    bot toggle so the Node bot stops auto-replying for this contact.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    org_id = _request_org_id(request)
    if not org_id:
        return JSONResponse({"error": "No org context"}, status_code=400)

    body = await request.json()
    never_contact = bool(body.get("never_contact", False))
    # never_contact ON  -> bot OFF + human takeover ON.
    bot_enabled = bool(body.get("bot_enabled", not never_contact))
    human_takeover = bool(body.get("human_takeover", never_contact))

    persisted = False
    try:
        persisted = whatsapp_clone_service.set_bot_enabled(
            db, org_id=org_id, phone=phone,
            enabled=bot_enabled, human_takeover=human_takeover,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("bot-settings persistence failed: %s", e)
        db.rollback()

    # Best-effort bot proxy — the persisted state above is the source of truth.
    bot_ok = False
    try:
        client = get_bot_client()
        resp = await client.post(
            f"{WHATSAPP_BOT_URL}/api/bot-control",
            json={"phone": phone, "botEnabled": bot_enabled},
            timeout=10.0,
        )
        bot_ok = resp.status_code == 200
    except Exception as e:  # noqa: BLE001
        logger.info("bot-settings bot proxy unavailable: %s", e)

    return JSONResponse({
        "success": persisted,
        "never_contact": never_contact,
        "bot_enabled": bot_enabled,
        "human_takeover": human_takeover,
        "bot_synced": bot_ok,
    })
