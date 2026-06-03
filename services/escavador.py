"""
CaseHub Lite — Escavador API Client
Search processos, parties, lawyers, and monitor court publications.
Docs: https://api.escavador.com/v1/docs/

Usage:
    from services.escavador import escavador_client

    resultado = await escavador_client.buscar_processo("0001234-56.2024.8.13.0145")
    processos = await escavador_client.buscar_por_nome("João Silva")
    publicacoes = await escavador_client.buscar_publicacoes(oab="MG123456")
"""
import httpx
import logging
from typing import Optional, List, Dict, Any
from config import settings

logger = logging.getLogger(__name__)

ESCAVADOR_BASE_URL = "https://api.escavador.com/v1"

# Mock responses for development/testing when API key is not set
_MOCK_PROCESSO = {
    "id": 99999,
    "numero_cnj": "0001234-56.2024.8.13.0145",
    "titulo_polo_ativo": "MOCK — João Silva",
    "titulo_polo_passivo": "MOCK — Estado de Minas Gerais",
    "ano_inicio": 2024,
    "tribunal": "TJMG",
    "grau": "1º Grau",
    "classe": {"nome": "Procedimento Comum Cível"},
    "assuntos": [{"nome": "Obrigação de Fazer / Não Fazer"}],
    "fontes": [{"nome": "TJMG - 1ª Instância", "tipo": "TRIBUNAL"}],
    "ultima_movimentacao": {
        "data": "2024-12-01",
        "descricao": "Juntada de petição",
    },
    "_mock": True,
}

_MOCK_MOVIMENTACAO = {
    "data": "2024-12-01",
    "descricao": "Juntada de petição intermediária",
    "tipo": "Juntada",
    "_mock": True,
}

_MOCK_PUBLICACAO = {
    "data": "2024-12-01",
    "diario": "DJe - Diário de Justiça Eletrônico - TJMG",
    "conteudo": "MOCK — Intimação para manifestação no prazo de 15 dias...",
    "caderno": "Caderno Judicial",
    "_mock": True,
}


class EscavadorClient:
    """Client for Escavador API (Brazilian legal data)."""

    def __init__(self):
        self.api_key = getattr(settings, "ESCAVADOR_API_KEY", "")
        self.base_url = ESCAVADOR_BASE_URL
        self.timeout = 30.0

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

    async def _get(self, path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute a GET request against the Escavador API."""
        url = f"{self.base_url}{path}"
        logger.info("Escavador GET %s params=%s", url, params)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, headers=self._headers(), params=params)
                resp.raise_for_status()
                data = resp.json()
                logger.debug("Escavador response: %s", str(data)[:500])
                return data
        except httpx.TimeoutException:
            logger.error("Escavador API timeout: %s", path)
            raise
        except httpx.HTTPStatusError as e:
            logger.error(
                "Escavador API HTTP %d: %s", e.response.status_code, e.response.text[:500]
            )
            raise
        except Exception as e:
            logger.error("Escavador API error: %s", e)
            raise

    async def _post(self, path: str, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute a POST request against the Escavador API."""
        url = f"{self.base_url}{path}"
        logger.info("Escavador POST %s", url)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, headers=self._headers(), json=payload or {})
                resp.raise_for_status()
                data = resp.json()
                logger.debug("Escavador response: %s", str(data)[:500])
                return data
        except httpx.TimeoutException:
            logger.error("Escavador API timeout: %s", path)
            raise
        except httpx.HTTPStatusError as e:
            logger.error(
                "Escavador API HTTP %d: %s", e.response.status_code, e.response.text[:500]
            )
            raise
        except Exception as e:
            logger.error("Escavador API error: %s", e)
            raise

    # ------------------------------------------------------------------
    # Process search
    # ------------------------------------------------------------------

    async def buscar_processo(self, numero_cnj: str) -> Dict[str, Any]:
        """
        Search processo by CNJ number.

        Args:
            numero_cnj: CNJ-formatted number (e.g., "0001234-56.2024.8.13.0145")

        Returns:
            Dict with processo data, or mock data if API key not configured.
        """
        if not self.is_configured:
            logger.warning("Escavador API key not configured — returning mock data")
            mock = dict(_MOCK_PROCESSO)
            mock["numero_cnj"] = numero_cnj
            return {"error": "ESCAVADOR_API_KEY not configured", "mock": True, "data": mock}

        data = await self._get(f"/processos/numero_cnj/{numero_cnj}")
        logger.info("Escavador buscar_processo(%s): found", numero_cnj)
        return data

    async def buscar_por_nome(self, nome: str) -> Dict[str, Any]:
        """
        Search processos by party name.

        Args:
            nome: Full or partial name of a party.

        Returns:
            Dict with search results or mock data.
        """
        if not self.is_configured:
            logger.warning("Escavador API key not configured — returning mock data")
            mock = dict(_MOCK_PROCESSO)
            mock["titulo_polo_ativo"] = f"MOCK — {nome}"
            return {
                "error": "ESCAVADOR_API_KEY not configured",
                "mock": True,
                "data": {"items": [mock]},
            }

        data = await self._get("/processos", params={"nome": nome})
        logger.info("Escavador buscar_por_nome(%s): %d results", nome, len(data.get("items", [])))
        return data

    async def buscar_por_cpf_cnpj(self, documento: str) -> Dict[str, Any]:
        """
        Search processos by CPF or CNPJ.

        Args:
            documento: CPF (11 digits) or CNPJ (14 digits), with or without formatting.

        Returns:
            Dict with search results or mock data.
        """
        # Strip formatting
        doc_clean = documento.replace(".", "").replace("-", "").replace("/", "")

        if not self.is_configured:
            logger.warning("Escavador API key not configured — returning mock data")
            mock = dict(_MOCK_PROCESSO)
            mock["titulo_polo_ativo"] = f"MOCK — CPF/CNPJ {doc_clean}"
            return {
                "error": "ESCAVADOR_API_KEY not configured",
                "mock": True,
                "data": {"items": [mock]},
            }

        data = await self._get("/processos", params={"cpf_cnpj": doc_clean})
        logger.info("Escavador buscar_por_cpf_cnpj(%s): %d results", doc_clean[:6] + "...", len(data.get("items", [])))
        return data

    async def buscar_por_oab(self, oab: str, estado: str = "MG") -> Dict[str, Any]:
        """
        Search processos by lawyer OAB number.

        Args:
            oab: OAB registration number (e.g., "123456").
            estado: State code (e.g., "MG", "SP"). Default: "MG".

        Returns:
            Dict with search results or mock data.
        """
        if not self.is_configured:
            logger.warning("Escavador API key not configured — returning mock data")
            mock = dict(_MOCK_PROCESSO)
            return {
                "error": "ESCAVADOR_API_KEY not configured",
                "mock": True,
                "data": {"items": [mock]},
            }

        data = await self._get("/processos", params={"oab_numero": oab, "oab_estado": estado.upper()})
        logger.info("Escavador buscar_por_oab(%s/%s): %d results", estado, oab, len(data.get("items", [])))
        return data

    # ------------------------------------------------------------------
    # Movimentações (movements/updates)
    # ------------------------------------------------------------------

    async def get_movimentacoes(self, processo_id: int) -> List[Dict]:
        """
        Get all movements for a processo.

        Args:
            processo_id: Escavador internal processo ID.

        Returns:
            List of movement dicts sorted by date descending, or mock data.
        """
        if not self.is_configured:
            logger.warning("Escavador API key not configured — returning mock movimentacoes")
            return [dict(_MOCK_MOVIMENTACAO)]

        data = await self._get(f"/processos/{processo_id}/movimentacoes")
        movs = data.get("items", data.get("movimentacoes", []))
        movs.sort(key=lambda m: m.get("data", ""), reverse=True)
        logger.info("Escavador get_movimentacoes(%d): %d movements", processo_id, len(movs))
        return movs

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------

    async def monitorar_processo(self, numero_cnj: str) -> Dict[str, Any]:
        """
        Start monitoring a processo for new movements via Escavador.

        Args:
            numero_cnj: CNJ-formatted number.

        Returns:
            Dict with monitoring status or mock confirmation.
        """
        if not self.is_configured:
            logger.warning("Escavador API key not configured — returning mock monitoring")
            return {
                "error": "ESCAVADOR_API_KEY not configured",
                "mock": True,
                "data": {
                    "numero_cnj": numero_cnj,
                    "status": "mock_monitorado",
                    "message": "Monitoring not active — API key not configured",
                },
            }

        data = await self._post("/monitoramentos", payload={"numero_cnj": numero_cnj})
        logger.info("Escavador monitorar_processo(%s): %s", numero_cnj, data.get("status", "ok"))
        return data

    # ------------------------------------------------------------------
    # Publicações (Diário de Justiça)
    # ------------------------------------------------------------------

    async def buscar_publicacoes(
        self,
        nome: str = None,
        oab: str = None,
        data_inicio: str = None,
    ) -> List[Dict]:
        """
        Search Diário de Justiça publications.

        Args:
            nome: Party or lawyer name to search.
            oab: OAB number to search.
            data_inicio: Start date filter (YYYY-MM-DD).

        Returns:
            List of publication dicts, or mock data.
        """
        if not self.is_configured:
            logger.warning("Escavador API key not configured — returning mock publicacoes")
            mock = dict(_MOCK_PUBLICACAO)
            if nome:
                mock["conteudo"] = f"MOCK — Publicação referente a {nome}"
            return [mock]

        params: Dict[str, Any] = {}
        if nome:
            params["nome"] = nome
        if oab:
            params["oab"] = oab
        if data_inicio:
            params["data_inicio"] = data_inicio

        data = await self._get("/diarios", params=params)
        publicacoes = data.get("items", [])
        logger.info(
            "Escavador buscar_publicacoes(nome=%s, oab=%s): %d results",
            nome, oab, len(publicacoes),
        )
        return publicacoes


# Singleton instance
escavador_client = EscavadorClient()
