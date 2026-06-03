"""
CaseHub Lite — DataJud API Client (CNJ)
Official Brazilian judiciary process tracking.

Docs: https://datajud-wiki.cnj.jus.br/api-publica/

Usage:
    from services.datajud import datajud_client

    resultado = await datajud_client.consultar_processo("0001234-56.2024.8.13.0145")
    processos = await datajud_client.buscar_por_parte("João Silva", tribunal="TJMG")
    processos = await datajud_client.buscar_por_advogado("MG123456", tribunal="TJMG")
    movs = await datajud_client.get_movimentacoes("0001234-56.2024.8.13.0145")
"""
import httpx
import logging
import re
from typing import Optional, List, Dict, Any
from config import settings

logger = logging.getLogger(__name__)

DATAJUD_BASE_URL = "https://api-publica.datajud.cnj.jus.br"

# Map tribunal codes to DataJud API endpoint slugs
TRIBUNAL_ENDPOINTS = {
    # Tribunais Estaduais
    "TJAC": "api_publica_tjac",
    "TJAL": "api_publica_tjal",
    "TJAM": "api_publica_tjam",
    "TJAP": "api_publica_tjap",
    "TJBA": "api_publica_tjba",
    "TJCE": "api_publica_tjce",
    "TJDFT": "api_publica_tjdft",
    "TJES": "api_publica_tjes",
    "TJGO": "api_publica_tjgo",
    "TJMA": "api_publica_tjma",
    "TJMG": "api_publica_tjmg",
    "TJMS": "api_publica_tjms",
    "TJMT": "api_publica_tjmt",
    "TJPA": "api_publica_tjpa",
    "TJPB": "api_publica_tjpb",
    "TJPE": "api_publica_tjpe",
    "TJPI": "api_publica_tjpi",
    "TJPR": "api_publica_tjpr",
    "TJRJ": "api_publica_tjrj",
    "TJRN": "api_publica_tjrn",
    "TJRO": "api_publica_tjro",
    "TJRR": "api_publica_tjrr",
    "TJRS": "api_publica_tjrs",
    "TJSC": "api_publica_tjsc",
    "TJSE": "api_publica_tjse",
    "TJSP": "api_publica_tjsp",
    "TJTO": "api_publica_tjto",
    # Tribunais do Trabalho
    "TRT1": "api_publica_trt1",
    "TRT2": "api_publica_trt2",
    "TRT3": "api_publica_trt3",
    "TRT4": "api_publica_trt4",
    "TRT5": "api_publica_trt5",
    "TRT6": "api_publica_trt6",
    "TRT7": "api_publica_trt7",
    "TRT8": "api_publica_trt8",
    "TRT9": "api_publica_trt9",
    "TRT10": "api_publica_trt10",
    "TRT11": "api_publica_trt11",
    "TRT12": "api_publica_trt12",
    "TRT13": "api_publica_trt13",
    "TRT14": "api_publica_trt14",
    "TRT15": "api_publica_trt15",
    "TRT16": "api_publica_trt16",
    "TRT17": "api_publica_trt17",
    "TRT18": "api_publica_trt18",
    "TRT19": "api_publica_trt19",
    "TRT20": "api_publica_trt20",
    "TRT21": "api_publica_trt21",
    "TRT22": "api_publica_trt22",
    "TRT23": "api_publica_trt23",
    "TRT24": "api_publica_trt24",
    # Tribunais Federais
    "TRF1": "api_publica_trf1",
    "TRF2": "api_publica_trf2",
    "TRF3": "api_publica_trf3",
    "TRF4": "api_publica_trf4",
    "TRF5": "api_publica_trf5",
    "TRF6": "api_publica_trf6",
    # Superiores
    "STF": "api_publica_stf",
    "STJ": "api_publica_stj",
    "TST": "api_publica_tst",
    "TSE": "api_publica_tse",
    "STM": "api_publica_stm",
}

# Mapping: justice segment code (J) + tribunal code (TR) -> tribunal key
# CNJ format: NNNNNNN-DD.AAAA.J.TR.OOOO
JUSTICA_TRIBUNAL_MAP = {
    # 8 = Justiça Estadual
    ("8", "01"): "TJRJ",   # Nota: TJ codes differ from region. Using common mapping.
    ("8", "02"): "TJDFT",
    ("8", "03"): "TJMS",
    ("8", "04"): "TJAL",
    ("8", "05"): "TJCE",
    ("8", "06"): "TJPE",
    ("8", "07"): "TJAP",
    ("8", "08"): "TJAM",
    ("8", "09"): "TJPA",
    ("8", "10"): "TJMA",
    ("8", "11"): "TJPI",
    ("8", "12"): "TJBA",
    ("8", "13"): "TJMG",
    ("8", "14"): "TJES",
    ("8", "15"): "TJRJ",
    ("8", "16"): "TJPR",
    ("8", "17"): "TJSC",
    ("8", "18"): "TJRS",
    ("8", "19"): "TJSP",
    ("8", "20"): "TJSE",
    ("8", "21"): "TJRN",
    ("8", "22"): "TJPB",
    ("8", "23"): "TJRR",
    ("8", "24"): "TJRO",
    ("8", "25"): "TJAC",
    ("8", "26"): "TJGO",
    ("8", "27"): "TJTO",
    ("8", "28"): "TJMT",
    # 5 = Justiça do Trabalho
    ("5", "01"): "TRT1",
    ("5", "02"): "TRT2",
    ("5", "03"): "TRT3",
    ("5", "04"): "TRT4",
    ("5", "05"): "TRT5",
    ("5", "06"): "TRT6",
    ("5", "07"): "TRT7",
    ("5", "08"): "TRT8",
    ("5", "09"): "TRT9",
    ("5", "10"): "TRT10",
    ("5", "11"): "TRT11",
    ("5", "12"): "TRT12",
    ("5", "13"): "TRT13",
    ("5", "14"): "TRT14",
    ("5", "15"): "TRT15",
    ("5", "16"): "TRT16",
    ("5", "17"): "TRT17",
    ("5", "18"): "TRT18",
    ("5", "19"): "TRT19",
    ("5", "20"): "TRT20",
    ("5", "21"): "TRT21",
    ("5", "22"): "TRT22",
    ("5", "23"): "TRT23",
    ("5", "24"): "TRT24",
    # 4 = Justiça Federal
    ("4", "01"): "TRF1",
    ("4", "02"): "TRF2",
    ("4", "03"): "TRF3",
    ("4", "04"): "TRF4",
    ("4", "05"): "TRF5",
    ("4", "06"): "TRF6",
}


def _parse_cnj_number(numero: str) -> dict:
    """
    Parse a CNJ-formatted process number.
    Format: NNNNNNN-DD.AAAA.J.TR.OOOO
    Returns dict with keys: numero_seq, digito, ano, justica, tribunal, origem
    """
    clean = re.sub(r"[.\-\s]", "", numero)
    if len(clean) != 20:
        raise ValueError(f"Numero CNJ invalido (deve ter 20 digitos): {numero}")

    return {
        "numero_seq": clean[:7],
        "digito": clean[7:9],
        "ano": clean[9:13],
        "justica": clean[13],
        "tribunal": clean[14:16],
        "origem": clean[16:20],
        "raw": clean,
    }


def _resolve_tribunal(numero_processo: str, tribunal: Optional[str] = None) -> str:
    """Resolve tribunal code from CNJ number or explicit parameter."""
    if tribunal:
        tribunal_upper = tribunal.upper()
        if tribunal_upper in TRIBUNAL_ENDPOINTS:
            return tribunal_upper
        raise ValueError(f"Tribunal desconhecido: {tribunal}. Tribunais disponiveis: {list(TRIBUNAL_ENDPOINTS.keys())}")

    parsed = _parse_cnj_number(numero_processo)
    key = (parsed["justica"], parsed["tribunal"])
    tribunal_code = JUSTICA_TRIBUNAL_MAP.get(key)
    if not tribunal_code:
        raise ValueError(
            f"Nao foi possivel determinar o tribunal a partir do numero {numero_processo} "
            f"(justica={parsed['justica']}, tribunal={parsed['tribunal']}). "
            f"Informe o tribunal explicitamente."
        )
    return tribunal_code


class DataJudClient:
    """Async client for the CNJ DataJud public API."""

    def __init__(self):
        self.api_key = getattr(settings, "DATAJUD_API_KEY", "")
        self.base_url = DATAJUD_BASE_URL
        self.timeout = 30.0

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"APIKey cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw==",
        }
        if self.api_key:
            headers["Authorization"] = f"APIKey {self.api_key}"
        return headers

    def _endpoint_url(self, tribunal: str) -> str:
        slug = TRIBUNAL_ENDPOINTS.get(tribunal)
        if not slug:
            raise ValueError(f"Tribunal sem endpoint configurado: {tribunal}")
        return f"{self.base_url}/{slug}/_search"

    async def _request(self, tribunal: str, query: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a search request against the DataJud API."""
        if settings.DEMO_MODE:
            logger.info("DataJud DEMO: returning empty result for tribunal=%s", tribunal)
            return {"hits": {"hits": [], "total": {"value": 0}}}
        url = self._endpoint_url(tribunal)
        logger.info("DataJud API request: %s tribunal=%s", url, tribunal)
        logger.debug("DataJud query: %s", query)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=query, headers=self._headers())
                response.raise_for_status()
                data = response.json()
                logger.info(
                    "DataJud API response: %d hits",
                    data.get("hits", {}).get("total", {}).get("value", 0),
                )
                return data
        except httpx.TimeoutException:
            logger.error("DataJud API timeout: tribunal=%s", tribunal)
            raise
        except httpx.HTTPStatusError as e:
            logger.error(
                "DataJud API HTTP error: %d %s", e.response.status_code, e.response.text[:500]
            )
            raise
        except Exception as e:
            logger.error("DataJud API error: %s", e)
            raise

    def _extract_hits(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract process records from Elasticsearch-style response."""
        hits = response.get("hits", {}).get("hits", [])
        return [hit.get("_source", {}) for hit in hits]

    async def consultar_processo(self, numero_processo: str, tribunal: str = None) -> Dict[str, Any]:
        """
        Query a processo by its CNJ number.

        Args:
            numero_processo: CNJ-formatted number (e.g., "0001234-56.2024.8.13.0145")
            tribunal: Optional tribunal code (e.g., "TJMG"). Auto-detected from number if omitted.

        Returns:
            Dict with process data or empty dict if not found.
        """
        tribunal_code = _resolve_tribunal(numero_processo, tribunal)
        clean_number = re.sub(r"[.\-\s]", "", numero_processo)

        query = {
            "query": {
                "match": {
                    "numeroProcesso": clean_number
                }
            }
        }

        response = await self._request(tribunal_code, query)
        hits = self._extract_hits(response)
        if hits:
            logger.info("Processo encontrado: %s", numero_processo)
            return hits[0]
        logger.warning("Processo nao encontrado: %s", numero_processo)
        return {}

    async def buscar_por_parte(
        self, nome: str, tribunal: str = "TJMG", size: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search processos by party name.

        Args:
            nome: Name of the party to search for.
            tribunal: Tribunal code (default: TJMG).
            size: Max number of results (default: 10).

        Returns:
            List of process dicts.
        """
        tribunal_code = _resolve_tribunal("", tribunal)

        query = {
            "size": size,
            "query": {
                "match": {
                    "partes.nome": {
                        "query": nome,
                        "fuzziness": "AUTO",
                    }
                }
            },
            "sort": [{"dataAjuizamento": {"order": "desc"}}],
        }

        response = await self._request(tribunal_code, query)
        results = self._extract_hits(response)
        logger.info("Busca por parte '%s': %d resultados", nome, len(results))
        return results

    async def buscar_por_advogado(
        self, oab: str, tribunal: str = "TJMG", size: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search processos by lawyer OAB number.

        Args:
            oab: OAB registration number (e.g., "MG123456" or just "123456").
            tribunal: Tribunal code (default: TJMG).
            size: Max number of results (default: 10).

        Returns:
            List of process dicts.
        """
        tribunal_code = _resolve_tribunal("", tribunal)

        # Try matching on the inscricao field in the advogados nested object
        query = {
            "size": size,
            "query": {
                "bool": {
                    "should": [
                        {"match": {"partes.advogados.inscricao": oab}},
                        {"match": {"partes.advogados.nome": oab}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            "sort": [{"dataAjuizamento": {"order": "desc"}}],
        }

        response = await self._request(tribunal_code, query)
        results = self._extract_hits(response)
        logger.info("Busca por advogado OAB '%s': %d resultados", oab, len(results))
        return results

    async def get_movimentacoes(
        self, numero_processo: str, tribunal: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get all movements/updates for a processo.

        Args:
            numero_processo: CNJ-formatted number.
            tribunal: Optional tribunal code.

        Returns:
            List of movement dicts sorted by date (most recent first).
        """
        processo = await self.consultar_processo(numero_processo, tribunal)
        if not processo:
            logger.warning("Nenhuma movimentacao: processo nao encontrado %s", numero_processo)
            return []

        movimentacoes = processo.get("movimentos", [])
        # Sort by date descending
        movimentacoes.sort(
            key=lambda m: m.get("dataHora", ""),
            reverse=True,
        )
        logger.info(
            "Movimentacoes do processo %s: %d encontradas",
            numero_processo,
            len(movimentacoes),
        )
        return movimentacoes

    async def buscar_por_classe(
        self, classe_codigo: int, tribunal: str = "TJMG", size: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search processos by procedural class code (e.g., 1116 = Execucao Fiscal).

        Args:
            classe_codigo: Numeric class code from TPU tables.
            tribunal: Tribunal code.
            size: Max results.

        Returns:
            List of process dicts.
        """
        tribunal_code = _resolve_tribunal("", tribunal)

        query = {
            "size": size,
            "query": {
                "match": {
                    "classe.codigo": classe_codigo
                }
            },
            "sort": [{"dataAjuizamento": {"order": "desc"}}],
        }

        response = await self._request(tribunal_code, query)
        return self._extract_hits(response)


# Singleton instance
datajud_client = DataJudClient()
