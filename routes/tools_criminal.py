"""
CaseHub Lite - Brazilian Criminal Law Calculators

Routes:
    GET  /tools/dosimetria           — Dosimetria da pena form (Art. 68 CP)
    POST /tools/dosimetria/calcular  — Calculate dosimetria
    GET  /tools/progressao           — Progressao de regime form
    POST /tools/progressao/calcular  — Calculate progressao
    GET  /tools/prescricao           — Prescricao punitiva form (Art. 109 CP)
    POST /tools/prescricao/calcular  — Calculate prescricao

Test cases (see comments in each function).
"""
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from typing import Optional, List
import logging
import math

logger = logging.getLogger(__name__)

from auth import get_current_user
from models import get_db
from i18n import get_translations
from core.template_config import templates, PREFIX

router = APIRouter(prefix="/tools", tags=["tools_criminal"])


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
# 1. Dosimetria da Pena — Art. 68 CP (3 phases)
# ---------------------------------------------------------------------------
# Test case: Furto (Art. 155) pena 1-4 anos, 3 circunstancias desfavoraveis,
#   1 atenuante (confissao), 1 aumento 1/3 (repouso noturno)
#   Fase 1: 1 + 3*(3/8) = 1 + 1.125 = 2.125 anos = 2 anos 1 mes 15 dias
#   Fase 2: 2.125 - 1/6*2.125 = 2.125 - 0.354 = 1.771 anos (nao abaixo de 1)
#   Fase 3: 1.771 * (1 + 1/3) = 2.361 anos (pode ultrapassar max)

def calcular_dosimetria(
    pena_minima_anos: int,
    pena_minima_meses: int,
    pena_maxima_anos: int,
    pena_maxima_meses: int,
    circunstancias_desfavoraveis: int,
    agravantes: list,
    atenuantes: list,
    causas_aumento: list,
    causas_diminuicao: list,
) -> dict:
    """
    Calcula dosimetria da pena em 3 fases (Art. 68 CP).

    Fundamentacao legal:
    - CP Art. 59 (circunstancias judiciais)
    - CP Art. 61-62 (agravantes)
    - CP Art. 65-66 (atenuantes)
    - CP Art. 68 (calculo trifasico)
    """
    pena_min = pena_minima_anos * 12 + pena_minima_meses  # em meses
    pena_max = pena_maxima_anos * 12 + pena_maxima_meses

    intervalo = pena_max - pena_min
    detalhes = []

    # --- FASE 1: Pena Base (Art. 59 CP) ---
    # Cada circunstancia desfavoravel aumenta 1/8 do intervalo
    circunstancias_desfavoraveis = min(max(circunstancias_desfavoraveis, 0), 8)
    aumento_fase1 = (intervalo / 8) * circunstancias_desfavoraveis
    pena_base = pena_min + aumento_fase1

    detalhes.append({
        "fase": "1a Fase - Pena Base (Art. 59 CP)",
        "descricao": f"Pena minima + ({circunstancias_desfavoraveis}/8 do intervalo)",
        "calculo": f"{_format_meses(pena_min)} + {circunstancias_desfavoraveis} x {_format_meses(intervalo / 8)} = {_format_meses(pena_base)}",
        "resultado_meses": pena_base,
        "resultado": _format_meses(pena_base),
    })

    # --- FASE 2: Agravantes e Atenuantes (Art. 61-66 CP) ---
    pena_fase2 = pena_base

    for ag in agravantes:
        fracao = ag.get("fracao", 1/6)
        nome = ag.get("nome", "Agravante")
        aumento = pena_fase2 * fracao
        pena_fase2 += aumento
        detalhes.append({
            "fase": "2a Fase - Agravante",
            "descricao": f"{nome} (+{_format_fracao(fracao)})",
            "calculo": f"{_format_meses(pena_fase2 - aumento)} + {_format_meses(aumento)} = {_format_meses(pena_fase2)}",
            "resultado_meses": pena_fase2,
            "resultado": _format_meses(pena_fase2),
        })

    for at in atenuantes:
        fracao = at.get("fracao", 1/6)
        nome = at.get("nome", "Atenuante")
        diminuicao = pena_fase2 * fracao
        pena_fase2 -= diminuicao
        detalhes.append({
            "fase": "2a Fase - Atenuante",
            "descricao": f"{nome} (-{_format_fracao(fracao)})",
            "calculo": f"{_format_meses(pena_fase2 + diminuicao)} - {_format_meses(diminuicao)} = {_format_meses(pena_fase2)}",
            "resultado_meses": pena_fase2,
            "resultado": _format_meses(pena_fase2),
        })

    # Fase 2 NAO pode ultrapassar min/max
    if pena_fase2 < pena_min:
        pena_fase2 = pena_min
        detalhes.append({
            "fase": "2a Fase - Limite",
            "descricao": "Pena nao pode ficar abaixo do minimo na 2a fase",
            "calculo": f"Ajustada para {_format_meses(pena_min)}",
            "resultado_meses": pena_fase2,
            "resultado": _format_meses(pena_fase2),
        })
    elif pena_fase2 > pena_max:
        pena_fase2 = pena_max
        detalhes.append({
            "fase": "2a Fase - Limite",
            "descricao": "Pena nao pode ultrapassar o maximo na 2a fase",
            "calculo": f"Ajustada para {_format_meses(pena_max)}",
            "resultado_meses": pena_fase2,
            "resultado": _format_meses(pena_fase2),
        })

    # --- FASE 3: Causas de aumento/diminuicao (PODE ultrapassar min/max) ---
    pena_fase3 = pena_fase2

    for ca in causas_aumento:
        fracao = ca.get("fracao", 1/3)
        nome = ca.get("nome", "Causa de aumento")
        aumento = pena_fase3 * fracao
        pena_fase3 += aumento
        detalhes.append({
            "fase": "3a Fase - Causa de Aumento",
            "descricao": f"{nome} (+{_format_fracao(fracao)})",
            "calculo": f"{_format_meses(pena_fase3 - aumento)} + {_format_meses(aumento)} = {_format_meses(pena_fase3)}",
            "resultado_meses": pena_fase3,
            "resultado": _format_meses(pena_fase3),
        })

    for cd in causas_diminuicao:
        fracao = cd.get("fracao", 1/3)
        nome = cd.get("nome", "Causa de diminuicao")
        diminuicao = pena_fase3 * fracao
        pena_fase3 -= diminuicao
        detalhes.append({
            "fase": "3a Fase - Causa de Diminuicao",
            "descricao": f"{nome} (-{_format_fracao(fracao)})",
            "calculo": f"{_format_meses(pena_fase3 + diminuicao)} - {_format_meses(diminuicao)} = {_format_meses(pena_fase3)}",
            "resultado_meses": pena_fase3,
            "resultado": _format_meses(pena_fase3),
        })

    pena_final = max(pena_fase3, 0)

    # Regime inicial sugerido (Art. 33 CP)
    pena_anos = pena_final / 12
    if pena_anos > 8:
        regime = "Fechado"
    elif pena_anos > 4:
        regime = "Semiaberto"
    else:
        regime = "Aberto"

    return {
        "pena_minima": _format_meses(pena_min),
        "pena_maxima": _format_meses(pena_max),
        "pena_base": _format_meses(pena_base),
        "pena_fase2": _format_meses(pena_fase2),
        "pena_final": _format_meses(pena_final),
        "pena_final_meses": pena_final,
        "regime_sugerido": regime,
        "detalhes": detalhes,
    }


def _format_meses(meses: float) -> str:
    """Format months to 'X ano(s) Y mes(es)' string."""
    total = round(meses, 1)
    anos = int(total // 12)
    m = round(total % 12)
    if m == 12:
        anos += 1
        m = 0
    parts = []
    if anos > 0:
        parts.append(f"{anos} ano{'s' if anos != 1 else ''}")
    if m > 0 or anos == 0:
        parts.append(f"{m} mes{'es' if m != 1 else ''}")
    return " e ".join(parts)


def _format_fracao(f: float) -> str:
    """Format a fraction to human-readable string."""
    fracs = {
        1/6: "1/6", 1/5: "1/5", 1/4: "1/4", 1/3: "1/3",
        2/5: "2/5", 1/2: "1/2", 2/3: "2/3", 3/5: "3/5",
        1/8: "1/8", 3/8: "3/8",
    }
    for val, label in fracs.items():
        if abs(f - val) < 0.001:
            return label
    return f"{f:.2%}"


@router.get("/dosimetria", response_class=HTMLResponse)
async def dosimetria_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    return templates.TemplateResponse("app/tools/dosimetria.html", get_context(request, db, resultado=None, form=None, error=None))


@router.post("/dosimetria/calcular", response_class=HTMLResponse)
async def dosimetria_calcular(
    request: Request,
    db: Session = Depends(get_db),
    crime: str = Form(""),
    pena_minima_anos: int = Form(0),
    pena_minima_meses: int = Form(0),
    pena_maxima_anos: int = Form(0),
    pena_maxima_meses: int = Form(0),
    circunstancias: int = Form(0),
    # Agravantes
    ag_reincidencia: bool = Form(False),
    ag_motivo_futil: bool = Form(False),
    ag_meio_cruel: bool = Form(False),
    ag_outro: bool = Form(False),
    ag_outro_nome: str = Form(""),
    # Atenuantes
    at_confissao: bool = Form(False),
    at_menoridade: bool = Form(False),
    at_outro: bool = Form(False),
    at_outro_nome: str = Form(""),
    # Causas de aumento
    ca_aplicar: bool = Form(False),
    ca_nome: str = Form(""),
    ca_fracao_num: int = Form(1),
    ca_fracao_den: int = Form(3),
    # Causas de diminuicao
    cd_aplicar: bool = Form(False),
    cd_nome: str = Form(""),
    cd_fracao_num: int = Form(1),
    cd_fracao_den: int = Form(3),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    form = {
        "crime": crime,
        "pena_minima_anos": pena_minima_anos,
        "pena_minima_meses": pena_minima_meses,
        "pena_maxima_anos": pena_maxima_anos,
        "pena_maxima_meses": pena_maxima_meses,
        "circunstancias": circunstancias,
        "ag_reincidencia": ag_reincidencia,
        "ag_motivo_futil": ag_motivo_futil,
        "ag_meio_cruel": ag_meio_cruel,
        "ag_outro": ag_outro,
        "ag_outro_nome": ag_outro_nome,
        "at_confissao": at_confissao,
        "at_menoridade": at_menoridade,
        "at_outro": at_outro,
        "at_outro_nome": at_outro_nome,
        "ca_aplicar": ca_aplicar,
        "ca_nome": ca_nome,
        "ca_fracao_num": ca_fracao_num,
        "ca_fracao_den": ca_fracao_den,
        "cd_aplicar": cd_aplicar,
        "cd_nome": cd_nome,
        "cd_fracao_num": cd_fracao_num,
        "cd_fracao_den": cd_fracao_den,
    }

    try:
        pena_min_total = pena_minima_anos * 12 + pena_minima_meses
        pena_max_total = pena_maxima_anos * 12 + pena_maxima_meses
        if pena_min_total <= 0 or pena_max_total <= 0:
            raise ValueError("Penas minima e maxima devem ser maiores que zero.")
        if pena_min_total > pena_max_total:
            raise ValueError("Pena minima nao pode ser maior que pena maxima.")

        agravantes = []
        if ag_reincidencia:
            agravantes.append({"nome": "Reincidencia (Art. 61, I)", "fracao": 1/6})
        if ag_motivo_futil:
            agravantes.append({"nome": "Motivo futil/torpe (Art. 61, II, a)", "fracao": 1/6})
        if ag_meio_cruel:
            agravantes.append({"nome": "Meio cruel (Art. 61, II, d)", "fracao": 1/6})
        if ag_outro and ag_outro_nome:
            agravantes.append({"nome": ag_outro_nome, "fracao": 1/6})

        atenuantes = []
        if at_confissao:
            atenuantes.append({"nome": "Confissao espontanea (Art. 65, III, d)", "fracao": 1/6})
        if at_menoridade:
            atenuantes.append({"nome": "Menor de 21 anos (Art. 65, I)", "fracao": 1/6})
        if at_outro and at_outro_nome:
            atenuantes.append({"nome": at_outro_nome, "fracao": 1/6})

        causas_aumento = []
        if ca_aplicar and ca_fracao_den > 0:
            causas_aumento.append({
                "nome": ca_nome or "Causa de aumento",
                "fracao": ca_fracao_num / ca_fracao_den,
            })

        causas_diminuicao = []
        if cd_aplicar and cd_fracao_den > 0:
            causas_diminuicao.append({
                "nome": cd_nome or "Causa de diminuicao",
                "fracao": cd_fracao_num / cd_fracao_den,
            })

        resultado = calcular_dosimetria(
            pena_minima_anos=pena_minima_anos,
            pena_minima_meses=pena_minima_meses,
            pena_maxima_anos=pena_maxima_anos,
            pena_maxima_meses=pena_maxima_meses,
            circunstancias_desfavoraveis=circunstancias,
            agravantes=agravantes,
            atenuantes=atenuantes,
            causas_aumento=causas_aumento,
            causas_diminuicao=causas_diminuicao,
        )
        resultado["crime"] = crime

        return templates.TemplateResponse("app/tools/dosimetria.html", get_context(request, db, resultado=resultado, form=form, error=None))

    except Exception as e:
        logger.exception("Dosimetria calculation error")
        return templates.TemplateResponse("app/tools/dosimetria.html", get_context(request, db, resultado=None, form=form, error=str(e)))


# ---------------------------------------------------------------------------
# 2. Progressao de Regime — LEP Art. 112, CP Art. 33
# ---------------------------------------------------------------------------
# Test case: Pena 8 anos fechado, primario, crime comum
#   Fracao: 1/6 (primario, crime comum — pre Pacote Anticrime era 1/6)
#   Atualizado Lei 13.964/2019: 16% primario crime comum
#   8 anos = 96 meses. 96 * 16% = 15.36 meses = 1 ano 3 meses 11 dias
#   Ou com fracao 1/6: 96/6 = 16 meses = 1 ano 4 meses

def calcular_progressao(
    pena_total_anos: int,
    pena_total_meses: int,
    regime_inicial: str,
    tipo_crime: str,
    reincidente: bool,
    dias_remidos_trabalho: int = 0,
    dias_remidos_estudo: int = 0,
) -> dict:
    """
    Calcula progressao de regime prisional.

    Fundamentacao legal:
    - LEP Art. 112 (com redacao da Lei 13.964/2019 - Pacote Anticrime)
    - CP Art. 33 (regimes de cumprimento)
    - LEP Art. 126-130 (remicao por trabalho/estudo)
    """
    pena_total_m = pena_total_anos * 12 + pena_total_meses
    pena_total_dias = pena_total_m * 30  # aproximacao

    # Fracoes de progressao (Lei 13.964/2019 — Pacote Anticrime)
    fracoes = {
        "comum": {"primario": 1/6, "reincidente": 1/5, "label_p": "1/6", "label_r": "1/5"},
        "hediondo": {"primario": 2/5, "reincidente": 3/5, "label_p": "2/5", "label_r": "3/5"},
        "hediondo_resultado_morte": {"primario": 1/2, "reincidente": 7/10, "label_p": "1/2 (50%)", "label_r": "7/10 (70%)"},
        "administracao_militar": {"primario": 1/8, "reincidente": 1/4, "label_p": "1/8", "label_r": "1/4"},
    }

    tipo_info = fracoes.get(tipo_crime, fracoes["comum"])
    chave = "reincidente" if reincidente else "primario"
    fracao = tipo_info[chave]
    fracao_label = tipo_info[f"label_{'r' if reincidente else 'p'}"]

    # Remicao (LEP Art. 126-130)
    # Trabalho: 1 dia remido a cada 3 dias de trabalho
    # Estudo: 1 dia remido a cada 12 horas de estudo (= aprox 1 dia a cada 4 dias, 3h/dia)
    dias_remicao_trabalho = dias_remidos_trabalho // 3
    dias_remicao_estudo = dias_remidos_estudo // 3  # simplificacao: 12h = ~3 dias de 4h
    total_remicao = dias_remicao_trabalho + dias_remicao_estudo

    pena_efetiva_dias = pena_total_dias - total_remicao
    if pena_efetiva_dias < 0:
        pena_efetiva_dias = 0

    # Tempo para progressao
    dias_para_progressao = math.ceil(pena_efetiva_dias * fracao)
    meses_progressao = dias_para_progressao / 30

    # Regimes possiveis
    regimes = ["fechado", "semiaberto", "aberto"]
    idx_atual = regimes.index(regime_inicial) if regime_inicial in regimes else 0

    progressoes = []
    dias_acumulados = 0
    for i in range(idx_atual, len(regimes) - 1):
        dias_prog = math.ceil(pena_efetiva_dias * fracao)
        dias_acumulados += dias_prog
        progressoes.append({
            "de": regimes[i].capitalize(),
            "para": regimes[i + 1].capitalize(),
            "dias": dias_prog,
            "meses": round(dias_prog / 30, 1),
            "formatado": _format_dias(dias_prog),
        })

    return {
        "pena_total": _format_meses(pena_total_m),
        "pena_total_dias": pena_total_dias,
        "regime_inicial": regime_inicial.capitalize(),
        "tipo_crime": tipo_crime.replace("_", " ").capitalize(),
        "reincidente": reincidente,
        "fracao": fracao,
        "fracao_label": fracao_label,
        "dias_remicao_trabalho": dias_remicao_trabalho,
        "dias_remicao_estudo": dias_remicao_estudo,
        "total_remicao": total_remicao,
        "pena_efetiva_dias": pena_efetiva_dias,
        "pena_efetiva": _format_dias(pena_efetiva_dias),
        "dias_para_progressao": dias_para_progressao,
        "tempo_progressao": _format_dias(dias_para_progressao),
        "progressoes": progressoes,
    }


def _format_dias(dias: int) -> str:
    """Format days to readable string."""
    if dias <= 0:
        return "0 dias"
    anos = dias // 365
    resto = dias % 365
    meses = resto // 30
    d = resto % 30
    parts = []
    if anos > 0:
        parts.append(f"{anos} ano{'s' if anos != 1 else ''}")
    if meses > 0:
        parts.append(f"{meses} mes{'es' if meses != 1 else ''}")
    if d > 0 or not parts:
        parts.append(f"{d} dia{'s' if d != 1 else ''}")
    return ", ".join(parts)


@router.get("/progressao", response_class=HTMLResponse)
async def progressao_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    return templates.TemplateResponse("app/tools/progressao.html", get_context(request, db, resultado=None, form=None, error=None))


@router.post("/progressao/calcular", response_class=HTMLResponse)
async def progressao_calcular(
    request: Request,
    db: Session = Depends(get_db),
    pena_anos: int = Form(0),
    pena_meses: int = Form(0),
    regime_inicial: str = Form("fechado"),
    tipo_crime: str = Form("comum"),
    reincidente: bool = Form(False),
    dias_trabalho: int = Form(0),
    dias_estudo: int = Form(0),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    form = {
        "pena_anos": pena_anos,
        "pena_meses": pena_meses,
        "regime_inicial": regime_inicial,
        "tipo_crime": tipo_crime,
        "reincidente": reincidente,
        "dias_trabalho": dias_trabalho,
        "dias_estudo": dias_estudo,
    }

    try:
        pena_total = pena_anos * 12 + pena_meses
        if pena_total <= 0:
            raise ValueError("Pena total deve ser maior que zero.")

        resultado = calcular_progressao(
            pena_total_anos=pena_anos,
            pena_total_meses=pena_meses,
            regime_inicial=regime_inicial,
            tipo_crime=tipo_crime,
            reincidente=reincidente,
            dias_remidos_trabalho=dias_trabalho,
            dias_remidos_estudo=dias_estudo,
        )

        return templates.TemplateResponse("app/tools/progressao.html", get_context(request, db, resultado=resultado, form=form, error=None))

    except Exception as e:
        logger.exception("Progressao calculation error")
        return templates.TemplateResponse("app/tools/progressao.html", get_context(request, db, resultado=None, form=form, error=str(e)))


# ---------------------------------------------------------------------------
# 3. Prescricao Punitiva — Art. 109-117 CP
# ---------------------------------------------------------------------------
# Test case: Pena 3 anos, reu 19 anos na data do fato
#   Pena > 2 e <= 4: prescricao 8 anos
#   Menor de 21 na data do fato: reduz pela metade = 4 anos

def calcular_prescricao(
    pena_anos: int,
    pena_meses: int,
    data_fato: date,
    idade_na_data_fato: int,
    idade_na_sentenca: Optional[int] = None,
    marcos_interruptivos: Optional[List[dict]] = None,
) -> dict:
    """
    Calcula prescricao da pretensao punitiva (Art. 109-117 CP).

    Tabela Art. 109 CP:
    - Pena > 12 anos: 20 anos
    - Pena > 8 e <= 12: 16 anos
    - Pena > 4 e <= 8: 12 anos
    - Pena > 2 e <= 4: 8 anos
    - Pena >= 1 e <= 2: 4 anos
    - Pena < 1 ano: 3 anos

    Art. 115 CP: prazo reduzido pela metade se:
    - Agente < 21 anos na data do fato
    - Agente > 70 anos na data da sentenca
    """
    pena_total_meses = pena_anos * 12 + pena_meses
    pena_em_anos = pena_total_meses / 12

    # Tabela Art. 109 CP
    if pena_em_anos > 12:
        prazo_prescricao = 20
    elif pena_em_anos > 8:
        prazo_prescricao = 16
    elif pena_em_anos > 4:
        prazo_prescricao = 12
    elif pena_em_anos > 2:
        prazo_prescricao = 8
    elif pena_em_anos >= 1:
        prazo_prescricao = 4
    else:
        prazo_prescricao = 3

    prazo_original = prazo_prescricao
    reducao_metade = False
    motivo_reducao = None

    # Art. 115 CP - reducao pela metade
    if idade_na_data_fato < 21:
        prazo_prescricao = prazo_prescricao / 2
        reducao_metade = True
        motivo_reducao = f"Agente menor de 21 anos na data do fato ({idade_na_data_fato} anos) - Art. 115 CP"
    elif idade_na_sentenca and idade_na_sentenca > 70:
        prazo_prescricao = prazo_prescricao / 2
        reducao_metade = True
        motivo_reducao = f"Agente maior de 70 anos na data da sentenca ({idade_na_sentenca} anos) - Art. 115 CP"

    # Data da prescricao (a partir da data do fato)
    prazo_anos_int = int(prazo_prescricao)
    prazo_meses_frac = int((prazo_prescricao - prazo_anos_int) * 12)
    data_prescricao = data_fato + relativedelta(years=prazo_anos_int, months=prazo_meses_frac)

    hoje = date.today()
    prescrito = hoje >= data_prescricao
    dias_restantes = (data_prescricao - hoje).days if not prescrito else 0

    # Marcos interruptivos (Art. 117 CP)
    marcos_info = []
    if marcos_interruptivos:
        for marco in marcos_interruptivos:
            nome = marco.get("nome", "Marco interruptivo")
            data_str = marco.get("data", "")
            if data_str:
                try:
                    data_marco = datetime.strptime(data_str, "%Y-%m-%d").date()
                    nova_prescricao = data_marco + relativedelta(years=prazo_anos_int, months=prazo_meses_frac)
                    marcos_info.append({
                        "nome": nome,
                        "data": data_marco.strftime("%d/%m/%Y"),
                        "nova_prescricao": nova_prescricao.strftime("%d/%m/%Y"),
                        "prescrito": hoje >= nova_prescricao,
                    })
                    # O ultimo marco interruptivo define a prescricao
                    if nova_prescricao > data_prescricao:
                        data_prescricao = nova_prescricao
                        prescrito = hoje >= data_prescricao
                        dias_restantes = (data_prescricao - hoje).days if not prescrito else 0
                except ValueError:
                    pass

    return {
        "pena": _format_meses(pena_total_meses),
        "pena_em_anos": round(pena_em_anos, 1),
        "prazo_original": prazo_original,
        "prazo_prescricao": prazo_prescricao,
        "prazo_formatado": _format_meses(prazo_prescricao * 12),
        "reducao_metade": reducao_metade,
        "motivo_reducao": motivo_reducao,
        "data_fato": data_fato.strftime("%d/%m/%Y"),
        "data_prescricao": data_prescricao.strftime("%d/%m/%Y"),
        "prescrito": prescrito,
        "dias_restantes": dias_restantes,
        "marcos": marcos_info,
    }


@router.get("/prescricao", response_class=HTMLResponse)
async def prescricao_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    return templates.TemplateResponse("app/tools/prescricao.html", get_context(request, db, resultado=None, form=None, error=None))


@router.post("/prescricao/calcular", response_class=HTMLResponse)
async def prescricao_calcular(
    request: Request,
    db: Session = Depends(get_db),
    pena_anos: int = Form(0),
    pena_meses: int = Form(0),
    data_fato: str = Form(""),
    idade_fato: int = Form(30),
    idade_sentenca: int = Form(0),
    # Marcos interruptivos
    marco1_nome: str = Form(""),
    marco1_data: str = Form(""),
    marco2_nome: str = Form(""),
    marco2_data: str = Form(""),
    marco3_nome: str = Form(""),
    marco3_data: str = Form(""),
    marco4_nome: str = Form(""),
    marco4_data: str = Form(""),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    form = {
        "pena_anos": pena_anos,
        "pena_meses": pena_meses,
        "data_fato": data_fato,
        "idade_fato": idade_fato,
        "idade_sentenca": idade_sentenca,
        "marco1_nome": marco1_nome, "marco1_data": marco1_data,
        "marco2_nome": marco2_nome, "marco2_data": marco2_data,
        "marco3_nome": marco3_nome, "marco3_data": marco3_data,
        "marco4_nome": marco4_nome, "marco4_data": marco4_data,
    }

    try:
        if not data_fato:
            raise ValueError("Data do fato e obrigatoria.")
        data_fato_parsed = datetime.strptime(data_fato, "%Y-%m-%d").date()
        pena_total = pena_anos * 12 + pena_meses
        if pena_total <= 0:
            raise ValueError("Pena deve ser maior que zero.")

        marcos = []
        for nome, data in [(marco1_nome, marco1_data), (marco2_nome, marco2_data),
                           (marco3_nome, marco3_data), (marco4_nome, marco4_data)]:
            if nome and data:
                marcos.append({"nome": nome, "data": data})

        resultado = calcular_prescricao(
            pena_anos=pena_anos,
            pena_meses=pena_meses,
            data_fato=data_fato_parsed,
            idade_na_data_fato=idade_fato,
            idade_na_sentenca=idade_sentenca if idade_sentenca > 0 else None,
            marcos_interruptivos=marcos if marcos else None,
        )

        return templates.TemplateResponse("app/tools/prescricao.html", get_context(request, db, resultado=resultado, form=form, error=None))

    except Exception as e:
        logger.exception("Prescricao calculation error")
        return templates.TemplateResponse("app/tools/prescricao.html", get_context(request, db, resultado=None, form=form, error=str(e)))
