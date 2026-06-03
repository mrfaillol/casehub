"""
CaseHub Lite - Brazilian Tax Law Tools (Calculadoras Tributarias)
8 tax calculators for Brazilian law firms.

Routes:
    GET  /tools/itbi                      - ITBI calculator form
    POST /tools/itbi/calcular             - Calculate ITBI
    GET  /tools/itcmd                     - ITCMD calculator form
    POST /tools/itcmd/calcular            - Calculate ITCMD
    GET  /tools/ganho-capital             - IR Ganho de Capital form
    POST /tools/ganho-capital/calcular    - Calculate IR Ganho de Capital
    GET  /tools/simples-vs-presumido      - Simples vs Presumido vs Real form
    POST /tools/simples-vs-presumido/calcular
    GET  /tools/icms                      - ICMS calculator form
    POST /tools/icms/calcular             - Calculate ICMS
    GET  /tools/pis-cofins                - PIS/COFINS calculator form
    POST /tools/pis-cofins/calcular       - Calculate PIS/COFINS
    GET  /tools/iss                       - ISS calculator form
    POST /tools/iss/calcular              - Calculate ISS
    GET  /tools/cprb                      - CPRB calculator form
    POST /tools/cprb/calcular             - Calculate CPRB
"""
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from datetime import date, datetime
from typing import Optional
import logging
import math

logger = logging.getLogger(__name__)

from auth import get_current_user
from models import get_db
from i18n import get_translations
from core.template_config import templates, PREFIX

router = APIRouter(prefix="/tools", tags=["tools_tributario"])


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


def fmt(value: float) -> str:
    """Format number as Brazilian currency string."""
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ===========================================================================
# 1. ITBI - Imposto Transmissao Bens Imoveis
# ===========================================================================
def calcular_itbi(valor_venal: float, aliquota: float) -> dict:
    """
    ITBI = valor_venal * aliquota
    Fundamentacao: CTN Art. 35-42, CF Art. 156, II
    """
    itbi = valor_venal * (aliquota / 100)
    return {
        "valor_venal": valor_venal,
        "aliquota": aliquota,
        "itbi": round(itbi, 2),
        "valor_venal_fmt": fmt(valor_venal),
        "itbi_fmt": fmt(round(itbi, 2)),
        "fundamentacao": [
            "CTN Art. 35-42 - Fato gerador e base de calculo do ITBI",
            "CF Art. 156, II - Competencia municipal",
            "Aliquota definida por lei municipal (geralmente 2-3%)",
        ],
    }


@router.get("/itbi", response_class=HTMLResponse)
async def itbi_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("app/tools/itbi.html", get_context(request, db))


@router.post("/itbi/calcular", response_class=HTMLResponse)
async def itbi_calcular(
    request: Request,
    valor_venal: float = Form(...),
    aliquota: float = Form(2.0),
    db: Session = Depends(get_db),
):
    resultado = calcular_itbi(valor_venal, aliquota)
    form = {"valor_venal": valor_venal, "aliquota": aliquota}
    return templates.TemplateResponse("app/tools/itbi.html", get_context(request, db, resultado=resultado, form=form))


# ===========================================================================
# 2. ITCMD - Imposto Transmissao Causa Mortis e Doacao
# ===========================================================================
# Aliquotas por UF (simplificado - valor unico ou faixa principal)
ITCMD_ALIQUOTAS = {
    "AC": 4.0, "AL": 4.0, "AM": 4.0, "AP": 4.0, "BA": 8.0,
    "CE": 8.0, "DF": 4.0, "ES": 4.0, "GO": 4.0, "MA": 7.0,
    "MG": 5.0, "MS": 6.0, "MT": 4.0, "PA": 4.0, "PB": 8.0,
    "PE": 5.0, "PI": 4.0, "PR": 4.0, "RJ": 8.0, "RN": 6.0,
    "RO": 4.0, "RR": 4.0, "RS": 4.0, "SC": 8.0, "SE": 8.0,
    "SP": 4.0, "TO": 4.0,
}

# SP progressivo (Lei 10.705/00 - aliquota unica de 4%, mas proposta de progressividade)
# RJ progressivo (Lei 7.174/15)
ITCMD_PROGRESSIVO_RJ = [
    (400_000, 4.0),
    (1_000_000, 5.0),
    (2_000_000, 6.0),
    (4_000_000, 7.0),
    (float("inf"), 8.0),
]


def calcular_itcmd(valor_bens: float, uf: str, tipo: str) -> dict:
    """
    ITCMD = valor_bens * aliquota(UF)
    Fundamentacao: CF Art. 155, II; Resolucao SF 9/92 (teto 8%)
    """
    uf = uf.upper()
    aliquota = ITCMD_ALIQUOTAS.get(uf, 4.0)
    nota_progressivo = ""

    # RJ tem aliquota progressiva
    if uf == "RJ":
        for limite, aliq in ITCMD_PROGRESSIVO_RJ:
            if valor_bens <= limite:
                aliquota = aliq
                break
        nota_progressivo = f"RJ: aliquota progressiva conforme Lei 7.174/15 - {aliquota}% para valores ate R$ {fmt(limite) if limite != float('inf') else 'acima'}"

    itcmd = valor_bens * (aliquota / 100)

    return {
        "valor_bens": valor_bens,
        "uf": uf,
        "tipo": tipo,
        "aliquota": aliquota,
        "itcmd": round(itcmd, 2),
        "valor_bens_fmt": fmt(valor_bens),
        "itcmd_fmt": fmt(round(itcmd, 2)),
        "nota_progressivo": nota_progressivo,
        "fundamentacao": [
            "CF Art. 155, II - Competencia estadual (ITCMD)",
            f"Aliquota {uf}: {aliquota}%",
            "Resolucao SF 9/92 - Teto de 8%",
            f"Tipo: {'Heranca (causa mortis)' if tipo == 'heranca' else 'Doacao'}",
        ],
    }


@router.get("/itcmd", response_class=HTMLResponse)
async def itcmd_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("app/tools/itcmd.html", get_context(request, db, ufs=sorted(ITCMD_ALIQUOTAS.keys())))


@router.post("/itcmd/calcular", response_class=HTMLResponse)
async def itcmd_calcular(
    request: Request,
    valor_bens: float = Form(...),
    uf: str = Form(...),
    tipo: str = Form("heranca"),
    db: Session = Depends(get_db),
):
    resultado = calcular_itcmd(valor_bens, uf, tipo)
    form = {"valor_bens": valor_bens, "uf": uf, "tipo": tipo}
    return templates.TemplateResponse("app/tools/itcmd.html", get_context(request, db, resultado=resultado, form=form, ufs=sorted(ITCMD_ALIQUOTAS.keys())))


# ===========================================================================
# 3. IR sobre Ganho de Capital
# ===========================================================================
FAIXAS_GANHO_CAPITAL = [
    (5_000_000, 0.15),
    (10_000_000, 0.175),
    (30_000_000, 0.20),
    (float("inf"), 0.225),
]


def calcular_ganho_capital(
    valor_venda: float,
    valor_aquisicao: float,
    data_aquisicao: date,
    tipo_bem: str,
) -> dict:
    """
    IR Ganho Capital: faixas progressivas 15-22.5%
    Fundamentacao: Lei 7.713/88, IN RFB 599/05, Lei 13.259/16
    """
    ganho_bruto = valor_venda - valor_aquisicao
    if ganho_bruto <= 0:
        return {
            "valor_venda": valor_venda,
            "valor_aquisicao": valor_aquisicao,
            "ganho_bruto": 0,
            "reducao_percentual": 0,
            "ganho_tributavel": 0,
            "ir_total": 0,
            "aliquota_efetiva": 0,
            "detalhamento_faixas": [],
            "valor_venda_fmt": fmt(valor_venda),
            "valor_aquisicao_fmt": fmt(valor_aquisicao),
            "ganho_bruto_fmt": "0,00",
            "ganho_tributavel_fmt": "0,00",
            "ir_total_fmt": "0,00",
            "nota_reducao": "Sem ganho de capital - nao ha imposto a pagar.",
            "fundamentacao": ["Sem ganho de capital tributavel."],
        }

    # Reducao por tempo para imoveis adquiridos antes de 1988
    reducao_percentual = 0.0
    nota_reducao = ""
    if tipo_bem == "imovel" and data_aquisicao.year <= 1988:
        # 5% por ano ate 1988 (max 100%)
        anos_ate_88 = 1988 - data_aquisicao.year
        reducao_percentual = min(anos_ate_88 * 5.0, 100.0)
        nota_reducao = f"Reducao de {reducao_percentual:.0f}% para imovel adquirido em {data_aquisicao.year} (Art. 18, Lei 7.713/88)"

    # Reducao adicional para imoveis residenciais (IN RFB 599/05)
    # Fator de reducao = 1 / (1.0035)^n, n = meses entre aquisicao e Jan/1996
    fator_reducao_inrfb = 1.0
    if tipo_bem == "imovel" and data_aquisicao < date(1996, 1, 1):
        meses = (1996 - data_aquisicao.year) * 12 + (1 - data_aquisicao.month)
        if meses > 0:
            fator_reducao_inrfb = 1.0 / (1.0035 ** meses)
            nota_reducao += f"\nFator reducao IN RFB 599/05: {fator_reducao_inrfb:.6f} ({meses} meses)"

    ganho_apos_reducao_percentual = ganho_bruto * (1 - reducao_percentual / 100)
    ganho_tributavel = ganho_apos_reducao_percentual * fator_reducao_inrfb
    ganho_tributavel = max(0, round(ganho_tributavel, 2))

    # Calculo progressivo por faixas
    restante = ganho_tributavel
    ir_total = 0
    detalhamento = []
    prev_limit = 0

    for limite, aliquota in FAIXAS_GANHO_CAPITAL:
        faixa_size = limite - prev_limit if limite != float("inf") else restante
        tributavel_faixa = min(restante, faixa_size)
        if tributavel_faixa <= 0:
            break
        ir_faixa = tributavel_faixa * aliquota
        ir_total += ir_faixa
        detalhamento.append({
            "faixa": f"Ate R$ {fmt(limite)}" if limite != float("inf") else f"Acima de R$ {fmt(prev_limit)}",
            "aliquota": f"{aliquota * 100:.1f}%",
            "base": fmt(tributavel_faixa),
            "ir": fmt(round(ir_faixa, 2)),
        })
        restante -= tributavel_faixa
        prev_limit = limite

    ir_total = round(ir_total, 2)
    aliquota_efetiva = (ir_total / ganho_tributavel * 100) if ganho_tributavel > 0 else 0

    return {
        "valor_venda": valor_venda,
        "valor_aquisicao": valor_aquisicao,
        "data_aquisicao": data_aquisicao.isoformat(),
        "tipo_bem": tipo_bem,
        "ganho_bruto": ganho_bruto,
        "reducao_percentual": reducao_percentual,
        "ganho_tributavel": ganho_tributavel,
        "ir_total": ir_total,
        "aliquota_efetiva": round(aliquota_efetiva, 2),
        "detalhamento_faixas": detalhamento,
        "valor_venda_fmt": fmt(valor_venda),
        "valor_aquisicao_fmt": fmt(valor_aquisicao),
        "ganho_bruto_fmt": fmt(ganho_bruto),
        "ganho_tributavel_fmt": fmt(ganho_tributavel),
        "ir_total_fmt": fmt(ir_total),
        "nota_reducao": nota_reducao,
        "fundamentacao": [
            "Lei 7.713/88 - IR sobre ganho de capital",
            "Lei 13.259/16 - Faixas progressivas (15%, 17.5%, 20%, 22.5%)",
            "IN RFB 599/05 - Fator de reducao para imoveis",
            "Art. 18, Lei 7.713/88 - Reducao 5%/ano para imoveis ate 1988",
        ],
    }


@router.get("/ganho-capital", response_class=HTMLResponse)
async def ganho_capital_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("app/tools/ganho_capital.html", get_context(request, db))


@router.post("/ganho-capital/calcular", response_class=HTMLResponse)
async def ganho_capital_calcular(
    request: Request,
    valor_venda: float = Form(...),
    valor_aquisicao: float = Form(...),
    data_aquisicao: str = Form(...),
    tipo_bem: str = Form("imovel"),
    db: Session = Depends(get_db),
):
    dt_aquisicao = date.fromisoformat(data_aquisicao)
    resultado = calcular_ganho_capital(valor_venda, valor_aquisicao, dt_aquisicao, tipo_bem)
    form = {"valor_venda": valor_venda, "valor_aquisicao": valor_aquisicao, "data_aquisicao": data_aquisicao, "tipo_bem": tipo_bem}
    return templates.TemplateResponse("app/tools/ganho_capital.html", get_context(request, db, resultado=resultado, form=form))


# ===========================================================================
# 4. Simples Nacional vs Lucro Presumido vs Lucro Real
# ===========================================================================
# Simples Nacional - Anexo I (Comercio) simplificado
SIMPLES_ANEXO_I = [
    (180_000, 0.04, 0),
    (360_000, 0.073, 5_940),
    (720_000, 0.095, 13_860),
    (1_800_000, 0.107, 22_500),
    (3_600_000, 0.143, 87_300),
    (4_800_000, 0.19, 378_000),
]

# Anexo III (Servicos)
SIMPLES_ANEXO_III = [
    (180_000, 0.06, 0),
    (360_000, 0.112, 9_360),
    (720_000, 0.135, 17_640),
    (1_800_000, 0.16, 35_640),
    (3_600_000, 0.21, 125_640),
    (4_800_000, 0.33, 648_000),
]

# Anexo V (Servicos - fator R < 28%)
SIMPLES_ANEXO_V = [
    (180_000, 0.155, 0),
    (360_000, 0.18, 4_500),
    (720_000, 0.195, 9_900),
    (1_800_000, 0.205, 17_100),
    (3_600_000, 0.23, 62_100),
    (4_800_000, 0.305, 540_000),
]


def aliquota_simples(faturamento: float, tabela: list) -> float:
    """Calcula aliquota efetiva do Simples Nacional."""
    for limite, aliq_nominal, deducao in tabela:
        if faturamento <= limite:
            aliq_efetiva = (faturamento * aliq_nominal - deducao) / faturamento
            return max(aliq_efetiva, 0)
    return tabela[-1][1]  # Excedeu - usa ultima faixa


def calcular_regimes(faturamento: float, atividade: str, folha: float) -> dict:
    """
    Comparativo Simples Nacional vs Lucro Presumido vs Lucro Real.
    Fundamentacao: LC 123/2006
    """
    fator_r = folha / faturamento if faturamento > 0 else 0

    # --- Simples Nacional ---
    simples_elegivel = faturamento <= 4_800_000
    if atividade == "comercio":
        tabela = SIMPLES_ANEXO_I
        anexo = "I"
    elif atividade == "servico":
        if fator_r >= 0.28:
            tabela = SIMPLES_ANEXO_III
            anexo = "III"
        else:
            tabela = SIMPLES_ANEXO_V
            anexo = "V"
    else:  # industria
        tabela = SIMPLES_ANEXO_I  # Anexo II e similar ao I
        anexo = "II"

    if simples_elegivel:
        aliq_simples = aliquota_simples(faturamento, tabela)
        simples_total = faturamento * aliq_simples
    else:
        aliq_simples = 0
        simples_total = 0

    # --- Lucro Presumido ---
    if atividade == "comercio":
        presuncao_irpj = 0.08
        presuncao_csll = 0.12
    elif atividade == "servico":
        presuncao_irpj = 0.32
        presuncao_csll = 0.32
    else:  # industria
        presuncao_irpj = 0.08
        presuncao_csll = 0.12

    base_irpj = faturamento * presuncao_irpj
    irpj = base_irpj * 0.15
    # Adicional IRPJ (10% sobre o que exceder R$ 60k/trimestre = R$ 240k/ano)
    if base_irpj > 240_000:
        irpj += (base_irpj - 240_000) * 0.10

    base_csll = faturamento * presuncao_csll
    csll = base_csll * 0.09

    pis_presumido = faturamento * 0.0065
    cofins_presumido = faturamento * 0.03
    cpp_presumido = folha * 0.20  # 20% patronal

    presumido_total = irpj + csll + pis_presumido + cofins_presumido + cpp_presumido

    # --- Lucro Real (simplificado) ---
    # Lucro estimado = 20% do faturamento (simplificacao)
    lucro_estimado = faturamento * 0.20
    irpj_real = lucro_estimado * 0.15
    if lucro_estimado > 240_000:
        irpj_real += (lucro_estimado - 240_000) * 0.10
    csll_real = lucro_estimado * 0.09

    pis_real = faturamento * 0.0165  # Nao cumulativo
    cofins_real = faturamento * 0.076  # Nao cumulativo
    # Creditos estimados (30% dos insumos)
    creditos_pis_cofins = (faturamento * 0.30) * (0.0165 + 0.076)
    pis_real -= creditos_pis_cofins * (0.0165 / (0.0165 + 0.076))
    cofins_real -= creditos_pis_cofins * (0.076 / (0.0165 + 0.076))
    pis_real = max(0, pis_real)
    cofins_real = max(0, cofins_real)

    cpp_real = folha * 0.20
    real_total = irpj_real + csll_real + pis_real + cofins_real + cpp_real

    # Melhor regime
    opcoes = {}
    if simples_elegivel:
        opcoes["Simples Nacional"] = simples_total
    opcoes["Lucro Presumido"] = presumido_total
    opcoes["Lucro Real"] = real_total

    melhor = min(opcoes, key=opcoes.get)

    return {
        "faturamento": faturamento,
        "atividade": atividade,
        "folha": folha,
        "fator_r": round(fator_r * 100, 2),
        "faturamento_fmt": fmt(faturamento),
        "folha_fmt": fmt(folha),
        "simples": {
            "elegivel": simples_elegivel,
            "anexo": anexo,
            "aliquota_efetiva": round(aliq_simples * 100, 2) if simples_elegivel else 0,
            "total": round(simples_total, 2),
            "total_fmt": fmt(round(simples_total, 2)) if simples_elegivel else "N/A",
            "percentual": round(simples_total / faturamento * 100, 2) if simples_elegivel and faturamento > 0 else 0,
        },
        "presumido": {
            "irpj": round(irpj, 2),
            "csll": round(csll, 2),
            "pis": round(pis_presumido, 2),
            "cofins": round(cofins_presumido, 2),
            "cpp": round(cpp_presumido, 2),
            "total": round(presumido_total, 2),
            "total_fmt": fmt(round(presumido_total, 2)),
            "percentual": round(presumido_total / faturamento * 100, 2) if faturamento > 0 else 0,
            "irpj_fmt": fmt(round(irpj, 2)),
            "csll_fmt": fmt(round(csll, 2)),
            "pis_fmt": fmt(round(pis_presumido, 2)),
            "cofins_fmt": fmt(round(cofins_presumido, 2)),
            "cpp_fmt": fmt(round(cpp_presumido, 2)),
        },
        "real": {
            "irpj": round(irpj_real, 2),
            "csll": round(csll_real, 2),
            "pis": round(pis_real, 2),
            "cofins": round(cofins_real, 2),
            "cpp": round(cpp_real, 2),
            "total": round(real_total, 2),
            "total_fmt": fmt(round(real_total, 2)),
            "percentual": round(real_total / faturamento * 100, 2) if faturamento > 0 else 0,
            "irpj_fmt": fmt(round(irpj_real, 2)),
            "csll_fmt": fmt(round(csll_real, 2)),
            "pis_fmt": fmt(round(pis_real, 2)),
            "cofins_fmt": fmt(round(cofins_real, 2)),
            "cpp_fmt": fmt(round(cpp_real, 2)),
        },
        "melhor_regime": melhor,
        "economia": round(max(opcoes.values()) - min(opcoes.values()), 2),
        "economia_fmt": fmt(round(max(opcoes.values()) - min(opcoes.values()), 2)),
        "fundamentacao": [
            "LC 123/2006 - Simples Nacional",
            f"Anexo {anexo} - Fator R: {round(fator_r * 100, 2)}%",
            "Lei 9.249/95 - Lucro Presumido",
            "Lei 9.430/96 - Lucro Real",
            "Lei 10.637/02 (PIS) e Lei 10.833/03 (COFINS) - Nao cumulativo",
        ],
    }


@router.get("/simples-vs-presumido", response_class=HTMLResponse)
async def simples_vs_presumido_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("app/tools/simples_vs_presumido.html", get_context(request, db))


@router.post("/simples-vs-presumido/calcular", response_class=HTMLResponse)
async def simples_vs_presumido_calcular(
    request: Request,
    faturamento: float = Form(...),
    atividade: str = Form("comercio"),
    folha: float = Form(0),
    db: Session = Depends(get_db),
):
    resultado = calcular_regimes(faturamento, atividade, folha)
    form = {"faturamento": faturamento, "atividade": atividade, "folha": folha}
    return templates.TemplateResponse("app/tools/simples_vs_presumido.html", get_context(request, db, resultado=resultado, form=form))


# ===========================================================================
# 5. ICMS (Calculo por Dentro)
# ===========================================================================
def calcular_icms(
    valor_produto: float,
    aliquota_interna: float,
    icms_st: bool = False,
    mva: float = 0,
) -> dict:
    """
    ICMS por dentro: base = valor / (1 - aliquota)
    Fundamentacao: LC 87/96 (Lei Kandir)
    """
    aliq = aliquota_interna / 100
    base_calculo = valor_produto / (1 - aliq) if aliq < 1 else valor_produto
    icms_proprio = base_calculo * aliq

    icms_st_valor = 0
    base_st = 0
    if icms_st and mva > 0:
        base_st = base_calculo * (1 + mva / 100)
        icms_st_valor = base_st * aliq - icms_proprio
        icms_st_valor = max(0, icms_st_valor)

    total = icms_proprio + icms_st_valor

    return {
        "valor_produto": valor_produto,
        "aliquota_interna": aliquota_interna,
        "icms_st": icms_st,
        "mva": mva,
        "base_calculo": round(base_calculo, 2),
        "icms_proprio": round(icms_proprio, 2),
        "base_st": round(base_st, 2),
        "icms_st_valor": round(icms_st_valor, 2),
        "total": round(total, 2),
        "valor_produto_fmt": fmt(valor_produto),
        "base_calculo_fmt": fmt(round(base_calculo, 2)),
        "icms_proprio_fmt": fmt(round(icms_proprio, 2)),
        "base_st_fmt": fmt(round(base_st, 2)),
        "icms_st_valor_fmt": fmt(round(icms_st_valor, 2)),
        "total_fmt": fmt(round(total, 2)),
        "fundamentacao": [
            "LC 87/96 (Lei Kandir) - ICMS",
            "Calculo por dentro: Base = Valor / (1 - Aliquota)",
            "ICMS-ST: Base ST = Base * (1 + MVA); ICMS-ST = Base_ST * Aliq - ICMS proprio",
            "CF Art. 155, II - Competencia estadual",
        ],
    }


@router.get("/icms", response_class=HTMLResponse)
async def icms_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("app/tools/icms.html", get_context(request, db))


@router.post("/icms/calcular", response_class=HTMLResponse)
async def icms_calcular(
    request: Request,
    valor_produto: float = Form(...),
    aliquota_interna: float = Form(18.0),
    icms_st: str = Form("nao"),
    mva: float = Form(0),
    db: Session = Depends(get_db),
):
    resultado = calcular_icms(valor_produto, aliquota_interna, icms_st == "sim", mva)
    form = {"valor_produto": valor_produto, "aliquota_interna": aliquota_interna, "icms_st": icms_st, "mva": mva}
    return templates.TemplateResponse("app/tools/icms.html", get_context(request, db, resultado=resultado, form=form))


# ===========================================================================
# 6. PIS/COFINS (Cumulativo vs Nao-Cumulativo)
# ===========================================================================
def calcular_pis_cofins(
    receita_bruta: float,
    regime: str,
    creditos: float = 0,
) -> dict:
    """
    Cumulativo: PIS 0.65% + COFINS 3%
    Nao-cumulativo: PIS 1.65% + COFINS 7.6% - creditos
    Fundamentacao: Lei 10.637/02 (PIS), Lei 10.833/03 (COFINS)
    """
    if regime == "cumulativo":
        pis_aliq = 0.0065
        cofins_aliq = 0.03
        pis = receita_bruta * pis_aliq
        cofins = receita_bruta * cofins_aliq
        pis_credito = 0
        cofins_credito = 0
    else:
        pis_aliq = 0.0165
        cofins_aliq = 0.076
        pis_bruto = receita_bruta * pis_aliq
        cofins_bruto = receita_bruta * cofins_aliq
        total_aliq = pis_aliq + cofins_aliq
        pis_credito = creditos * (pis_aliq / total_aliq) if total_aliq > 0 else 0
        cofins_credito = creditos * (cofins_aliq / total_aliq) if total_aliq > 0 else 0
        pis = max(0, pis_bruto - pis_credito)
        cofins = max(0, cofins_bruto - cofins_credito)

    total = pis + cofins
    carga_efetiva = (total / receita_bruta * 100) if receita_bruta > 0 else 0

    return {
        "receita_bruta": receita_bruta,
        "regime": regime,
        "creditos": creditos,
        "pis_aliquota": pis_aliq * 100,
        "cofins_aliquota": cofins_aliq * 100,
        "pis": round(pis, 2),
        "cofins": round(cofins, 2),
        "pis_credito": round(pis_credito, 2),
        "cofins_credito": round(cofins_credito, 2),
        "total": round(total, 2),
        "carga_efetiva": round(carga_efetiva, 2),
        "receita_bruta_fmt": fmt(receita_bruta),
        "creditos_fmt": fmt(creditos),
        "pis_fmt": fmt(round(pis, 2)),
        "cofins_fmt": fmt(round(cofins, 2)),
        "pis_credito_fmt": fmt(round(pis_credito, 2)),
        "cofins_credito_fmt": fmt(round(cofins_credito, 2)),
        "total_fmt": fmt(round(total, 2)),
        "fundamentacao": [
            "Lei 10.637/02 - PIS nao cumulativo (1.65%)",
            "Lei 10.833/03 - COFINS nao cumulativo (7.6%)",
            "Lei 9.718/98 - PIS/COFINS cumulativo (0.65% / 3%)",
            f"Regime: {'Cumulativo (Lucro Presumido)' if regime == 'cumulativo' else 'Nao-Cumulativo (Lucro Real)'}",
        ],
    }


@router.get("/pis-cofins", response_class=HTMLResponse)
async def pis_cofins_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("app/tools/pis_cofins.html", get_context(request, db))


@router.post("/pis-cofins/calcular", response_class=HTMLResponse)
async def pis_cofins_calcular(
    request: Request,
    receita_bruta: float = Form(...),
    regime: str = Form("cumulativo"),
    creditos: float = Form(0),
    db: Session = Depends(get_db),
):
    resultado = calcular_pis_cofins(receita_bruta, regime, creditos)
    form = {"receita_bruta": receita_bruta, "regime": regime, "creditos": creditos}
    return templates.TemplateResponse("app/tools/pis_cofins.html", get_context(request, db, resultado=resultado, form=form))


# ===========================================================================
# 7. ISS (Imposto sobre Servicos)
# ===========================================================================
def calcular_iss(
    valor_servico: float,
    aliquota: float,
    municipio: str = "",
) -> dict:
    """
    ISS = valor * aliquota (minimo 2%, maximo 5%)
    Fundamentacao: LC 116/2003
    """
    aliquota = max(2.0, min(5.0, aliquota))
    iss = valor_servico * (aliquota / 100)

    return {
        "valor_servico": valor_servico,
        "aliquota": aliquota,
        "municipio": municipio,
        "iss": round(iss, 2),
        "valor_servico_fmt": fmt(valor_servico),
        "iss_fmt": fmt(round(iss, 2)),
        "fundamentacao": [
            "LC 116/2003 - ISS",
            f"Aliquota: {aliquota}% (minimo 2%, maximo 5%)",
            "CF Art. 156, III - Competencia municipal",
            "LC 157/2016 - Aliquota minima de 2%",
            f"Municipio: {municipio}" if municipio else "Municipio nao informado",
        ],
    }


@router.get("/iss", response_class=HTMLResponse)
async def iss_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("app/tools/iss.html", get_context(request, db))


@router.post("/iss/calcular", response_class=HTMLResponse)
async def iss_calcular(
    request: Request,
    valor_servico: float = Form(...),
    aliquota: float = Form(5.0),
    municipio: str = Form(""),
    db: Session = Depends(get_db),
):
    resultado = calcular_iss(valor_servico, aliquota, municipio)
    form = {"valor_servico": valor_servico, "aliquota": aliquota, "municipio": municipio}
    return templates.TemplateResponse("app/tools/iss.html", get_context(request, db, resultado=resultado, form=form))


# ===========================================================================
# 8. CPRB - Contribuicao Previdenciaria sobre Receita Bruta
# ===========================================================================
CPRB_ALIQUOTAS = {
    "ti_tic": 4.5,
    "call_center": 3.0,
    "transporte": 1.5,
    "construcao_civil": 4.5,
    "comunicacao": 1.5,
    "textil": 1.5,
    "calcados": 1.5,
    "maquinas": 1.0,
    "outras": 4.5,
}


def calcular_cprb(
    folha: float,
    receita_bruta: float,
    atividade: str,
) -> dict:
    """
    Sobre folha: 20% patronal
    Sobre receita: 1-4.5% conforme atividade (CPRB)
    Fundamentacao: Lei 12.546/2011
    """
    # Sobre folha (regime normal)
    contribuicao_folha = folha * 0.20

    # Sobre receita (CPRB - desoneracao)
    aliquota_cprb = CPRB_ALIQUOTAS.get(atividade, 4.5)
    contribuicao_receita = receita_bruta * (aliquota_cprb / 100)

    economia = contribuicao_folha - contribuicao_receita
    melhor = "CPRB (Receita)" if contribuicao_receita < contribuicao_folha else "CPP (Folha)"

    return {
        "folha": folha,
        "receita_bruta": receita_bruta,
        "atividade": atividade,
        "contribuicao_folha": round(contribuicao_folha, 2),
        "contribuicao_receita": round(contribuicao_receita, 2),
        "aliquota_cprb": aliquota_cprb,
        "economia": round(abs(economia), 2),
        "melhor": melhor,
        "folha_fmt": fmt(folha),
        "receita_bruta_fmt": fmt(receita_bruta),
        "contribuicao_folha_fmt": fmt(round(contribuicao_folha, 2)),
        "contribuicao_receita_fmt": fmt(round(contribuicao_receita, 2)),
        "economia_fmt": fmt(round(abs(economia), 2)),
        "fundamentacao": [
            "Lei 12.546/2011 - Desoneracao da folha (CPRB)",
            "Lei 8.212/91 - Contribuicao patronal sobre folha (20%)",
            f"Atividade: {atividade.replace('_', ' ').title()} - Aliquota CPRB: {aliquota_cprb}%",
            "Opcao pela CPRB e irretratavel para o ano-calendario",
        ],
    }


@router.get("/cprb", response_class=HTMLResponse)
async def cprb_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse("app/tools/cprb.html", get_context(request, db, atividades=CPRB_ALIQUOTAS))


@router.post("/cprb/calcular", response_class=HTMLResponse)
async def cprb_calcular(
    request: Request,
    folha: float = Form(...),
    receita_bruta: float = Form(...),
    atividade: str = Form("outras"),
    db: Session = Depends(get_db),
):
    resultado = calcular_cprb(folha, receita_bruta, atividade)
    form = {"folha": folha, "receita_bruta": receita_bruta, "atividade": atividade}
    return templates.TemplateResponse("app/tools/cprb.html", get_context(request, db, resultado=resultado, form=form, atividades=CPRB_ALIQUOTAS))
