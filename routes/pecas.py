"""
CaseHub Lite - Gerador de Pecas Juridicas (Legal Document Generator)

Routes:
    GET  /tools/pecas                  — Landing page showing all 8 peca types
    GET  /tools/pecas/{tipo}           — Form for specific peca type
    POST /tools/pecas/{tipo}/gerar     — Generate document, return preview
    POST /tools/pecas/{tipo}/download  — Download as DOCX or TXT
    GET  /api/pecas/ollama-status      — Check if Ollama is available
"""
from fastapi import APIRouter, Depends, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional
import logging
import io

logger = logging.getLogger(__name__)

from auth import get_current_user
from models import get_db, Case, Client
from models.tenant import tenant_query
from i18n import get_translations
from core.template_config import templates, PREFIX
from services.gerador_pecas import (
    listar_pecas, get_template, gerar_peca_template,
    gerar_peca_llm, verificar_ollama, gerar_docx, PECAS_TEMPLATES,
)

router = APIRouter(prefix="/tools", tags=["pecas"])


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
        **kwargs,
    }


# ---------------------------------------------------------------------------
# Landing page: all peca types as cards
# ---------------------------------------------------------------------------
@router.get("/pecas", response_class=HTMLResponse)
async def pecas_index(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    pecas = listar_pecas()
    ollama_online = await verificar_ollama()

    return templates.TemplateResponse("app/tools/pecas_index.html", get_context(
        request, db,
        pecas=pecas,
        ollama_online=ollama_online,
    ))


# ---------------------------------------------------------------------------
# Form for specific peca type
# ---------------------------------------------------------------------------
@router.get("/pecas/{tipo}", response_class=HTMLResponse)
async def peca_form(
    request: Request,
    tipo: str,
    process_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    template = get_template(tipo)
    if not template:
        return RedirectResponse(url=f"{PREFIX}/tools/pecas", status_code=302)

    # Pre-populate from linked process if process_id provided
    prefill = {}
    processo_info = None
    if process_id:
        try:
            caso = tenant_query(db, Case, request.state.org_id).filter(Case.id == process_id).first()
            if caso:
                processo_info = caso
                # Map case fields to form fields
                if caso.numero_processo:
                    prefill["processo"] = caso.numero_processo
                if caso.vara:
                    prefill["vara"] = caso.vara
                if caso.comarca:
                    prefill["comarca"] = caso.comarca
                if caso.tipo_acao:
                    prefill["tipo_acao"] = caso.tipo_acao
                if caso.case_value:
                    prefill["valor_causa"] = str(caso.case_value)
                if caso.polo_ativo:
                    prefill["autor"] = caso.polo_ativo
                    prefill["apelante"] = caso.polo_ativo
                    prefill["agravante"] = caso.polo_ativo
                    prefill["embargante"] = caso.polo_ativo
                    prefill["recorrente"] = caso.polo_ativo
                    prefill["impetrante"] = caso.polo_ativo
                if caso.polo_passivo:
                    prefill["reu"] = caso.polo_passivo
                    prefill["apelado"] = caso.polo_passivo
                    prefill["agravado"] = caso.polo_passivo
                    prefill["recorrido"] = caso.polo_passivo

                # Get client name
                if caso.client:
                    prefill.setdefault("autor", caso.client.name)
        except Exception as e:
            logger.warning("Error loading process %s: %s", process_id, e)

    ollama_online = await verificar_ollama()

    return templates.TemplateResponse("app/tools/peca_form.html", get_context(
        request, db,
        tipo=tipo,
        template=template,
        campos=template.get("campos", []),
        prefill=prefill,
        processo_info=processo_info,
        ollama_online=ollama_online,
    ))


# ---------------------------------------------------------------------------
# Generate document
# ---------------------------------------------------------------------------
@router.post("/pecas/{tipo}/gerar", response_class=HTMLResponse)
async def peca_gerar(
    request: Request,
    tipo: str,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    template = get_template(tipo)
    if not template:
        return RedirectResponse(url=f"{PREFIX}/tools/pecas", status_code=302)

    # Collect form data
    form_data = await request.form()
    dados = {}
    for campo in template.get("campos", []):
        campo_id = campo["id"] if isinstance(campo, dict) else campo
        value = form_data.get(campo_id, "").strip()
        if value:
            dados[campo_id] = value

    usar_ia = form_data.get("usar_ia") == "on"

    # Generate from template
    try:
        texto_base = gerar_peca_template(tipo, dados.copy())
    except ValueError as e:
        return templates.TemplateResponse("app/tools/peca_form.html", get_context(
            request, db,
            tipo=tipo,
            template=template,
            campos=template.get("campos", []),
            prefill=dados,
            error=str(e),
            ollama_online=await verificar_ollama(),
        ))

    # LLM enhancement if requested
    texto_final = texto_base
    ia_status = None
    ia_model = None
    if usar_ia:
        resultado_ia = await gerar_peca_llm(tipo, dados, texto_base)
        texto_final = resultado_ia["texto"]
        ia_status = resultado_ia["status"]
        ia_model = resultado_ia.get("model")

    ollama_online = await verificar_ollama()

    return templates.TemplateResponse("app/tools/peca_form.html", get_context(
        request, db,
        tipo=tipo,
        template=template,
        campos=template.get("campos", []),
        prefill=dados,
        texto_gerado=texto_final,
        texto_base=texto_base,
        ia_status=ia_status,
        ia_model=ia_model,
        usar_ia=usar_ia,
        ollama_online=ollama_online,
    ))


# ---------------------------------------------------------------------------
# Download as DOCX or TXT
# ---------------------------------------------------------------------------
@router.post("/pecas/{tipo}/download")
async def peca_download(
    request: Request,
    tipo: str,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    form_data = await request.form()
    texto = form_data.get("texto", "")
    formato = form_data.get("formato", "txt")

    template = get_template(tipo)
    nome_peca = template["nome"] if template else tipo
    nome_arquivo = nome_peca.lower().replace(" ", "_").replace("/", "_")
    data_str = date.today().strftime("%Y%m%d")

    if formato == "docx":
        buffer = gerar_docx(texto, nome_peca)
        if buffer:
            return StreamingResponse(
                buffer,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={
                    "Content-Disposition": f'attachment; filename="{nome_arquivo}_{data_str}.docx"',
                },
            )
        else:
            # Fallback to TXT if python-docx not available
            formato = "txt"

    # TXT download
    buffer = io.BytesIO(texto.encode("utf-8"))
    return StreamingResponse(
        buffer,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{nome_arquivo}_{data_str}.txt"',
        },
    )


# ---------------------------------------------------------------------------
# API: Check Ollama status
# ---------------------------------------------------------------------------
@router.get("/api/pecas/ollama-status")
async def ollama_status():
    online = await verificar_ollama()
    return {"online": online, "model": PECAS_TEMPLATES and "configured" or "none"}
