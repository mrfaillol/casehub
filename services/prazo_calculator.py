"""Calculadora determinística de prazos processuais brasileiros.

Regras verificadas em 09/06/2026 contra textos consolidados do Planalto.
Referências: CPC art.219/220/224/231, CLT art.775/775-A, CPP art.798/798-A,
L9.099 art.12-A, L14.365/2022, L13.467/2017, L13.545/2017, L14.939/2024.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import List, Optional


# ---------------------------------------------------------------------------
# Feriados nacionais fixos (MM-DD)
# ---------------------------------------------------------------------------
_FERIADOS_FIXOS = {
    "01-01",  # Ano Novo
    "04-21",  # Tiradentes
    "05-01",  # Dia do Trabalho
    "09-07",  # Independência
    "10-12",  # Nossa Senhora Aparecida
    "11-02",  # Finados
    "11-15",  # Proclamação da República
    "11-20",  # Consciência Negra (L14.759/2023)
    "12-25",  # Natal
}


def _pascoa(ano: int) -> date:
    """Computus gregoriano (algoritmo de Meeus) — determinístico."""
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def feriados_nacionais(ano: int) -> set[date]:
    """Retorna o conjunto de feriados nacionais + forenses federais para o ano."""
    feriados: set[date] = set()
    for md in _FERIADOS_FIXOS:
        m, d = int(md[:2]), int(md[3:])
        try:
            feriados.add(date(ano, m, d))
        except ValueError:
            pass

    pascoa = _pascoa(ano)
    # Sexta-Feira Santa (Paixão) = Páscoa - 2 dias
    feriados.add(pascoa - timedelta(days=2))
    # Segunda e Terça de Carnaval (feriado JF e muitos tribunais)
    feriados.add(pascoa - timedelta(days=48))
    feriados.add(pascoa - timedelta(days=47))
    # Corpus Christi (ponto facultativo federal / feriado na maioria dos tribunais)
    feriados.add(pascoa + timedelta(days=60))
    return feriados


def _is_recesso(d: date) -> bool:
    """Recesso universal 20/dez a 20/jan (CPC 220, CLT 775-A, CPP 798-A)."""
    m, dia = d.month, d.day
    return (m == 12 and dia >= 20) or (m == 1 and dia <= 20)


def _is_util(d: date, feriados_extras: Optional[set[date]] = None) -> bool:
    """Dia útil forense: segunda a sexta, não feriado, não recesso."""
    if d.weekday() >= 5:  # sáb=5, dom=6
        return False
    if _is_recesso(d):
        return False
    nac = feriados_nacionais(d.year)
    if d in nac:
        return False
    if feriados_extras and d in feriados_extras:
        return False
    return True


def _proximo_util(d: date, feriados_extras: Optional[set[date]] = None) -> date:
    while not _is_util(d, feriados_extras):
        d += timedelta(days=1)
    return d


def contar_dias_uteis(
    inicio: date,
    n_dias: int,
    feriados_extras: Optional[set[date]] = None,
) -> date:
    """Conta n_dias ÚTEIS a partir de inicio (exclusive), retorna o vencimento."""
    atual = inicio
    contados = 0
    while contados < n_dias:
        atual += timedelta(days=1)
        if _is_util(atual, feriados_extras):
            contados += 1
    # Se o vencimento cair em dia não útil, prorroga (CPC 224 §1º / CPP 798 §3º)
    return _proximo_util(atual, feriados_extras)


def contar_dias_corridos(
    inicio: date,
    n_dias: int,
    feriados_extras: Optional[set[date]] = None,
) -> date:
    """Conta n_dias CORRIDOS (regime CPP) a partir de inicio (exclusive).

    O bloco de recesso 20/dez–20/jan é tratado como suspensão: os dias do
    período não são contados; o prazo retoma o saldo após 20/jan.
    Vencimento em dia sem expediente → prorroga ao 1º dia útil (CPP 798 §3º).
    """
    atual = inicio
    contados = 0
    while contados < n_dias:
        atual += timedelta(days=1)
        if not _is_recesso(atual):
            contados += 1
    return _proximo_util(atual, feriados_extras)


# ---------------------------------------------------------------------------
# Ponto de entrada principal
# ---------------------------------------------------------------------------

REGIME_UTIL = "util"
REGIME_CORRIDO = "corrido"

RAMO_CIVEL = "civel"
RAMO_TRABALHISTA = "trabalhista"
RAMO_PENAL = "penal"
RAMO_JUCIVEL = "juizado_civel"  # Lei 9.099/95 cível
RAMO_JUCRIMINAL = "juizado_criminal"  # Leis 9.099/95 criminal → CPP

# Tabela de prazos conhecidos: (ramo, ato) → (dias, regime, multiplicadores_disponiveis)
_TABELA: dict[tuple[str, str], tuple[int, str]] = {
    # Cível
    (RAMO_CIVEL, "apelacao"): (15, REGIME_UTIL),
    (RAMO_CIVEL, "agravo_instrumento"): (15, REGIME_UTIL),
    (RAMO_CIVEL, "agravo_interno"): (15, REGIME_UTIL),
    (RAMO_CIVEL, "embargos_declaracao"): (5, REGIME_UTIL),
    (RAMO_CIVEL, "resp"): (15, REGIME_UTIL),
    (RAMO_CIVEL, "re"): (15, REGIME_UTIL),
    (RAMO_CIVEL, "contestacao"): (15, REGIME_UTIL),
    (RAMO_CIVEL, "replica"): (15, REGIME_UTIL),
    (RAMO_CIVEL, "pagamento_voluntario"): (15, REGIME_UTIL),
    (RAMO_CIVEL, "impugnacao_cumprimento"): (15, REGIME_UTIL),
    (RAMO_CIVEL, "embargos_execucao"): (15, REGIME_UTIL),
    (RAMO_CIVEL, "supletivo"): (5, REGIME_UTIL),
    # Trabalhista
    (RAMO_TRABALHISTA, "recurso_ordinario"): (8, REGIME_UTIL),
    (RAMO_TRABALHISTA, "recurso_revista"): (8, REGIME_UTIL),
    (RAMO_TRABALHISTA, "agravo_peticao"): (8, REGIME_UTIL),
    (RAMO_TRABALHISTA, "agravo_instrumento"): (8, REGIME_UTIL),
    (RAMO_TRABALHISTA, "embargos_tst"): (8, REGIME_UTIL),
    (RAMO_TRABALHISTA, "contrarrazoes"): (8, REGIME_UTIL),
    (RAMO_TRABALHISTA, "embargos_declaracao"): (5, REGIME_UTIL),
    (RAMO_TRABALHISTA, "embargos_execucao"): (5, REGIME_UTIL),
    (RAMO_TRABALHISTA, "re"): (15, REGIME_UTIL),
    # Penal (corridos)
    (RAMO_PENAL, "apelacao"): (5, REGIME_CORRIDO),
    (RAMO_PENAL, "rese"): (5, REGIME_CORRIDO),
    (RAMO_PENAL, "razoes_apelacao"): (8, REGIME_CORRIDO),
    (RAMO_PENAL, "embargos_declaracao"): (2, REGIME_CORRIDO),
    (RAMO_PENAL, "embargos_infringentes"): (10, REGIME_CORRIDO),
    (RAMO_PENAL, "agravo_execucao"): (5, REGIME_CORRIDO),
    (RAMO_PENAL, "re"): (15, REGIME_CORRIDO),
    (RAMO_PENAL, "resp"): (15, REGIME_CORRIDO),
    # Juizado cível (dias úteis, Lei 9.099)
    (RAMO_JUCIVEL, "recurso_inominado"): (10, REGIME_UTIL),
    (RAMO_JUCIVEL, "contrarrazoes"): (10, REGIME_UTIL),
    (RAMO_JUCIVEL, "embargos_declaracao"): (5, REGIME_UTIL),
}

# Multiplicadores (CPC 183/180/186/229 e DL 779/69)
_MULT: dict[str, int] = {
    "fazenda": 2,
    "mp": 2,
    "defensoria": 2,
    "litisconsortes_papel": 2,  # NÃO se aplica em autos eletrônicos
    "fazenda_trabalhista_recurso": 2,
}


class PrazoResult:
    """Resultado da calculadora."""

    def __init__(
        self,
        data_vencimento: date,
        dias_base: int,
        regime: str,
        multiplicador: int,
        notas: List[str],
    ):
        self.data_vencimento = data_vencimento
        self.dias_base = dias_base
        self.regime = regime
        self.multiplicador = multiplicador
        self.notas = notas

    def __str__(self):
        mult_str = f" (x{self.multiplicador}={self.dias_base * self.multiplicador}d)" if self.multiplicador > 1 else ""
        notas_str = " | " + "; ".join(self.notas) if self.notas else ""
        return (
            f"Vence {self.data_vencimento.isoformat()} "
            f"— {self.dias_base}d {self.regime}{mult_str}"
            f"{notas_str}"
        )


def calcular_prazo(
    *,
    data_evento: date,
    ramo: str,
    ato: str,
    parte: str = "normal",
    autos_eletronicos: bool = True,
    feriados_extras: Optional[set[date]] = None,
    dias_customizado: Optional[int] = None,
) -> PrazoResult:
    """Calcula o vencimento do prazo.

    Parâmetros
    ----------
    data_evento : data da intimação/publicação/audiência (o dies a quo é o
                  1º dia útil SEGUINTE a este).
    ramo : 'civel', 'trabalhista', 'penal', 'juizado_civel', 'juizado_criminal'
    ato  : chave da tabela interna (p.ex. 'apelacao', 'contestacao'...)
    parte : 'normal', 'fazenda', 'mp', 'defensoria' ou 'litisconsortes_papel'
    autos_eletronicos : se True, CPC 229 §2º exclui o dobro de litisconsortes
    feriados_extras : set de dates com feriados locais adicionais (tribunal)
    dias_customizado : sobrescreve a tabela interna (prazo não catalogado)
    """
    notas: List[str] = []

    # Determinar dias-base e regime
    chave = (ramo, ato)
    if dias_customizado is not None:
        # Regime default por ramo quando customizado
        regime = REGIME_CORRIDO if ramo in (RAMO_PENAL, RAMO_JUCRIMINAL) else REGIME_UTIL
        dias = dias_customizado
        notas.append("prazo customizado")
    elif chave in _TABELA:
        dias, regime = _TABELA[chave]
    else:
        dias = 5
        regime = REGIME_UTIL
        notas.append(f"prazo não catalogado para ({ramo},{ato}) → supletivo 5 dias úteis (CPC 218 §3º)")

    # Multiplicador
    mult = 1
    if parte == "fazenda":
        if ramo == RAMO_TRABALHISTA:
            if ato in ("recurso_ordinario", "recurso_revista", "agravo_peticao", "agravo_instrumento", "embargos_tst", "contrarrazoes"):
                mult = 2
                notas.append("dobro: Fazenda (DL 779/69 art.1º III)")
        elif ramo in (RAMO_JUCIVEL, RAMO_JUCRIMINAL):
            notas.append("SEM dobro p/ Fazenda nos juizados (L10.259 art.9º; L12.153 art.7º)")
        else:
            mult = 2
            notas.append("dobro: Fazenda (CPC 183)")
    elif parte == "mp":
        if ramo == RAMO_PENAL:
            notas.append("ATENÇÃO: MP não tem dobro no processo penal (STF/STJ)")
        elif ramo in (RAMO_JUCIVEL, RAMO_JUCRIMINAL):
            notas.append("SEM dobro p/ MP nos juizados")
        else:
            mult = 2
            notas.append("dobro: MP (CPC 180)")
    elif parte == "defensoria":
        mult = 2
        notas.append("dobro: Defensoria (LC 80/94 / CPC 186)")
    elif parte == "litisconsortes_papel":
        if autos_eletronicos:
            notas.append("INAPLICÁVEL o dobro de litisconsortes em autos eletrônicos (CPC 229 §2º)")
        else:
            mult = 2
            notas.append("dobro: litisconsortes c/ procuradores distintos (CPC 229) — autos físicos")

    dias_totais = dias * mult

    # Dies a quo: 1º dia útil seguinte ao evento
    dies_a_quo = data_evento
    if regime == REGIME_UTIL or ramo != RAMO_PENAL:
        # Exclui o dia do começo; inicia no 1º útil seguinte
        dies_a_quo = _proximo_util(data_evento + timedelta(days=1), feriados_extras)
    else:
        # Penal: 1º dia da contagem deve ser dia útil (Súm. 310/710 STF)
        dies_a_quo = _proximo_util(data_evento + timedelta(days=1), feriados_extras)

    # Contar o prazo
    if regime == REGIME_UTIL:
        # Conta a partir de dies_a_quo - 1 dia (para que dies_a_quo seja o 1º dia contado)
        vencimento = contar_dias_uteis(dies_a_quo - timedelta(days=1), dias_totais, feriados_extras)
    else:
        vencimento = contar_dias_corridos(dies_a_quo - timedelta(days=1), dias_totais, feriados_extras)

    return PrazoResult(
        data_vencimento=vencimento,
        dias_base=dias,
        regime=regime,
        multiplicador=mult,
        notas=notas,
    )


def resumo_prazo(
    *,
    data_evento: date,
    ramo: str,
    ato: str,
    parte: str = "normal",
    autos_eletronicos: bool = True,
    feriados_extras: Optional[set[date]] = None,
    dias_customizado: Optional[int] = None,
) -> str:
    """Retorna string legível para o Maestro citar diretamente ao advogado."""
    r = calcular_prazo(
        data_evento=data_evento,
        ramo=ramo,
        ato=ato,
        parte=parte,
        autos_eletronicos=autos_eletronicos,
        feriados_extras=feriados_extras,
        dias_customizado=dias_customizado,
    )
    notas_str = (" Obs.: " + "; ".join(r.notas) + ".") if r.notas else ""
    mult_str = (
        f" O prazo é em dobro ({r.dias_base * r.multiplicador} dias {r.regime})."
        if r.multiplicador > 1
        else ""
    )
    return (
        f"O prazo vence em **{r.data_vencimento.isoformat()}** "
        f"({r.dias_base} dias {r.regime}, contando a partir do evento de {data_evento.isoformat()})."
        f"{mult_str}{notas_str}"
    )
