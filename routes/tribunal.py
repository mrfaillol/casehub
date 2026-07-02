"""
CaseHub Lite — Tribunal Consultation Routes
Unified search across DataJud, Escavador, and JusBrasil.

Routes:
    GET  /tribunal                      — Search page (template)
    POST /tribunal/consulta             — Search processo by number, name, or OAB
    GET  /tribunal/processo/{numero_cnj} — Detail view of a processo
    POST /tribunal/monitorar            — Start monitoring a processo
    GET  /tribunal/publicacoes          — Recent publications for monitored processos
"""
import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from auth import get_current_user
from config import settings
from core.template_config import templates
from i18n import get_translations
from models import get_db
from services.comunicaapi import comunicaapi_client
from services.datajud import datajud_client
from services.escavador import escavador_client
from services.jusbrasil import jusbrasil_client

logger = logging.getLogger(__name__)

PREFIX = settings.PREFIX

router = APIRouter(prefix="/tribunal", tags=["tribunal"])

# CNJ number pattern: NNNNNNN-DD.AAAA.J.TR.OOOO
CNJ_PATTERN = re.compile(r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$")


def _get_context(request: Request, db: Session, **kwargs):
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


def _is_cnj_number(text: str) -> bool:
    """Check if text looks like a CNJ process number."""
    clean = text.strip()
    if CNJ_PATTERN.match(clean):
        return True
    # Also accept raw 20-digit string
    digits_only = re.sub(r"[.\-\s]", "", clean)
    return len(digits_only) == 20 and digits_only.isdigit()


def _is_oab(text: str) -> bool:
    """Check if text looks like an OAB number (e.g., MG123456 or 123456)."""
    clean = text.strip().upper()
    return bool(re.match(r"^[A-Z]{2}\d{3,6}$", clean)) or bool(re.match(r"^\d{3,6}$", clean))


def _normalize_cnj(text: str) -> str:
    """Normalize a CNJ number to standard format NNNNNNN-DD.AAAA.J.TR.OOOO."""
    digits = re.sub(r"[.\-\s]", "", text.strip())
    if len(digits) != 20:
        return text.strip()
    return f"{digits[:7]}-{digits[7:9]}.{digits[9:13]}.{digits[13]}.{digits[14:16]}.{digits[16:20]}"


# ------------------------------------------------------------------
# Search page
# ------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
async def tribunal_search_page(request: Request, db: Session = Depends(get_db)):
    """Render the tribunal consultation search page."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ctx = _get_context(request, db, results=None, query="", search_type="")
    return templates.TemplateResponse("app/tribunal/consulta.html", ctx)


# ------------------------------------------------------------------
# Unified search
# ------------------------------------------------------------------

@router.get("/consulta")
async def tribunal_consulta_redirect():
    """Redirect GET /consulta to /tribunal (form page)."""
    return RedirectResponse(url=f"{PREFIX}/tribunal", status_code=302)

@router.post("/consulta", response_class=HTMLResponse)
async def tribunal_consulta(
    request: Request,
    db: Session = Depends(get_db),
    query: str = Form(""),
    tribunal: str = Form("TJMG"),
    search_type: str = Form("auto"),
):
    """
    Search processo by number, name, or OAB across available APIs.
    Tries APIs in order: DataJud (free) -> Escavador -> JusBrasil.
    """
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    query = query.strip()
    if not query:
        ctx = _get_context(
            request, db,
            results=None,
            query=query,
            search_type=search_type,
            error="Informe um número de processo, nome ou OAB para buscar.",
        )
        return templates.TemplateResponse("app/tribunal/consulta.html", ctx)

    # Auto-detect search type
    if search_type == "auto":
        if _is_cnj_number(query):
            search_type = "numero"
        elif _is_oab(query):
            search_type = "oab"
        else:
            search_type = "nome"

    results = []
    source = None
    error = None

    # Incident-class fix (2026-07-01 outage pattern): the DataJud/Escavador/
    # JusBrasil/ComunicaAPI chain below can take up to ~2min across
    # providers + fallbacks. get_current_user() caches the user on
    # request.state, so the _get_context() call further down (which calls
    # get_current_user again) won't re-touch the DB — release the session
    # now instead of holding it idle-in-transaction across the search.
    db.close()

    try:
        if search_type == "numero":
            # Search by CNJ number — try DataJud first, then Escavador, then JusBrasil
            cnj = _normalize_cnj(query)
            resultado = await _search_by_numero(cnj, tribunal)
            results = resultado["results"]
            source = resultado["source"]

        elif search_type == "oab":
            # Search by OAB — parse estado from input or use form value
            oab_numero = query.strip().upper()
            oab_estado = tribunal[:2] if len(tribunal) >= 2 else "MG"
            # If query starts with 2-letter state code, extract it
            oab_match = re.match(r"^([A-Z]{2})(\d+)$", oab_numero)
            if oab_match:
                oab_estado = oab_match.group(1)
                oab_numero = oab_match.group(2)

            resultado = await _search_by_oab(
                oab_numero,
                oab_estado,
                tribunal,
                org_id=getattr(request.state, "org_id", None),
            )
            results = resultado["results"]
            source = resultado["source"]

        elif search_type == "nome":
            # Search by party name
            resultado = await _search_by_nome(query, tribunal)
            results = resultado["results"]
            source = resultado["source"]

    except Exception as e:
        logger.error("Tribunal search error: %s", e, exc_info=True)
        error = f"Erro na consulta: {str(e)}"

    ctx = _get_context(
        request, db,
        results=results,
        query=query,
        search_type=search_type,
        tribunal=tribunal,
        source=source,
        error=error,
    )
    return templates.TemplateResponse("app/tribunal/consulta.html", ctx)


async def _search_by_numero(cnj: str, tribunal: str) -> dict:
    """Try APIs in order for CNJ number search."""
    # 1. DataJud (free, always try first)
    try:
        resultado = await datajud_client.consultar_processo(cnj, tribunal)
        if resultado:
            return {"results": [resultado], "source": "DataJud (CNJ)"}
    except Exception as e:
        logger.warning("DataJud search failed: %s", e)

    # 2. Escavador
    if escavador_client.is_configured:
        try:
            resultado = await escavador_client.buscar_processo(cnj)
            data = resultado.get("data", resultado)
            if data and not resultado.get("mock"):
                return {"results": [data], "source": "Escavador"}
        except Exception as e:
            logger.warning("Escavador search failed: %s", e)

    # 3. JusBrasil
    if jusbrasil_client.is_configured:
        try:
            resultado = await jusbrasil_client.consultar_processo(cnj)
            data = resultado.get("data", resultado)
            if data and not resultado.get("mock"):
                return {"results": [data], "source": "JusBrasil"}
        except Exception as e:
            logger.warning("JusBrasil search failed: %s", e)

    # Fallback: return DataJud result even if empty, or mock from Escavador
    try:
        resultado = await datajud_client.consultar_processo(cnj, tribunal)
        return {"results": [resultado] if resultado else [], "source": "DataJud (CNJ)"}
    except Exception:
        resultado = await escavador_client.buscar_processo(cnj)
        data = resultado.get("data", resultado)
        return {"results": [data] if data else [], "source": "Escavador (mock)"}


async def _search_by_oab(oab: str, estado: str, tribunal: str, org_id: Optional[int] = None) -> dict:
    """Try APIs in order for OAB search. ComunicaAPI first (free, official)."""
    # 0. ComunicaAPI PJE/CNJ (gratuita, oficial, prioridade #1)
    try:
        resultado = await comunicaapi_client.buscar_por_oab(oab, estado, org_id=org_id)
        items = resultado.get("items", [])
        if items:
            return {"results": items, "source": "ComunicaAPI PJE/CNJ"}
    except Exception as e:
        logger.warning("ComunicaAPI OAB search failed: %s", e)

    # 1. DataJud
    try:
        resultados = await datajud_client.buscar_por_advogado(oab, tribunal)
        if resultados:
            return {"results": resultados, "source": "DataJud (CNJ)"}
    except Exception as e:
        logger.warning("DataJud OAB search failed: %s", e)

    # 2. Escavador
    if escavador_client.is_configured:
        try:
            resultado = await escavador_client.buscar_por_oab(oab, estado)
            items = resultado.get("data", {}).get("items", [])
            if items and not resultado.get("mock"):
                return {"results": items, "source": "Escavador"}
        except Exception as e:
            logger.warning("Escavador OAB search failed: %s", e)

    # 3. JusBrasil
    if jusbrasil_client.is_configured:
        try:
            resultado = await jusbrasil_client.monitorar_por_oab(oab, estado)
            if not resultado.get("mock"):
                return {"results": [resultado.get("data", resultado)], "source": "JusBrasil"}
        except Exception as e:
            logger.warning("JusBrasil OAB search failed: %s", e)

    # Fallback
    try:
        resultados = await datajud_client.buscar_por_advogado(oab, tribunal)
        return {"results": resultados, "source": "DataJud (CNJ)"}
    except Exception:
        return {"results": [], "source": None}


async def _search_by_nome(nome: str, tribunal: str) -> dict:
    """Try APIs in order for name search."""
    # 1. DataJud
    try:
        resultados = await datajud_client.buscar_por_parte(nome, tribunal)
        if resultados:
            return {"results": resultados, "source": "DataJud (CNJ)"}
    except Exception as e:
        logger.warning("DataJud name search failed: %s", e)

    # 2. Escavador
    if escavador_client.is_configured:
        try:
            resultado = await escavador_client.buscar_por_nome(nome)
            items = resultado.get("data", {}).get("items", [])
            if items and not resultado.get("mock"):
                return {"results": items, "source": "Escavador"}
        except Exception as e:
            logger.warning("Escavador name search failed: %s", e)

    # 3. JusBrasil
    if jusbrasil_client.is_configured:
        try:
            diarios = await jusbrasil_client.buscar_diarios(nome)
            if diarios and not any(d.get("_mock") for d in diarios):
                return {"results": diarios, "source": "JusBrasil (Diários)"}
        except Exception as e:
            logger.warning("JusBrasil name search failed: %s", e)

    # Fallback
    try:
        resultados = await datajud_client.buscar_por_parte(nome, tribunal)
        return {"results": resultados, "source": "DataJud (CNJ)"}
    except Exception:
        return {"results": [], "source": None}


# ------------------------------------------------------------------
# Processo detail
# ------------------------------------------------------------------

@router.get("/processo/{numero_cnj:path}", response_class=HTMLResponse)
async def tribunal_processo_detail(
    request: Request,
    numero_cnj: str,
    db: Session = Depends(get_db),
):
    """Detail view of a processo with movimentações."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    cnj = _normalize_cnj(numero_cnj)
    processo = None
    movimentacoes = []
    source = None

    # Incident-class fix (2026-07-01 outage pattern): release the DB session
    # before the DataJud/Escavador/JusBrasil chain below (see
    # tribunal_consulta above for the full rationale — get_current_user's
    # request-level cache means the later _get_context() call is safe).
    db.close()

    # Try DataJud first
    try:
        processo = await datajud_client.consultar_processo(cnj)
        if processo:
            movimentacoes = processo.get("movimentos", [])
            movimentacoes.sort(key=lambda m: m.get("dataHora", ""), reverse=True)
            source = "DataJud (CNJ)"
    except Exception as e:
        logger.warning("DataJud detail failed: %s", e)

    # Try Escavador if DataJud returned nothing
    if not processo and escavador_client.is_configured:
        try:
            resultado = await escavador_client.buscar_processo(cnj)
            data = resultado.get("data", resultado)
            if data and not resultado.get("mock"):
                processo = data
                pid = data.get("id")
                if pid:
                    movimentacoes = await escavador_client.get_movimentacoes(pid)
                source = "Escavador"
        except Exception as e:
            logger.warning("Escavador detail failed: %s", e)

    # Try JusBrasil
    if not processo and jusbrasil_client.is_configured:
        try:
            resultado = await jusbrasil_client.consultar_processo(cnj)
            data = resultado.get("data", resultado)
            if data and not resultado.get("mock"):
                processo = data
                movimentacoes = data.get("movimentacoes", [])
                source = "JusBrasil"
        except Exception as e:
            logger.warning("JusBrasil detail failed: %s", e)

    if not processo:
        ctx = _get_context(
            request, db,
            error=f"Processo {cnj} não encontrado em nenhuma base de dados.",
        )
        return templates.TemplateResponse("app/tribunal/consulta.html", ctx)

    ctx = _get_context(
        request, db,
        processo=processo,
        movimentacoes=movimentacoes,
        numero_cnj=cnj,
        source=source,
    )
    return templates.TemplateResponse("app/tribunal/consulta.html", ctx)


# ------------------------------------------------------------------
# Monitor a processo
# ------------------------------------------------------------------

@router.post("/monitorar")
async def tribunal_monitorar(
    request: Request,
    db: Session = Depends(get_db),
    numero_cnj: str = Form(""),
):
    """Start monitoring a processo for new movements."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    cnj = _normalize_cnj(numero_cnj)
    if not cnj:
        return JSONResponse({"error": "Número CNJ obrigatório"}, status_code=400)

    results = {}

    # Incident-class fix (2026-07-01 outage pattern): `db` is not used again
    # in this handler after auth — release it before the Escavador/JusBrasil
    # monitoring calls instead of holding it idle-in-transaction.
    db.close()

    # Try Escavador monitoring
    if escavador_client.is_configured:
        try:
            esc_result = await escavador_client.monitorar_processo(cnj)
            results["escavador"] = esc_result
        except Exception as e:
            logger.error("Escavador monitor error: %s", e)
            results["escavador"] = {"error": str(e)}

    # Try JusBrasil monitoring
    if jusbrasil_client.is_configured:
        try:
            jb_result = await jusbrasil_client.monitorar_por_parte(cnj, "")
            results["jusbrasil"] = jb_result
        except Exception as e:
            logger.error("JusBrasil monitor error: %s", e)
            results["jusbrasil"] = {"error": str(e)}

    if not results:
        return JSONResponse(
            {
                "status": "warning",
                "message": "Nenhuma API de monitoramento configurada. Configure ESCAVADOR_API_KEY ou JUSBRASIL_API_KEY.",
            },
            status_code=200,
        )

    logger.info("Monitoramento iniciado para %s: %s", cnj, list(results.keys()))
    return JSONResponse(
        {
            "status": "ok",
            "message": f"Monitoramento iniciado para {cnj}",
            "results": results,
        }
    )


# ------------------------------------------------------------------
# Publications
# ------------------------------------------------------------------

@router.get("/publicacoes", response_class=HTMLResponse)
async def tribunal_publicacoes(
    request: Request,
    db: Session = Depends(get_db),
    nome: Optional[str] = None,
    oab: Optional[str] = None,
):
    """Recent publications for monitored processos."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    publicacoes = []
    source = None

    # Incident-class fix (2026-07-01 outage pattern): release the DB session
    # before the Escavador/JusBrasil calls below (see tribunal_consulta above
    # for the full rationale).
    db.close()

    # Try Escavador
    if escavador_client.is_configured or not jusbrasil_client.is_configured:
        try:
            publicacoes = await escavador_client.buscar_publicacoes(nome=nome, oab=oab)
            source = "Escavador"
        except Exception as e:
            logger.warning("Escavador publicacoes failed: %s", e)

    # Try JusBrasil if Escavador returned nothing useful
    if not publicacoes and jusbrasil_client.is_configured:
        try:
            termos = nome or oab or ""
            publicacoes = await jusbrasil_client.buscar_diarios(termos)
            source = "JusBrasil"
        except Exception as e:
            logger.warning("JusBrasil publicacoes failed: %s", e)

    ctx = _get_context(
        request, db,
        publicacoes=publicacoes,
        source=source,
        nome=nome or "",
        oab=oab or "",
    )
    return templates.TemplateResponse("app/tribunal/consulta.html", ctx)
