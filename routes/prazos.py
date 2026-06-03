"""
CaseHub Lite — Prazos (Deadline Calculator) Routes
Brazilian CPC deadline management.

Routes:
    GET  /prazos           — Dashboard with deadline calculator
    POST /prazos/calcular  — Calculate deadline from intimation date + tipo
    GET  /prazos/feriados/{ano} — List holidays for a year
"""
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from datetime import date
import logging

logger = logging.getLogger(__name__)

from auth import get_current_user
from models import get_db
from i18n import get_translations
from config import settings
from services.prazos_cpc import (
    calcular_prazo,
    calcular_prazo_detalhado,
    prazos_comuns,
    get_feriados,
    eh_dia_util,
    listar_prazos_para_data,
)
from core.template_config import templates

PREFIX = settings.PREFIX

router = APIRouter(prefix="/prazos", tags=["prazos"])


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


@router.get("", response_class=HTMLResponse)
async def prazos_dashboard(request: Request, db: Session = Depends(get_db)):
    """Dashboard with deadline calculator form."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    comuns = prazos_comuns()

    return templates.TemplateResponse(
        "prazos/dashboard.html",
        {
            **get_context(request, db),
            "prazos_comuns": comuns,
        },
    )


@router.post("/calcular")
async def calcular(request: Request, db: Session = Depends(get_db)):
    """
    Calculate a legal deadline.

    JSON body:
        - data_intimacao: str (YYYY-MM-DD)
        - tipo: str (key from prazos_comuns) OR
        - dias: int (custom number of business days)
        - estado: str (default "MG")
        - dobro: bool (default false, CPC Art. 229)
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON invalido"}, status_code=400)

    # Parse intimation date
    data_str = data.get("data_intimacao", "")
    if not data_str:
        return JSONResponse({"error": "data_intimacao e obrigatorio"}, status_code=400)

    try:
        data_intimacao = date.fromisoformat(data_str)
    except ValueError:
        return JSONResponse(
            {"error": "data_intimacao invalida (use YYYY-MM-DD)"}, status_code=400
        )

    estado = data.get("estado", "MG").upper()
    dobro = data.get("dobro", False)

    # Determine number of days
    tipo = data.get("tipo")
    dias = data.get("dias")

    if tipo:
        comuns = prazos_comuns()
        if tipo not in comuns:
            return JSONResponse(
                {"error": f"Tipo de prazo desconhecido: {tipo}. Disponiveis: {list(comuns.keys())}"},
                status_code=400,
            )
        dias = comuns[tipo]["dias"]
        ref = comuns[tipo]["ref"]
        descricao = comuns[tipo]["descricao"]
    elif dias:
        try:
            dias = int(dias)
        except (TypeError, ValueError):
            return JSONResponse({"error": "dias deve ser um numero inteiro"}, status_code=400)
        ref = "Personalizado"
        descricao = f"Prazo personalizado de {dias} dias uteis"
    else:
        return JSONResponse(
            {"error": "Informe 'tipo' (prazo comum) ou 'dias' (prazo personalizado)"},
            status_code=400,
        )

    try:
        resultado = calcular_prazo_detalhado(data_intimacao, dias, estado, dobro)
        resultado["tipo"] = tipo or "personalizado"
        resultado["ref"] = ref
        resultado["descricao"] = descricao
    except Exception as e:
        logger.error("Erro ao calcular prazo: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

    return JSONResponse(resultado)


@router.get("/feriados/{ano}")
async def listar_feriados(
    request: Request,
    ano: int,
    estado: str = "MG",
    db: Session = Depends(get_db),
):
    """
    List all holidays for a given year and state.

    Query params:
        - estado: State code (default MG)
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    if ano < 2000 or ano > 2100:
        return JSONResponse({"error": "Ano deve estar entre 2000 e 2100"}, status_code=400)

    feriados = get_feriados(ano, estado)

    # Format with names
    feriados_formatados = []
    for f in feriados:
        feriados_formatados.append({
            "data": f.isoformat(),
            "dia_semana": ["Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado", "Domingo"][
                f.weekday()
            ],
            "dia_util": eh_dia_util(f, estado),
        })

    return JSONResponse({
        "ano": ano,
        "estado": estado,
        "total": len(feriados),
        "feriados": feriados_formatados,
    })


@router.post("/todos")
async def todos_prazos(request: Request, db: Session = Depends(get_db)):
    """
    Calculate ALL common deadlines from a single intimation date.
    Useful after receiving a new notification.

    JSON body:
        - data_intimacao: str (YYYY-MM-DD)
        - estado: str (default "MG")
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Nao autenticado"}, status_code=401)

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "JSON invalido"}, status_code=400)

    data_str = data.get("data_intimacao", "")
    if not data_str:
        return JSONResponse({"error": "data_intimacao e obrigatorio"}, status_code=400)

    try:
        data_intimacao = date.fromisoformat(data_str)
    except ValueError:
        return JSONResponse(
            {"error": "data_intimacao invalida (use YYYY-MM-DD)"}, status_code=400
        )

    estado = data.get("estado", "MG").upper()

    try:
        resultado = listar_prazos_para_data(data_intimacao, estado)
    except Exception as e:
        logger.error("Erro ao calcular prazos: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

    return JSONResponse({
        "data_intimacao": data_str,
        "estado": estado,
        "prazos": resultado,
    })
