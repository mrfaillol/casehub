"""
CaseHub Lite - Brazilian Banking Law Calculators

Routes:
    GET  /tools/revisao-emprestimo           — Loan revision calculator form
    POST /tools/revisao-emprestimo/calcular  — Calculate loan revision
    GET  /tools/superendividamento           — Over-indebtedness analyzer form
    POST /tools/superendividamento/calcular  — Calculate over-indebtedness
    GET  /tools/juros-simples-compostos      — Simple vs compound interest form
    POST /tools/juros-simples-compostos/calcular — Calculate interest comparison
    GET  /tools/price-sac-sacre              — Price vs SAC vs SACRE form
    POST /tools/price-sac-sacre/calcular     — Calculate amortization comparison
    GET  /tools/cet                          — CET (total effective cost) form
    POST /tools/cet/calcular                 — Calculate CET

Test cases (see comments in each function).
"""
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional, List
import logging
import math
import json

logger = logging.getLogger(__name__)

from auth import get_current_user
from models import get_db
from i18n import get_translations
from core.template_config import templates, PREFIX

router = APIRouter(prefix="/tools", tags=["tools_bancario"])


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


# ===========================================================================
# Salario Minimo 2026 (referencia para superendividamento)
# ===========================================================================
SALARIO_MINIMO = 1518.00  # SM 2025 (atualizar conforme vigencia)


# ===========================================================================
# Utility: PMT (Payment) formula - Tabela Price
# PMT = PV * [i(1+i)^n / ((1+i)^n - 1)]
# ===========================================================================
def pmt(pv: float, i: float, n: int) -> float:
    """Calculate fixed monthly payment (Tabela Price / French system)."""
    if i == 0:
        return pv / n if n > 0 else 0
    factor = (1 + i) ** n
    return pv * (i * factor) / (factor - 1)


def fmt(value: float) -> str:
    """Format number as R$ X.XXX,XX for display."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ===========================================================================
# 1. Revisao de Emprestimo / Financiamento
# ===========================================================================
# Test case: Emprestimo R$10.000, taxa contratada 3%/mes, prazo 24 meses,
#   taxa correta 1.5%/mes (media BCB), parcela atual R$590.47
#   PMT(10000, 0.03, 24) = 590.47, PMT(10000, 0.015, 24) = 499.24
#   Diferenca mensal: R$91.23, total pago a mais: R$2,189.52
#
# Fundamentacao legal:
# - CDC Art. 6, V (revisao contratual por onerosidade excessiva)
# - CC Art. 591 (taxa media de mercado como parametro)
# - Sumula 530 STJ (taxa media BCB como referencia)

def calcular_revisao_emprestimo(
    valor_emprestado: float,
    taxa_contratada: float,
    prazo_meses: int,
    taxa_correta: float,
    parcela_atual: float,
) -> dict:
    """
    Calcula revisao de emprestimo comparando taxa contratada vs taxa correta.

    Args:
        valor_emprestado: Principal (R$)
        taxa_contratada: Taxa mensal contratada (% ao mes)
        prazo_meses: Prazo em meses
        taxa_correta: Taxa mensal correta / referencia BCB (% ao mes)
        parcela_atual: Parcela atualmente cobrada (R$)
    """
    i_contratada = taxa_contratada / 100
    i_correta = taxa_correta / 100

    parcela_contratada = pmt(valor_emprestado, i_contratada, prazo_meses)
    parcela_correta = pmt(valor_emprestado, i_correta, prazo_meses)

    diferenca_mensal = parcela_contratada - parcela_correta
    total_contratado = parcela_contratada * prazo_meses
    total_correto = parcela_correta * prazo_meses
    total_pago_a_mais = total_contratado - total_correto

    # Se parcela informada difere da calculada, usar a informada
    diferenca_real = parcela_atual - parcela_correta
    total_pago_real = parcela_atual * prazo_meses
    restituir = total_pago_real - total_correto

    juros_total_contratado = total_contratado - valor_emprestado
    juros_total_correto = total_correto - valor_emprestado

    return {
        "valor_emprestado": valor_emprestado,
        "taxa_contratada": taxa_contratada,
        "taxa_correta": taxa_correta,
        "prazo_meses": prazo_meses,
        "parcela_contratada": round(parcela_contratada, 2),
        "parcela_correta": round(parcela_correta, 2),
        "parcela_atual": parcela_atual,
        "diferenca_mensal": round(diferenca_mensal, 2),
        "diferenca_real": round(diferenca_real, 2),
        "total_contratado": round(total_contratado, 2),
        "total_correto": round(total_correto, 2),
        "total_pago_a_mais": round(total_pago_a_mais, 2),
        "restituir": round(restituir, 2),
        "juros_total_contratado": round(juros_total_contratado, 2),
        "juros_total_correto": round(juros_total_correto, 2),
        "economia_percentual": round((total_pago_a_mais / total_contratado) * 100, 2) if total_contratado > 0 else 0,
        "fundamentacao": [
            "CDC Art. 6, V - Direito a revisao contratual por onerosidade excessiva",
            "CC Art. 591 - Taxa media de mercado como parametro justo",
            "Sumula 530 STJ - Taxa media BCB como referencia para contratos bancarios",
            "CC Art. 404 - Perdas e danos incluem juros, correcao e honorarios",
        ],
    }


@router.get("/revisao-emprestimo", response_class=HTMLResponse)
async def revisao_emprestimo_form(request: Request, db: Session = Depends(get_db)):
    ctx = get_context(request, db, resultado=None, form=None, error=None)
    return templates.TemplateResponse("app/tools/revisao_emprestimo.html", ctx)


@router.post("/revisao-emprestimo/calcular", response_class=HTMLResponse)
async def revisao_emprestimo_calcular(
    request: Request,
    valor_emprestado: float = Form(...),
    taxa_contratada: float = Form(...),
    prazo_meses: int = Form(...),
    taxa_correta: float = Form(...),
    parcela_atual: float = Form(0),
    db: Session = Depends(get_db),
):
    form = {
        "valor_emprestado": valor_emprestado,
        "taxa_contratada": taxa_contratada,
        "prazo_meses": prazo_meses,
        "taxa_correta": taxa_correta,
        "parcela_atual": parcela_atual,
    }
    error = None
    resultado = None
    try:
        if valor_emprestado <= 0:
            raise ValueError("Valor emprestado deve ser positivo")
        if prazo_meses <= 0:
            raise ValueError("Prazo deve ser positivo")
        if parcela_atual == 0:
            # Auto-calculate parcela from contracted rate
            parcela_atual = pmt(valor_emprestado, taxa_contratada / 100, prazo_meses)
            form["parcela_atual"] = round(parcela_atual, 2)
        resultado = calcular_revisao_emprestimo(
            valor_emprestado, taxa_contratada, prazo_meses, taxa_correta, parcela_atual
        )
    except Exception as e:
        error = str(e)
        logger.exception("Erro no calculo de revisao de emprestimo")

    ctx = get_context(request, db, resultado=resultado, form=form, error=error)
    return templates.TemplateResponse("app/tools/revisao_emprestimo.html", ctx)


# ===========================================================================
# 2. Superendividamento
# ===========================================================================
# Test case: Renda R$3.000, despesas essenciais R$1.200
#   Dividas: [Cartao R$5000 parc R$500 taxa 12%, Emprestimo R$10000 parc R$800 taxa 3%]
#   Soma parcelas: R$1.300, comprometimento: 43.3%
#   Minimo existencial: max(25%*1518, 1200) = max(379.50, 1200) = R$1.200
#   Disponivel: 3000 - 1200 = R$1.800 (pode pagar todas as parcelas)
#
# Fundamentacao legal:
# - Lei 14.181/2021 (Superendividamento)
# - CDC Art. 104-A (Processo de repactuacao)
# - CDC Art. 104-B (Plano de pagamento)
# - CDC Art. 54-A a 54-G (Prevencao)

def calcular_superendividamento(
    renda_mensal: float,
    despesas_essenciais: float,
    dividas: list,
) -> dict:
    """
    Analisa superendividamento conforme Lei 14.181/2021.

    Args:
        renda_mensal: Renda bruta mensal (R$)
        despesas_essenciais: Despesas fixas essenciais (R$)
        dividas: Lista de dicts {nome, valor_total, parcela, taxa_mensal}
    """
    soma_parcelas = sum(d["parcela"] for d in dividas)
    comprometimento = (soma_parcelas / renda_mensal * 100) if renda_mensal > 0 else 0

    # Minimo existencial: maior entre 25% do SM e despesas essenciais informadas
    minimo_existencial_sm = 0.25 * SALARIO_MINIMO
    minimo_existencial = max(minimo_existencial_sm, despesas_essenciais)

    disponivel_mensal = renda_mensal - minimo_existencial
    if disponivel_mensal < 0:
        disponivel_mensal = 0

    # Classificacao
    superendividado = comprometimento > 30 or soma_parcelas > disponivel_mensal

    # Plano de pagamento sugerido: proporcionalmente entre as dividas
    plano = []
    for d in dividas:
        proporcao = (d["parcela"] / soma_parcelas) if soma_parcelas > 0 else 0
        parcela_sugerida = round(disponivel_mensal * proporcao, 2)
        meses_para_quitar = math.ceil(d["valor_total"] / parcela_sugerida) if parcela_sugerida > 0 else 0
        plano.append({
            "nome": d["nome"],
            "valor_total": d["valor_total"],
            "parcela_atual": d["parcela"],
            "taxa_mensal": d["taxa_mensal"],
            "parcela_sugerida": parcela_sugerida,
            "meses_para_quitar": meses_para_quitar,
            "proporcao": round(proporcao * 100, 1),
        })

    return {
        "renda_mensal": renda_mensal,
        "despesas_essenciais": despesas_essenciais,
        "soma_parcelas": round(soma_parcelas, 2),
        "comprometimento": round(comprometimento, 1),
        "minimo_existencial": round(minimo_existencial, 2),
        "minimo_existencial_sm": round(minimo_existencial_sm, 2),
        "disponivel_mensal": round(disponivel_mensal, 2),
        "superendividado": superendividado,
        "num_dividas": len(dividas),
        "total_dividas": round(sum(d["valor_total"] for d in dividas), 2),
        "plano": plano,
        "fundamentacao": [
            "Lei 14.181/2021 - Lei do Superendividamento",
            "CDC Art. 104-A - Processo de repactuacao de dividas",
            "CDC Art. 104-B - Plano de pagamento compulsorio (max 5 anos)",
            "CDC Art. 54-A a 54-G - Prevencao do superendividamento",
            "Preservacao do minimo existencial (25% do salario minimo)",
        ],
    }


@router.get("/superendividamento", response_class=HTMLResponse)
async def superendividamento_form(request: Request, db: Session = Depends(get_db)):
    ctx = get_context(request, db, resultado=None, form=None, error=None, salario_minimo=SALARIO_MINIMO)
    return templates.TemplateResponse("app/tools/superendividamento.html", ctx)


@router.post("/superendividamento/calcular", response_class=HTMLResponse)
async def superendividamento_calcular(
    request: Request,
    renda_mensal: float = Form(...),
    despesas_essenciais: float = Form(0),
    dividas_json: str = Form("[]"),
    db: Session = Depends(get_db),
):
    form = {
        "renda_mensal": renda_mensal,
        "despesas_essenciais": despesas_essenciais,
        "dividas_json": dividas_json,
    }
    error = None
    resultado = None
    try:
        if renda_mensal <= 0:
            raise ValueError("Renda mensal deve ser positiva")
        dividas = json.loads(dividas_json)
        if not dividas:
            raise ValueError("Adicione pelo menos uma divida")
        for d in dividas:
            d["parcela"] = float(d.get("parcela", 0))
            d["valor_total"] = float(d.get("valor_total", 0))
            d["taxa_mensal"] = float(d.get("taxa_mensal", 0))
            d["nome"] = str(d.get("nome", "Divida"))
        resultado = calcular_superendividamento(renda_mensal, despesas_essenciais, dividas)
    except json.JSONDecodeError:
        error = "Formato invalido de dividas"
    except Exception as e:
        error = str(e)
        logger.exception("Erro no calculo de superendividamento")

    ctx = get_context(request, db, resultado=resultado, form=form, error=error, salario_minimo=SALARIO_MINIMO)
    return templates.TemplateResponse("app/tools/superendividamento.html", ctx)


# ===========================================================================
# 3. Juros Compostos vs Simples (Anatocismo)
# ===========================================================================
# Test case: Capital R$10.000, taxa 2%/mes, 12 meses
#   Simples: M = 10000 * (1 + 0.02*12) = 10000 * 1.24 = R$12.400
#   Composto: M = 10000 * (1.02)^12 = 10000 * 1.26824 = R$12.682,42
#   Diferenca: R$282,42 (anatocismo)
#
# Fundamentacao legal:
# - Sumula 121 STF: "E vedada a capitalizacao de juros, ainda que expressamente
#   convencionada" (juros compostos proibidos salvo lei especial)
# - Sumula 596 STF: Instituicoes financeiras nao se submetem a Lei de Usura
# - MP 2.170-36/2001, Art. 5: Permite capitalizacao em contratos bancarios
# - STJ: Capitalizacao mensal permitida se pactuada (pos MP 2.170-36)

def calcular_juros_comparativo(
    capital: float,
    taxa_mensal: float,
    periodo_meses: int,
) -> dict:
    """
    Compara juros simples e compostos (anatocismo).

    Args:
        capital: Valor principal (R$)
        taxa_mensal: Taxa ao mes (%)
        periodo_meses: Numero de meses
    """
    i = taxa_mensal / 100

    # Montante simples: M = C * (1 + i*n)
    montante_simples = capital * (1 + i * periodo_meses)
    juros_simples = montante_simples - capital

    # Montante composto: M = C * (1+i)^n
    montante_composto = capital * ((1 + i) ** periodo_meses)
    juros_composto = montante_composto - capital

    # Diferenca (quanto a mais com compostos = anatocismo)
    diferenca = montante_composto - montante_simples
    percentual_a_mais = (diferenca / montante_simples * 100) if montante_simples > 0 else 0

    # Tabela evolutiva mes a mes
    tabela = []
    saldo_simples = capital
    saldo_composto = capital
    for mes in range(1, periodo_meses + 1):
        juros_s_mes = capital * i  # juros simples sempre sobre capital original
        juros_c_mes = saldo_composto * i  # juros compostos sobre saldo acumulado
        saldo_simples = capital * (1 + i * mes)
        saldo_composto = capital * ((1 + i) ** mes)
        tabela.append({
            "mes": mes,
            "saldo_simples": round(saldo_simples, 2),
            "saldo_composto": round(saldo_composto, 2),
            "juros_simples_mes": round(juros_s_mes, 2),
            "juros_composto_mes": round(juros_c_mes, 2),
            "diferenca_acumulada": round(saldo_composto - saldo_simples, 2),
        })

    # Taxa equivalente anual
    taxa_anual_simples = taxa_mensal * 12
    taxa_anual_composta = ((1 + i) ** 12 - 1) * 100

    return {
        "capital": capital,
        "taxa_mensal": taxa_mensal,
        "periodo_meses": periodo_meses,
        "montante_simples": round(montante_simples, 2),
        "montante_composto": round(montante_composto, 2),
        "juros_simples": round(juros_simples, 2),
        "juros_composto": round(juros_composto, 2),
        "diferenca": round(diferenca, 2),
        "percentual_a_mais": round(percentual_a_mais, 2),
        "taxa_anual_simples": round(taxa_anual_simples, 2),
        "taxa_anual_composta": round(taxa_anual_composta, 2),
        "tabela": tabela,
        "fundamentacao": [
            "Sumula 121 STF - Vedacao a capitalizacao de juros (anatocismo)",
            "Sumula 596 STF - Instituicoes financeiras e a Lei de Usura",
            "MP 2.170-36/2001, Art. 5 - Capitalizacao em contratos bancarios",
            "STJ REsp 973.827/RS - Capitalizacao mensal permitida se expressamente pactuada",
        ],
    }


@router.get("/juros-simples-compostos", response_class=HTMLResponse)
async def juros_comparativo_form(request: Request, db: Session = Depends(get_db)):
    ctx = get_context(request, db, resultado=None, form=None, error=None)
    return templates.TemplateResponse("app/tools/juros_simples_compostos.html", ctx)


@router.post("/juros-simples-compostos/calcular", response_class=HTMLResponse)
async def juros_comparativo_calcular(
    request: Request,
    capital: float = Form(...),
    taxa_mensal: float = Form(...),
    periodo_meses: int = Form(...),
    db: Session = Depends(get_db),
):
    form = {
        "capital": capital,
        "taxa_mensal": taxa_mensal,
        "periodo_meses": periodo_meses,
    }
    error = None
    resultado = None
    try:
        if capital <= 0:
            raise ValueError("Capital deve ser positivo")
        if periodo_meses <= 0:
            raise ValueError("Periodo deve ser positivo")
        if periodo_meses > 600:
            raise ValueError("Periodo maximo: 600 meses (50 anos)")
        resultado = calcular_juros_comparativo(capital, taxa_mensal, periodo_meses)
    except Exception as e:
        error = str(e)
        logger.exception("Erro no calculo de juros comparativo")

    ctx = get_context(request, db, resultado=resultado, form=form, error=error)
    return templates.TemplateResponse("app/tools/juros_simples_compostos.html", ctx)


# ===========================================================================
# 4. Tabela Price vs SAC vs SACRE
# ===========================================================================
# Test case: Financiamento R$100.000, taxa 1%/mes, 120 meses
#   PRICE: parcela fixa = PMT(100000, 0.01, 120) = R$1.434,71
#     Total pago: R$172.165,20, Total juros: R$72.165,20
#   SAC: amortizacao = 100000/120 = R$833,33
#     1a parcela = 833.33 + 1000 = R$1.833,33
#     Ultima parcela = 833.33 + 8.33 = R$841,67
#     Total pago: R$160.500,00, Total juros: R$60.500,00
#   SACRE: parcela = amortizacao_sac + juros, recalculada periodicamente
#
# Fundamentacao legal:
# - CC Art. 591 - Juros e sistema de amortizacao devem ser transparentes
# - CDC Art. 46 - Direito a informacao clara sobre encargos
# - Resolucao BCB 3.517/2007 - Transparencia nas operacoes de credito

def calcular_price_sac_sacre(
    valor_financiado: float,
    taxa_mensal: float,
    prazo_meses: int,
) -> dict:
    """
    Gera tabela comparativa entre Price, SAC e SACRE.
    """
    i = taxa_mensal / 100

    # --- PRICE (parcelas fixas) ---
    parcela_price = pmt(valor_financiado, i, prazo_meses)
    saldo_price = valor_financiado
    total_juros_price = 0
    tabela_price = []
    for mes in range(1, prazo_meses + 1):
        juros_mes = saldo_price * i
        amort_mes = parcela_price - juros_mes
        saldo_price -= amort_mes
        total_juros_price += juros_mes
        tabela_price.append({
            "mes": mes,
            "parcela": round(parcela_price, 2),
            "juros": round(juros_mes, 2),
            "amortizacao": round(amort_mes, 2),
            "saldo": round(max(saldo_price, 0), 2),
        })
    total_price = parcela_price * prazo_meses

    # --- SAC (amortizacao constante) ---
    amort_sac = valor_financiado / prazo_meses
    saldo_sac = valor_financiado
    total_juros_sac = 0
    total_sac = 0
    tabela_sac = []
    for mes in range(1, prazo_meses + 1):
        juros_mes = saldo_sac * i
        parcela_mes = amort_sac + juros_mes
        saldo_sac -= amort_sac
        total_juros_sac += juros_mes
        total_sac += parcela_mes
        tabela_sac.append({
            "mes": mes,
            "parcela": round(parcela_mes, 2),
            "juros": round(juros_mes, 2),
            "amortizacao": round(amort_sac, 2),
            "saldo": round(max(saldo_sac, 0), 2),
        })

    # --- SACRE (Sistema de Amortizacao Crescente / Misto) ---
    # SACRE: parcela inicial = mesma do SAC, mas recalculada periodicamente
    # Parcela = amortizacao fixa do SAC + juros sobre saldo, mas com piso
    # Na pratica: parcela_sacre = media entre Price e SAC para cada mes
    saldo_sacre = valor_financiado
    total_juros_sacre = 0
    total_sacre = 0
    tabela_sacre = []
    amort_sacre = valor_financiado / prazo_meses
    for mes in range(1, prazo_meses + 1):
        juros_mes = saldo_sacre * i
        # SACRE: parcela recalculada = PMT sobre saldo restante pelo prazo restante
        prazo_restante = prazo_meses - mes + 1
        if prazo_restante > 0 and i > 0:
            parcela_sacre = pmt(saldo_sacre, i, prazo_restante)
        else:
            parcela_sacre = saldo_sacre + juros_mes
        amort_mes = parcela_sacre - juros_mes
        saldo_sacre -= amort_mes
        total_juros_sacre += juros_mes
        total_sacre += parcela_sacre
        tabela_sacre.append({
            "mes": mes,
            "parcela": round(parcela_sacre, 2),
            "juros": round(juros_mes, 2),
            "amortizacao": round(amort_mes, 2),
            "saldo": round(max(saldo_sacre, 0), 2),
        })

    # Resumo comparativo
    economia_sac_vs_price = total_price - total_sac
    economia_sacre_vs_price = total_price - total_sacre

    return {
        "valor_financiado": valor_financiado,
        "taxa_mensal": taxa_mensal,
        "prazo_meses": prazo_meses,
        "price": {
            "parcela_inicial": round(parcela_price, 2),
            "parcela_final": round(parcela_price, 2),
            "total_pago": round(total_price, 2),
            "total_juros": round(total_juros_price, 2),
            "tabela": tabela_price,
        },
        "sac": {
            "parcela_inicial": tabela_sac[0]["parcela"] if tabela_sac else 0,
            "parcela_final": tabela_sac[-1]["parcela"] if tabela_sac else 0,
            "total_pago": round(total_sac, 2),
            "total_juros": round(total_juros_sac, 2),
            "tabela": tabela_sac,
        },
        "sacre": {
            "parcela_inicial": tabela_sacre[0]["parcela"] if tabela_sacre else 0,
            "parcela_final": tabela_sacre[-1]["parcela"] if tabela_sacre else 0,
            "total_pago": round(total_sacre, 2),
            "total_juros": round(total_juros_sacre, 2),
            "tabela": tabela_sacre,
        },
        "economia_sac_vs_price": round(economia_sac_vs_price, 2),
        "economia_sacre_vs_price": round(economia_sacre_vs_price, 2),
        "fundamentacao": [
            "CC Art. 591 - Transparencia nos juros e sistema de amortizacao",
            "CDC Art. 46 - Direito a informacao clara sobre encargos financeiros",
            "Resolucao BCB 3.517/2007 - Transparencia nas operacoes de credito",
            "STJ - Tabela Price nao implica necessariamente anatocismo",
        ],
    }


@router.get("/price-sac-sacre", response_class=HTMLResponse)
async def price_sac_sacre_form(request: Request, db: Session = Depends(get_db)):
    ctx = get_context(request, db, resultado=None, form=None, error=None)
    return templates.TemplateResponse("app/tools/price_sac_sacre.html", ctx)


@router.post("/price-sac-sacre/calcular", response_class=HTMLResponse)
async def price_sac_sacre_calcular(
    request: Request,
    valor_financiado: float = Form(...),
    taxa_mensal: float = Form(...),
    prazo_meses: int = Form(...),
    db: Session = Depends(get_db),
):
    form = {
        "valor_financiado": valor_financiado,
        "taxa_mensal": taxa_mensal,
        "prazo_meses": prazo_meses,
    }
    error = None
    resultado = None
    try:
        if valor_financiado <= 0:
            raise ValueError("Valor financiado deve ser positivo")
        if prazo_meses <= 0:
            raise ValueError("Prazo deve ser positivo")
        if prazo_meses > 600:
            raise ValueError("Prazo maximo: 600 meses (50 anos)")
        resultado = calcular_price_sac_sacre(valor_financiado, taxa_mensal, prazo_meses)
    except Exception as e:
        error = str(e)
        logger.exception("Erro no calculo Price/SAC/SACRE")

    ctx = get_context(request, db, resultado=resultado, form=form, error=error)
    return templates.TemplateResponse("app/tools/price_sac_sacre.html", ctx)


# ===========================================================================
# 5. CET (Custo Efetivo Total)
# ===========================================================================
# Test case: Emprestimo R$10.000, taxa nominal 2%/mes, TAC R$500, IOF 3%,
#   seguro R$30/mes, prazo 12 meses
#   Valor liquido recebido = 10000 - 500 - 300 (IOF) = R$9.200
#   Parcela nominal = PMT(10000, 0.02, 12) = R$945,60
#   Parcela real = 945.60 + 30 = R$975,60
#   CET mensal = taxa que iguala 9200 = sum(975.60/(1+cet)^k) para k=1..12
#   CET > 2%/mes (porque inclui custos adicionais)
#
# Fundamentacao legal:
# - Resolucao BCB 3.517/2007 - Obrigatoriedade de informar CET
# - CDC Art. 52 - Informacao clara de juros e acrescimos
# - Circular BCB 3.593/2012 - Metodologia de calculo do CET

def calcular_cet(
    valor_emprestimo: float,
    taxa_nominal: float,
    tac: float,
    iof_percentual: float,
    seguro_mensal: float,
    prazo_meses: int,
    outras_tarifas: float = 0,
) -> dict:
    """
    Calcula CET (Custo Efetivo Total) do emprestimo.
    """
    i_nominal = taxa_nominal / 100

    # Custos iniciais
    iof_valor = valor_emprestimo * (iof_percentual / 100)
    custos_iniciais = tac + iof_valor + outras_tarifas
    valor_liquido = valor_emprestimo - custos_iniciais

    # Parcela nominal (sem seguro)
    parcela_nominal = pmt(valor_emprestimo, i_nominal, prazo_meses)
    # Parcela real (com seguro)
    parcela_real = parcela_nominal + seguro_mensal

    total_nominal = parcela_nominal * prazo_meses
    total_real = parcela_real * prazo_meses + custos_iniciais
    total_seguro = seguro_mensal * prazo_meses

    # Calculo do CET via Newton-Raphson
    # Encontrar taxa r tal que: valor_liquido = sum(parcela_real / (1+r)^k) para k=1..n
    # f(r) = sum(parcela_real / (1+r)^k) - valor_liquido = 0
    cet_mensal = i_nominal  # chute inicial
    for _ in range(200):
        vpv = 0
        dvpv = 0
        for k in range(1, prazo_meses + 1):
            denom = (1 + cet_mensal) ** k
            vpv += parcela_real / denom
            dvpv -= k * parcela_real / ((1 + cet_mensal) ** (k + 1))
        f_val = vpv - valor_liquido
        if abs(f_val) < 0.001:
            break
        if dvpv != 0:
            cet_mensal = cet_mensal - f_val / dvpv
        else:
            break

    cet_anual = ((1 + cet_mensal) ** 12 - 1) * 100
    taxa_anual_nominal = ((1 + i_nominal) ** 12 - 1) * 100

    # Composicao do custo
    custo_juros = total_nominal - valor_emprestimo
    custo_total = total_real - valor_emprestimo

    return {
        "valor_emprestimo": valor_emprestimo,
        "taxa_nominal": taxa_nominal,
        "tac": tac,
        "iof_percentual": iof_percentual,
        "iof_valor": round(iof_valor, 2),
        "seguro_mensal": seguro_mensal,
        "outras_tarifas": outras_tarifas,
        "prazo_meses": prazo_meses,
        "custos_iniciais": round(custos_iniciais, 2),
        "valor_liquido": round(valor_liquido, 2),
        "parcela_nominal": round(parcela_nominal, 2),
        "parcela_real": round(parcela_real, 2),
        "total_nominal": round(total_nominal, 2),
        "total_real": round(total_real, 2),
        "total_seguro": round(total_seguro, 2),
        "custo_juros": round(custo_juros, 2),
        "custo_total": round(custo_total, 2),
        "cet_mensal": round(cet_mensal * 100, 4),
        "cet_anual": round(cet_anual, 2),
        "taxa_anual_nominal": round(taxa_anual_nominal, 2),
        "diferenca_taxa": round(cet_mensal * 100 - taxa_nominal, 4),
        "diferenca_anual": round(cet_anual - taxa_anual_nominal, 2),
        "fundamentacao": [
            "Resolucao BCB 3.517/2007 - Obrigatoriedade de informar CET",
            "CDC Art. 52 - Informacao clara de juros, acrescimos e encargos",
            "Circular BCB 3.593/2012 - Metodologia de calculo do CET",
            "CDC Art. 6, III - Direito a informacao adequada sobre o produto",
        ],
    }


@router.get("/cet", response_class=HTMLResponse)
async def cet_form(request: Request, db: Session = Depends(get_db)):
    ctx = get_context(request, db, resultado=None, form=None, error=None)
    return templates.TemplateResponse("app/tools/cet.html", ctx)


@router.post("/cet/calcular", response_class=HTMLResponse)
async def cet_calcular(
    request: Request,
    valor_emprestimo: float = Form(...),
    taxa_nominal: float = Form(...),
    tac: float = Form(0),
    iof_percentual: float = Form(0),
    seguro_mensal: float = Form(0),
    prazo_meses: int = Form(...),
    outras_tarifas: float = Form(0),
    db: Session = Depends(get_db),
):
    form = {
        "valor_emprestimo": valor_emprestimo,
        "taxa_nominal": taxa_nominal,
        "tac": tac,
        "iof_percentual": iof_percentual,
        "seguro_mensal": seguro_mensal,
        "prazo_meses": prazo_meses,
        "outras_tarifas": outras_tarifas,
    }
    error = None
    resultado = None
    try:
        if valor_emprestimo <= 0:
            raise ValueError("Valor do emprestimo deve ser positivo")
        if prazo_meses <= 0:
            raise ValueError("Prazo deve ser positivo")
        resultado = calcular_cet(
            valor_emprestimo, taxa_nominal, tac, iof_percentual,
            seguro_mensal, prazo_meses, outras_tarifas
        )
    except Exception as e:
        error = str(e)
        logger.exception("Erro no calculo de CET")

    ctx = get_context(request, db, resultado=resultado, form=form, error=error)
    return templates.TemplateResponse("app/tools/cet.html", ctx)
