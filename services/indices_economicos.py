"""
Correção Monetária com Índices Reais - API Banco Central do Brasil

Séries disponíveis:
- IPCA: série 433
- INPC: série 188
- IGP-M: série 189
- Selic: série 11
- TR: série 226

Documentação: https://dadosabertos.bcb.gov.br/
"""

import httpx
import logging
from datetime import datetime, date
from functools import lru_cache

logger = logging.getLogger(__name__)

BCB_API = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados"

SERIES = {
    "ipca": 433,
    "inpc": 188,
    "igpm": 189,
    "selic": 11,
    "tr": 226,
}


async def get_indice(nome: str, data_inicio: str, data_fim: str) -> list:
    """
    Busca índice econômico do BCB.
    data_inicio/data_fim: formato dd/mm/yyyy
    Retorna lista de {"data": "dd/mm/yyyy", "valor": "0.50"}
    """
    serie = SERIES.get(nome.lower())
    if not serie:
        return []

    url = BCB_API.format(serie=serie)
    params = {
        "formato": "json",
        "dataInicial": data_inicio,
        "dataFinal": data_fim,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        logger.error("BCB API error for %s: %s", nome, e)

    return []


def calcular_correcao(valor: float, indices: list) -> dict:
    """
    Aplica correção monetária usando lista de índices mensais.
    Retorna: valor_corrigido, fator_acumulado, detalhamento mensal
    """
    fator = 1.0
    detalhes = []
    for idx in indices:
        taxa = float(idx["valor"]) / 100
        fator *= (1 + taxa)
        detalhes.append({
            "data": idx["data"],
            "taxa": taxa,
            "fator_acumulado": fator,
            "valor_parcial": valor * fator,
        })

    return {
        "valor_original": valor,
        "valor_corrigido": round(valor * fator, 2),
        "fator_acumulado": round(fator, 8),
        "variacao_percentual": round((fator - 1) * 100, 4),
        "meses": len(indices),
        "detalhes": detalhes,
    }
