"""
CaseHub Lite - WhatsApp Routes (Brazilian Law Firms)
Simplified WhatsApp integration: dashboard, messages, templates, quick send.
"""
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

from models import get_db, Client, Case
from auth import get_current_user
from models.tenant import tenant_query
from i18n import get_translations

router = APIRouter(prefix="/whatsapp", tags=["whatsapp-lite"])

# ---------------------------------------------------------------------------
# Brazilian Message Templates
# ---------------------------------------------------------------------------
TEMPLATES_BR = {
    "prazo_vencendo": {
        "nome": "Prazo Vencendo",
        "mensagem": "Olá {cliente}! Informamos que o prazo do processo {numero} vence em {dias} dias ({data}). Fique atento. — {escritorio}",
        "campos": ["cliente", "numero", "dias", "data", "escritorio"],
        "icone": "fas fa-clock",
        "cor": "#f59e0b",
    },
    "audiencia_marcada": {
        "nome": "Audiência Marcada",
        "mensagem": "Olá {cliente}! Sua audiência no processo {numero} está marcada para {data} às {hora}, no {tribunal}, {vara}. — {escritorio}",
        "campos": ["cliente", "numero", "data", "hora", "tribunal", "vara", "escritorio"],
        "icone": "fas fa-gavel",
        "cor": "#3b82f6",
    },
    "documento_pronto": {
        "nome": "Documento Pronto",
        "mensagem": "Olá {cliente}! O documento '{documento}' referente ao processo {numero} está pronto para retirada/assinatura. — {escritorio}",
        "campos": ["cliente", "documento", "numero", "escritorio"],
        "icone": "fas fa-file-signature",
        "cor": "#22c55e",
    },
    "consulta_confirmacao": {
        "nome": "Confirmação de Consulta",
        "mensagem": "Olá {cliente}! Confirmamos sua consulta para {data} às {hora}. Endereço: {endereco}. — {escritorio}",
        "campos": ["cliente", "data", "hora", "endereco", "escritorio"],
        "icone": "fas fa-calendar-check",
        "cor": "#1C2447",
    },
    "cobranca_honorarios": {
        "nome": "Cobrança de Honorários",
        "mensagem": "Olá {cliente}! Lembramos que a parcela de honorários no valor de R$ {valor} vence em {data}. — {escritorio}",
        "campos": ["cliente", "valor", "data", "escritorio"],
        "icone": "fas fa-dollar-sign",
        "cor": "#ef4444",
    },
    "movimentacao_processo": {
        "nome": "Movimentação Processual",
        "mensagem": "Olá {cliente}! Houve uma movimentação no processo {numero}: {movimentacao}. — {escritorio}",
        "campos": ["cliente", "numero", "movimentacao", "escritorio"],
        "icone": "fas fa-balance-scale",
        "cor": "#8b5cf6",
    },
}


def get_context(request: Request, db: Session, **kwargs):
    """Build template context."""
    lang = request.cookies.get("lang", "pt")
    user = get_current_user(request, db)
    return {
        "request": request,
        "PREFIX": PREFIX,
        "lang": lang,
        "t": get_translations(lang),
        "user": user,
        **kwargs
    }


def _get_message_stats(db: Session, org_id: int):
    """Get message counts for today, this week, this month — scoped to the tenant."""
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    stats = {"hoje": 0, "semana": 0, "mes": 0, "total": 0}
    if not org_id:
        return stats  # sem tenant resolvido -> nada (nunca vazar cross-org)
    try:
        result = db.execute(text("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN created_at >= :today THEN 1 ELSE 0 END) AS hoje,
                SUM(CASE WHEN created_at >= :week THEN 1 ELSE 0 END) AS semana,
                SUM(CASE WHEN created_at >= :month THEN 1 ELSE 0 END) AS mes
            FROM whatsapp_messages
            WHERE org_id = :org
        """), {"today": today_start, "week": week_start, "month": month_start, "org": org_id}).fetchone()
        if result:
            stats["total"] = result.total or 0
            stats["hoje"] = result.hoje or 0
            stats["semana"] = result.semana or 0
            stats["mes"] = result.mes or 0
    except Exception as e:
        logger.warning("Could not fetch WhatsApp message stats: %s", e)
        db.rollback()
    return stats


# =============================================================================
# ROUTES
# =============================================================================

@router.get("", response_class=HTMLResponse)
async def whatsapp_dashboard(request: Request, db: Session = Depends(get_db)):
    """WhatsApp Lite dashboard - status, quick send, recent messages."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    stats = _get_message_stats(db, request.state.org_id)

    # Recent messages (last 10) — org-scoped
    recent = []
    try:
        recent = db.execute(text("""
            SELECT * FROM whatsapp_messages
            WHERE org_id = :org
            ORDER BY created_at DESC
            LIMIT 10
        """), {"org": request.state.org_id}).fetchall()
    except Exception as e:
        logger.warning("Failed to fetch recent WhatsApp messages: %s", e)
        db.rollback()

    # Clients with WhatsApp numbers for quick send
    clients = tenant_query(db, Client, request.state.org_id).filter(
        Client.whatsapp.isnot(None),
        Client.whatsapp != ""
    ).order_by(Client.first_name).all()

    return templates.TemplateResponse("app/whatsapp/lite_dashboard.html", {
        **get_context(request, db),
        "stats": stats,
        "recent": recent,
        "clients": clients,
        "templates_br": TEMPLATES_BR,
    })


@router.get("/mensagens", response_class=HTMLResponse)
async def message_history(request: Request, client_id: int = None, db: Session = Depends(get_db)):
    """Message history, optionally filtered by client."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    messages = []
    try:
        if client_id:
            client = tenant_query(db, Client, request.state.org_id).filter(Client.id == client_id).first()
            if client and (client.whatsapp or client.phone):
                phone = client.whatsapp or client.phone
                messages = db.execute(text("""
                    SELECT * FROM whatsapp_messages
                    WHERE phone = :phone AND org_id = :org
                    ORDER BY created_at DESC
                    LIMIT 100
                """), {"phone": phone, "org": request.state.org_id}).fetchall()
        else:
            messages = db.execute(text("""
                SELECT * FROM whatsapp_messages
                WHERE org_id = :org
                ORDER BY created_at DESC
                LIMIT 100
            """), {"org": request.state.org_id}).fetchall()
    except Exception as e:
        logger.warning("Failed to fetch message history: %s", e)
        db.rollback()

    clients = tenant_query(db, Client, request.state.org_id).filter(
        Client.whatsapp.isnot(None),
        Client.whatsapp != ""
    ).order_by(Client.first_name).all()

    return templates.TemplateResponse("app/whatsapp/lite_dashboard.html", {
        **get_context(request, db),
        "stats": _get_message_stats(db, request.state.org_id),
        "recent": messages,
        "clients": clients,
        "templates_br": TEMPLATES_BR,
        "view": "mensagens",
        "selected_client_id": client_id,
    })


@router.post("/enviar")
async def send_message(
    request: Request,
    phone: str = Form(...),
    message: str = Form(...),
    template_key: str = Form(None),
    db: Session = Depends(get_db)
):
    """Send a WhatsApp message to a client."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Não autorizado"}, status_code=401)

    # Try to use WhatsApp service
    try:
        from services.whatsapp import WhatsAppService
        service = WhatsAppService(db)
        result = service.send_message(phone, message, template_key)
        return JSONResponse(result)
    except ImportError:
        # Fallback: log the message attempt
        logger.info("WhatsApp send attempt (service unavailable): phone=%s, msg=%s...", phone, message[:50])
        return JSONResponse({
            "success": False,
            "error": "Serviço WhatsApp não disponível. Configure a integração."
        }, status_code=503)


@router.get("/templates")
async def list_templates(request: Request, db: Session = Depends(get_db)):
    """List all Brazilian message templates."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Não autorizado"}, status_code=401)

    return JSONResponse({
        "templates": {
            key: {
                "nome": t["nome"],
                "mensagem": t["mensagem"],
                "campos": t["campos"],
                "icone": t["icone"],
                "cor": t["cor"],
            }
            for key, t in TEMPLATES_BR.items()
        }
    })


@router.post("/templates/preview")
async def preview_template(request: Request, db: Session = Depends(get_db)):
    """Preview a template with filled-in values."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Não autorizado"}, status_code=401)

    body = await request.json()
    template_key = body.get("template_key")
    values = body.get("values", {})

    if template_key not in TEMPLATES_BR:
        return JSONResponse({"error": "Template não encontrado"}, status_code=404)

    tmpl = TEMPLATES_BR[template_key]
    try:
        preview = tmpl["mensagem"].format(**values)
    except KeyError as e:
        preview = tmpl["mensagem"]
        for k, v in values.items():
            preview = preview.replace("{" + k + "}", v)

    return JSONResponse({"preview": preview, "template": tmpl["nome"]})
