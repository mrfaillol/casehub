"""
CaseHub Lite — CPC Deadline Calculator
Calculates legal deadlines in business days, respecting holidays and judicial recess.

References:
- CPC Art. 219: Prazos contados em dias uteis
- CPC Art. 220: Recesso judiciario (20/dez a 20/jan)
- CPC Art. 224: Prazo comeca a correr no primeiro dia util seguinte a intimacao

Usage:
    from services.prazos_cpc import calcular_prazo, prazos_comuns, get_feriados

    prazo = calcular_prazo(date(2026, 3, 10), dias=15, estado="MG")
    feriados = get_feriados(2026, estado="MG")
    comuns = prazos_comuns()
"""
import logging
from datetime import date, timedelta
from typing import List, Optional, Dict, Any

from services.calendario_judicial import get_suspensoes_judiciais

logger = logging.getLogger(__name__)

# ============================================================================
# Fixed national holidays (month, day)
# ============================================================================
FERIADOS_NACIONAIS_FIXOS = [
    (1, 1),    # Confraternizacao Universal
    (4, 21),   # Tiradentes
    (5, 1),    # Dia do Trabalho
    (9, 7),    # Independencia do Brasil
    (10, 12),  # Nossa Senhora Aparecida
    (11, 2),   # Finados
    (11, 15),  # Proclamacao da Republica
    (12, 25),  # Natal
]

# ============================================================================
# State holidays: dict[estado] -> list[(month, day)]
# ============================================================================
FERIADOS_ESTADUAIS = {
    "MG": [
        (4, 21),   # Tiradentes (data magna de MG — also national, but important locally)
    ],
    "SP": [
        (7, 9),    # Revolucao Constitucionalista
    ],
    "RJ": [
        (4, 23),   # Dia de Sao Jorge
        (11, 20),  # Dia da Consciencia Negra
    ],
    "BA": [
        (7, 2),    # Independencia da Bahia
    ],
    "RS": [
        (9, 20),   # Revolucao Farroupilha
    ],
    "PR": [
        (12, 19),  # Emancipacao do Parana
    ],
    "PE": [
        (3, 6),    # Revolucao Pernambucana (data magna)
    ],
    "CE": [
        (3, 25),   # Data Magna do Ceara
    ],
    "SC": [
        (8, 11),   # Dia de Santa Catarina
    ],
    "GO": [
        (10, 24),  # Pedra Fundamental de Goiania
    ],
    "PA": [
        (8, 15),   # Adesao do Para a Independencia
    ],
    "AM": [
        (9, 5),    # Elevacao do Amazonas
    ],
    "MA": [
        (7, 28),   # Adesao do Maranhao a Independencia
    ],
    "MT": [
        (11, 20),  # Dia da Consciencia Negra
    ],
    "MS": [
        (10, 11),  # Criacao do Estado
    ],
    "ES": [
        (10, 28),  # Dia do Servidor Publico
    ],
    "PI": [
        (10, 19),  # Dia do Piaui
    ],
    "AL": [
        (9, 16),   # Emancipacao de Alagoas
    ],
    "SE": [
        (7, 8),    # Emancipacao de Sergipe
    ],
    "RN": [
        (10, 3),   # Martires de Cunhau e Uruacu
    ],
    "PB": [
        (8, 5),    # Fundacao do Estado
    ],
    "RR": [
        (10, 5),   # Criacao de Roraima
    ],
    "AP": [
        (3, 19),   # Dia de Sao Jose (padroeiro)
    ],
    "RO": [
        (1, 4),    # Criacao do Estado
    ],
    "AC": [
        (6, 15),   # Aniversario do Acre
    ],
    "TO": [
        (10, 5),   # Criacao do Estado
    ],
    "DF": [
        (4, 21),   # Fundacao de Brasilia
        (11, 30),  # Dia do Evangelico
    ],
}


def calcular_pascoa(ano: int) -> date:
    """
    Calculate Easter Sunday date using the Anonymous Gregorian algorithm
    (a.k.a. Meeus/Jones/Butcher algorithm).
    """
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


def get_feriados_moveis(ano: int) -> List[date]:
    """
    Calculate mobile holidays based on Easter for a given year.
    Returns: Carnival Monday, Carnival Tuesday, Ash Wednesday,
             Good Friday, Corpus Christi.
    """
    pascoa = calcular_pascoa(ano)
    return [
        pascoa - timedelta(days=48),  # Segunda-feira de Carnaval
        pascoa - timedelta(days=47),  # Terca-feira de Carnaval (Shrove Tuesday)
        pascoa - timedelta(days=46),  # Quarta-feira de Cinzas (ponto facultativo, mas feriado forense)
        pascoa - timedelta(days=2),   # Sexta-feira Santa (Good Friday)
        pascoa + timedelta(days=60),  # Corpus Christi
    ]


def get_feriados(ano: int, estado: str = "MG", tribunal: Optional[str] = None) -> List[date]:
    """
    Get all holidays for a given year and state.
    Includes: national fixed, mobile (Easter-based), and state-specific.

    Args:
        ano: Year.
        estado: State code (e.g., "MG", "SP", "RJ"). Default: MG.
        tribunal: Optional court code for tribunal-specific suspensions.

    Returns:
        Sorted list of holiday dates.
    """
    feriados = set()

    # National fixed holidays
    for mes, dia in FERIADOS_NACIONAIS_FIXOS:
        feriados.add(date(ano, mes, dia))

    # Mobile holidays
    for d in get_feriados_moveis(ano):
        feriados.add(d)

    # State holidays
    estado_upper = estado.upper()
    for mes, dia in FERIADOS_ESTADUAIS.get(estado_upper, []):
        try:
            feriados.add(date(ano, mes, dia))
        except ValueError:
            pass  # Invalid date for this year

    for d in get_suspensoes_judiciais(ano, tribunal=tribunal, estado=estado_upper):
        feriados.add(d)

    return sorted(feriados)


def _em_recesso(d: date) -> bool:
    """
    Check if date falls within judicial recess (CPC Art. 220).
    Recess: December 20 to January 20 (inclusive).
    During recess, deadlines are suspended.
    """
    # Dec 20 - Dec 31
    if d.month == 12 and d.day >= 20:
        return True
    # Jan 1 - Jan 20
    if d.month == 1 and d.day <= 20:
        return True
    return False


def eh_dia_util(d: date, estado: str = "MG", tribunal: Optional[str] = None) -> bool:
    """
    Check if a date is a judicial business day.

    A day is NOT a business day if:
    - It's a Saturday or Sunday
    - It's a national or state holiday
    - It falls within judicial recess (Dec 20 - Jan 20)

    Args:
        d: Date to check.
        estado: State code for state-specific holidays.
        tribunal: Optional court code for court-specific suspensions.

    Returns:
        True if it's a business day, False otherwise.
    """
    # Weekend
    if d.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return False

    # Judicial recess
    if _em_recesso(d):
        return False

    # Holidays — check both the year of the date
    feriados = get_feriados(d.year, estado, tribunal=tribunal)
    if d in feriados:
        return False

    return True


def proximo_dia_util(d: date, estado: str = "MG", tribunal: Optional[str] = None) -> date:
    """
    Find the next business day on or after the given date.
    """
    while not eh_dia_util(d, estado, tribunal=tribunal):
        d += timedelta(days=1)
    return d


def calcular_prazo(
    data_intimacao: date,
    dias: int,
    estado: str = "MG",
    dobro: bool = False,
    tribunal: Optional[str] = None,
) -> date:
    """
    Calculate a legal deadline from an intimation date.

    CPC Art. 224: The deadline starts running on the first business day
    AFTER the intimation date.
    CPC Art. 219: Deadlines are counted in business days only.
    CPC Art. 229: Prazo em dobro for Fazenda Publica, Ministerio Publico,
                  Defensoria Publica (optional flag).

    Args:
        data_intimacao: Date the party was served/notified.
        dias: Number of business days for the deadline.
        estado: State code for holidays.
        dobro: If True, doubles the deadline (CPC Art. 229).
        tribunal: Optional court code for court-specific suspensions.

    Returns:
        The deadline date (last day to act).
    """
    if dias <= 0:
        raise ValueError("Prazo deve ser positivo")

    prazo_dias = dias * 2 if dobro else dias

    # CPC Art. 224: prazo starts on the first business day AFTER intimation
    current = data_intimacao + timedelta(days=1)
    current = proximo_dia_util(current, estado, tribunal=tribunal)

    # Count business days
    dias_contados = 1  # first business day after intimation counts as day 1
    while dias_contados < prazo_dias:
        current += timedelta(days=1)
        if eh_dia_util(current, estado, tribunal=tribunal):
            dias_contados += 1

    logger.info(
        "Prazo calculado: intimacao=%s, dias=%d%s, estado=%s, tribunal=%s -> vencimento=%s",
        data_intimacao.isoformat(),
        dias,
        " (dobro)" if dobro else "",
        estado,
        tribunal or "",
        current.isoformat(),
    )
    return current


def calcular_prazo_corrido(data_intimacao: date, dias: int) -> date:
    """
    Calculate an ADMINISTRATIVE deadline counted in CALENDAR days (dias corridos).

    Unlike judicial deadlines (CPC business-day rules), administrative deadlines
    (INSS, processos administrativos) run continuously — no holiday/weekend
    suspension and no court calendar. Counted as plain calendar days from the
    intimation/start date. Reunião Ricardo/Example User 10/06/2026.

    Args:
        data_intimacao: Start/intimation date.
        dias: Number of calendar days for the deadline.

    Returns:
        The deadline date (data_intimacao + dias calendar days).
    """
    if dias <= 0:
        raise ValueError("Prazo deve ser positivo")
    return data_intimacao + timedelta(days=dias)


def calcular_prazo_detalhado(
    data_intimacao: date,
    dias: int,
    estado: str = "MG",
    dobro: bool = False,
    tribunal: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calculate deadline with detailed breakdown.

    Returns dict with:
        - data_intimacao: original intimation date
        - inicio_prazo: first business day (when counting starts)
        - vencimento: deadline date
        - dias_uteis: business days counted
        - dias_corridos: calendar days from intimation to deadline
        - feriados_no_periodo: holidays that fell within the period
        - recesso: whether recess affected the calculation
    """
    if dias <= 0:
        raise ValueError("Prazo deve ser positivo")

    prazo_dias = dias * 2 if dobro else dias

    # Find start
    inicio = data_intimacao + timedelta(days=1)
    inicio = proximo_dia_util(inicio, estado, tribunal=tribunal)

    # Count business days and track details
    current = inicio
    dias_contados = 1
    feriados_encontrados = []
    recesso_encontrado = False

    while dias_contados < prazo_dias:
        current += timedelta(days=1)
        if _em_recesso(current):
            recesso_encontrado = True
        if current.weekday() < 5:  # Weekday
            feriados_ano = get_feriados(current.year, estado, tribunal=tribunal)
            if current in feriados_ano:
                feriados_encontrados.append(current.isoformat())
        if eh_dia_util(current, estado, tribunal=tribunal):
            dias_contados += 1

    return {
        "data_intimacao": data_intimacao.isoformat(),
        "inicio_prazo": inicio.isoformat(),
        "vencimento": current.isoformat(),
        "dias_uteis": prazo_dias,
        "dias_corridos": (current - data_intimacao).days,
        "feriados_no_periodo": feriados_encontrados,
        "recesso": recesso_encontrado,
        "dobro": dobro,
        "estado": estado,
        "tribunal": tribunal,
    }


def prazos_comuns() -> Dict[str, Dict[str, Any]]:
    """
    Common CPC deadlines with legal references.

    Returns dict mapping deadline type -> {dias, ref, descricao}.
    """
    return {
        "contestacao": {
            "dias": 15,
            "ref": "CPC Art. 335",
            "descricao": "Contestacao (procedimento comum)",
        },
        "recurso_apelacao": {
            "dias": 15,
            "ref": "CPC Art. 1.003",
            "descricao": "Recurso de Apelacao",
        },
        "recurso_especial": {
            "dias": 15,
            "ref": "CPC Art. 1.029",
            "descricao": "Recurso Especial (STJ)",
        },
        "recurso_extraordinario": {
            "dias": 15,
            "ref": "CPC Art. 1.029",
            "descricao": "Recurso Extraordinario (STF)",
        },
        "agravo_instrumento": {
            "dias": 15,
            "ref": "CPC Art. 1.016",
            "descricao": "Agravo de Instrumento",
        },
        "agravo_interno": {
            "dias": 15,
            "ref": "CPC Art. 1.021",
            "descricao": "Agravo Interno",
        },
        "embargos_declaracao": {
            "dias": 5,
            "ref": "CPC Art. 1.023",
            "descricao": "Embargos de Declaracao",
        },
        "impugnacao_cumprimento": {
            "dias": 15,
            "ref": "CPC Art. 525",
            "descricao": "Impugnacao ao Cumprimento de Sentenca",
        },
        "recurso_ordinario": {
            "dias": 8,
            "ref": "CLT Art. 895",
            "descricao": "Recurso Ordinario (Trabalhista)",
        },
        "manifestacao": {
            "dias": 5,
            "ref": "CPC Art. 218",
            "descricao": "Manifestacao generica",
        },
        "replica": {
            "dias": 15,
            "ref": "CPC Art. 350",
            "descricao": "Replica (resposta a contestacao)",
        },
        "cumprimento_sentenca": {
            "dias": 15,
            "ref": "CPC Art. 523",
            "descricao": "Pagamento voluntario em cumprimento de sentenca",
        },
        "embargos_execucao": {
            "dias": 15,
            "ref": "CPC Art. 914",
            "descricao": "Embargos a Execucao",
        },
        "reconvencao": {
            "dias": 15,
            "ref": "CPC Art. 343",
            "descricao": "Reconvencao",
        },
        "tutela_urgencia": {
            "dias": 5,
            "ref": "CPC Art. 303",
            "descricao": "Aditamento da inicial (tutela de urgencia antecedente)",
        },
        "contrarrazoes": {
            "dias": 15,
            "ref": "CPC Art. 1.010",
            "descricao": "Contrarrazoes de Apelacao",
        },
    }


def listar_prazos_para_data(
    data_intimacao: date, estado: str = "MG", tribunal: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Calculate all common deadlines from a single intimation date.
    Useful for a quick overview after receiving a notification.

    Returns list of dicts with tipo, descricao, dias, ref, vencimento.
    """
    resultado = []
    for tipo, info in prazos_comuns().items():
        vencimento = calcular_prazo(data_intimacao, info["dias"], estado, tribunal=tribunal)
        resultado.append({
            "tipo": tipo,
            "descricao": info["descricao"],
            "dias": info["dias"],
            "ref": info["ref"],
            "vencimento": vencimento.isoformat(),
            "vencimento_date": vencimento,
        })
    resultado.sort(key=lambda x: x["vencimento_date"])
    # Remove the date object (not JSON-serializable)
    for r in resultado:
        del r["vencimento_date"]
    return resultado
