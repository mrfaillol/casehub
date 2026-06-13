"""
Calendario judicial complementar para prazos processuais.

O calculador CPC continua tratando fins de semana, feriados nacionais,
feriados estaduais e recesso. Este modulo concentra suspensoes/pontos
facultativos por tribunal, que dependem de ato administrativo local.
"""
from __future__ import annotations

import re
from datetime import date
from typing import List, Optional


_SUSPENSOES_JUDICIAIS = {
    # Portaria CNJ n. 81/2025: Corpus Christi e ponto facultativo.
    "CNJ": {
        2026: {date(2026, 6, 4), date(2026, 6, 5)},
    },
    # Portaria STJ/GDG 1.010/2025.
    "STJ": {
        2026: {date(2026, 6, 4), date(2026, 6, 5)},
    },
    # Portarias Conjuntas TJMG/PR 1.764/2026 e 1.798/2026.
    "TJMG": {
        2026: {date(2026, 6, 4), date(2026, 6, 5)},
    },
    # Portaria TRT3 SETPOE/OE 7/2025.
    "TRT3": {
        2026: {date(2026, 6, 4), date(2026, 6, 5)},
    },
    # Portaria Presi TRF6 1/2026.
    "TRF6": {
        2026: {date(2026, 6, 4), date(2026, 6, 5)},
    },
    # Portarias PRES/TRF2 30, 31, 32, 843 e 844/2026.
    "TRF2": {
        2026: {date(2026, 6, 4), date(2026, 6, 5)},
    },
}


_SUSPENSOES_FORENSES_POR_UF = {
    # Fallback conservador para prazo manual/tribunal ainda nao identificado
    # na Controladoria VS. Em 2026, os principais calendarios judiciais usados
    # pelo escritorio em MG suspenderam Corpus Christi e o ponto facultativo.
    "MG": {
        2026: {date(2026, 6, 4), date(2026, 6, 5)},
    },
}


_TRIBUNAL_ALIASES = {
    "CONSELHO NACIONAL DE JUSTICA": "CNJ",
    "CNJ": "CNJ",
    "SUPERIOR TRIBUNAL DE JUSTICA": "STJ",
    "STJ": "STJ",
    "TJMG": "TJMG",
    "TJ-MG": "TJMG",
    "TRIBUNAL DE JUSTICA DE MINAS GERAIS": "TJMG",
    "TRT3": "TRT3",
    "TRT-3": "TRT3",
    "TRT 3": "TRT3",
    "TRF6": "TRF6",
    "TRF-6": "TRF6",
    "TRF 6": "TRF6",
    "TRF2": "TRF2",
    "TRF-2": "TRF2",
    "TRF 2": "TRF2",
}

_CNJ_TRIBUNAL_MAP = {
    ("8", "13"): "TJMG",
    ("8", "26"): "TJSP",
    ("5", "03"): "TRT3",
    ("5", "01"): "TRT1",
    ("4", "06"): "TRF6",
    ("4", "02"): "TRF2",
}


def normalizar_tribunal(value: Optional[str]) -> str:
    """Normalize a tribunal label/code to the compact code used by the app."""
    raw = (value or "").strip().upper()
    if not raw:
        return "CNJ"
    raw = re.sub(r"\s+", " ", raw)
    return _TRIBUNAL_ALIASES.get(raw, raw.replace(" ", "").replace("-", ""))


def inferir_tribunal(numero_processo: Optional[str]) -> str:
    """Infer tribunal from a CNJ process number when possible."""
    raw = (numero_processo or "").strip()
    match = re.search(r"\d{7}-\d{2}\.\d{4}\.(\d)\.(\d{2})\.\d{4}", raw)
    if not match:
        return "CNJ"
    return _CNJ_TRIBUNAL_MAP.get((match.group(1), match.group(2)), "CNJ")


def get_suspensoes_judiciais(
    ano: int,
    tribunal: Optional[str] = None,
    estado: Optional[str] = None,
) -> List[date]:
    """
    Return tribunal-specific non-business days for deadline calculation.

    `estado` is used as a conservative fallback when the tribunal is unknown.
    """
    codigo = normalizar_tribunal(tribunal) if tribunal else ""
    direct = _SUSPENSOES_JUDICIAIS.get(codigo, {}).get(ano, set()) if codigo else set()
    if direct:
        return sorted(direct)
    estado_codigo = (estado or "").strip().upper()
    return sorted(_SUSPENSOES_FORENSES_POR_UF.get(estado_codigo, {}).get(ano, set()))


def listar_tribunais_suportados() -> List[str]:
    return sorted(_SUSPENSOES_JUDICIAIS)
