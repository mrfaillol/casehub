"""Reconhece perguntas sobre prazo processual e injeta resposta calculada.

Usado por maestro_lite.MaestroLite.chat() ANTES de chamar o LLM, quando a
pergunta contém padrões de data + tipo de ato processual. Falha graciosamente:
sem reconhecimento → retorna None e o fluxo normal segue.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from services.prazo_calculator import (
    RAMO_CIVEL, RAMO_PENAL, RAMO_TRABALHISTA, RAMO_JUCIVEL,
    calcular_prazo, resumo_prazo, feriados_nacionais,
)

# ---------------------------------------------------------------------------
# Mapeamento de termos em PT-BR → chaves da calculadora
# ---------------------------------------------------------------------------
_ATO_MAP = {
    # Cível
    r"contesta\w*": (RAMO_CIVEL, "contestacao"),
    r"apela\w*": (RAMO_CIVEL, "apelacao"),
    r"agravo de instrumento": (RAMO_CIVEL, "agravo_instrumento"),
    r"agravo interno": (RAMO_CIVEL, "agravo_interno"),
    r"embargos de declara\w*": (RAMO_CIVEL, "embargos_declaracao"),
    r"recurso especial|resp\b": (RAMO_CIVEL, "resp"),
    r"recurso extraordin\w*|\bre\b.{0,10}(civel|civil|stf)": (RAMO_CIVEL, "re"),
    r"r[eé]plica": (RAMO_CIVEL, "replica"),
    r"impugna\w+ (ao |à )?cumprimento": (RAMO_CIVEL, "impugnacao_cumprimento"),
    r"embargos [aà] execu\w+": (RAMO_CIVEL, "embargos_execucao"),
    r"pagamento volunt\w+": (RAMO_CIVEL, "pagamento_voluntario"),
    # Trabalhista
    r"recurso ordin\w+": (RAMO_TRABALHISTA, "recurso_ordinario"),
    r"recurso de revista": (RAMO_TRABALHISTA, "recurso_revista"),
    r"agravo de peti\w+": (RAMO_TRABALHISTA, "agravo_peticao"),
    r"embargos (no |ao )?tst": (RAMO_TRABALHISTA, "embargos_tst"),
    # Penal
    r"apela\w+.{0,20}(criminal|penal|crime|r[eé]u|reu)": (RAMO_PENAL, "apelacao"),
    r"rese\b|recurso em sentido estrito": (RAMO_PENAL, "rese"),
    r"embargos de declara\w+.{0,20}(criminal|penal|crime)": (RAMO_PENAL, "embargos_declaracao"),
    # Juizado
    r"recurso inomin\w+": (RAMO_JUCIVEL, "recurso_inominado"),
    r"juizado.{0,30}apela\w+": (RAMO_JUCIVEL, "recurso_inominado"),
}

_PARTE_MAP = {
    r"fazenda|estado|mun[ií]cip|uni[aã]o|autarquia|ibama|inss|pgm|pgf|pge": "fazenda",
    r"minist[eé]rio p[uú]blico|\bmp\b|mpf|mpe|mpt\b|promotor|procurador": "mp",
    r"defensoria|defensor": "defensoria",
}

# Regex para capturar data no formato DD/MM/AAAA ou DD-MM-AAAA ou "dia de mês de ano"
_MESES = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, "maio": 5,
    "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}
_RE_DATA_NUM = re.compile(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b")
_RE_DATA_EXT = re.compile(
    r"\b(\d{1,2})\s+de\s+(janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro|jan|fev|mar|abr|jun|jul|ago|set|out|nov|dez)\s+de\s+(\d{4})\b",
    re.IGNORECASE,
)
_RE_PRAZO = re.compile(r"\bprazo\b|\bvence\b|\bvencimento\b|\bconta[dr]\b|\bqual o dia\b|\bat[eé] quando\b", re.IGNORECASE)


def _extrair_data(texto: str) -> Optional[date]:
    """Extrai primeira data encontrada no texto."""
    m = _RE_DATA_NUM.search(texto)
    if m:
        try:
            dia, mes, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return date(ano, mes, dia)
        except ValueError:
            pass
    m = _RE_DATA_EXT.search(texto)
    if m:
        try:
            dia = int(m.group(1))
            mes = _MESES.get(m.group(2).lower(), 0)
            ano = int(m.group(3))
            if mes:
                return date(ano, mes, dia)
        except ValueError:
            pass
    return None


def _extrair_ato(texto: str) -> Optional[tuple[str, str]]:
    """Retorna (ramo, ato) se reconhecido."""
    lower = texto.lower()
    for pattern, chave in _ATO_MAP.items():
        if re.search(pattern, lower):
            return chave
    return None


def _extrair_parte(texto: str) -> str:
    lower = texto.lower()
    for pattern, parte in _PARTE_MAP.items():
        if re.search(pattern, lower):
            return parte
    return "normal"


def prazo_intent(message: str) -> Optional[str]:
    """Se a mensagem é sobre prazo processual com data e ato, retorna resposta calculada.

    Retorna None se não reconhecer → o LLM segue normalmente.
    Nunca lança exceção.
    """
    try:
        if not _RE_PRAZO.search(message):
            return None
        evento = _extrair_data(message)
        if evento is None:
            return None
        ramo_ato = _extrair_ato(message)
        if ramo_ato is None:
            return None
        ramo, ato = ramo_ato
        parte = _extrair_parte(message)
        # Autos eletrônicos: assume true (padrão atual)
        texto = resumo_prazo(
            data_evento=evento,
            ramo=ramo,
            ato=ato,
            parte=parte,
            autos_eletronicos=True,
        )
        ramo_legivel = {
            RAMO_CIVEL: "cível (CPC/2015)",
            RAMO_TRABALHISTA: "trabalhista (CLT)",
            RAMO_PENAL: "penal (CPP)",
            RAMO_JUCIVEL: "juizado especial cível (Lei 9.099/95)",
        }.get(ramo, ramo)
        return (
            f"📅 **Cálculo de prazo — {ramo_legivel}**\n\n"
            f"{texto}\n\n"
            "⚠️ *Confirme sempre o calendário do tribunal, feriados locais e "
            "eventuais suspensões antes de protocolar.*"
        )
    except Exception:  # noqa: BLE001
        return None
