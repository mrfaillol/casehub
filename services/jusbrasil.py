"""
CaseHub Lite — JusBrasil API Client
Process consultation, monitoring, and document retrieval.
Docs: https://api.jusbrasil.com.br/docs/

Usage:
    from services.jusbrasil import jusbrasil_client

    resultado = await jusbrasil_client.consultar_processo("0001234-56.2024.8.13.0145")
    docs = await jusbrasil_client.get_documentos(processo_id=12345)
    await jusbrasil_client.registrar_webhook("https://app.example.com/webhook", "movimentacao")
"""
import httpx
import logging
from typing import Optional, List, Dict, Any
from config import settings

logger = logging.getLogger(__name__)

JUSBRASIL_BASE_URL = "https://api.jusbrasil.com.br/v1"

# Mock responses for development/testing when API key is not set
_MOCK_PROCESSO = {
    "id": 88888,
    "numero_cnj": "0001234-56.2024.8.13.0145",
    "partes": {
        "polo_ativo": [{"nome": "MOCK — João Silva", "tipo": "Autor"}],
        "polo_passivo": [{"nome": "MOCK — Estado de Minas Gerais", "tipo": "Réu"}],
    },
    "tribunal": "TJMG",
    "classe": "Procedimento Comum Cível",
    "assuntos": ["Obrigação de Fazer / Não Fazer"],
    "status": "Em andamento",
    "data_distribuicao": "2024-01-15",
    "ultima_atualizacao": "2024-12-01",
    "movimentacoes": [
        {
            "data": "2024-12-01",
            "descricao": "Juntada de petição intermediária",
            "tipo": "Juntada",
        },
        {
            "data": "2024-11-15",
            "descricao": "Despacho: Cite-se a parte ré",
            "tipo": "Despacho",
        },
    ],
    "_mock": True,
}

_MOCK_DOCUMENTO = {
    "id": 77777,
    "titulo": "Petição Inicial",
    "tipo": "peticao",
    "data": "2024-01-15",
    "url_download": None,
    "_mock": True,
}

_MOCK_DIARIO = {
    "data": "2024-12-01",
    "diario": "DJe TJMG",
    "caderno": "Caderno Judicial - 1ª Instância",
    "conteudo": "MOCK — Intimação para ciência e manifestação...",
    "_mock": True,
}


class JusBrasilClient:
    """Client for JusBrasil API (Brazilian legal data)."""

    def __init__(self):
        self.api_key = getattr(settings, "JUSBRASIL_API_KEY", "")
        self.base_url = JUSBRASIL_BASE_URL
        self.timeout = 30.0

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _get(self, path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute a GET request against the JusBrasil API."""
        url = f"{self.base_url}{path}"
        logger.info("JusBrasil GET %s params=%s", url, params)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, headers=self._headers(), params=params)
                resp.raise_for_status()
                data = resp.json()
                logger.debug("JusBrasil response: %s", str(data)[:500])
                return data
        except httpx.TimeoutException:
            logger.error("JusBrasil API timeout: %s", path)
            raise
        except httpx.HTTPStatusError as e:
            logger.error(
                "JusBrasil API HTTP %d: %s", e.response.status_code, e.response.text[:500]
            )
            raise
        except Exception as e:
            logger.error("JusBrasil API error: %s", e)
            raise

    async def _post(self, path: str, payload: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute a POST request against the JusBrasil API."""
        url = f"{self.base_url}{path}"
        logger.info("JusBrasil POST %s", url)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, headers=self._headers(), json=payload or {})
                resp.raise_for_status()
                data = resp.json()
                logger.debug("JusBrasil response: %s", str(data)[:500])
                return data
        except httpx.TimeoutException:
            logger.error("JusBrasil API timeout: %s", path)
            raise
        except httpx.HTTPStatusError as e:
            logger.error(
                "JusBrasil API HTTP %d: %s", e.response.status_code, e.response.text[:500]
            )
            raise
        except Exception as e:
            logger.error("JusBrasil API error: %s", e)
            raise

    # ------------------------------------------------------------------
    # Process consultation
    # ------------------------------------------------------------------

    async def consultar_processo(self, numero_cnj: str) -> Dict[str, Any]:
        """
        Query a processo by its CNJ number.

        Args:
            numero_cnj: CNJ-formatted number (e.g., "0001234-56.2024.8.13.0145")

        Returns:
            Dict with processo data, or mock data if API key not configured.
        """
        if not self.is_configured:
            logger.warning("JusBrasil API key not configured — returning mock data")
            mock = dict(_MOCK_PROCESSO)
            mock["numero_cnj"] = numero_cnj
            return {"error": "JUSBRASIL_API_KEY not configured", "mock": True, "data": mock}

        data = await self._get(f"/processos/{numero_cnj}")
        logger.info("JusBrasil consultar_processo(%s): found", numero_cnj)
        return data

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------

    async def monitorar_por_parte(self, nome: str, tribunal: str = "TJMG") -> Dict[str, Any]:
        """
        Start monitoring new processos by party name.

        Args:
            nome: Full name of the party to monitor.
            tribunal: Tribunal code (e.g., "TJMG", "TJSP").

        Returns:
            Dict with monitoring status or mock confirmation.
        """
        if not self.is_configured:
            logger.warning("JusBrasil API key not configured — returning mock monitoring")
            return {
                "error": "JUSBRASIL_API_KEY not configured",
                "mock": True,
                "data": {
                    "nome": nome,
                    "tribunal": tribunal,
                    "status": "mock_monitorado",
                    "message": "Monitoring not active — API key not configured",
                },
            }

        data = await self._post(
            "/monitoramentos/parte",
            payload={"nome": nome, "tribunal": tribunal},
        )
        logger.info("JusBrasil monitorar_por_parte(%s, %s): %s", nome, tribunal, data.get("status", "ok"))
        return data

    async def monitorar_por_oab(self, oab: str, estado: str = "MG") -> Dict[str, Any]:
        """
        Start monitoring processos by lawyer OAB number.

        Args:
            oab: OAB registration number.
            estado: State code (e.g., "MG", "SP").

        Returns:
            Dict with monitoring status or mock confirmation.
        """
        if not self.is_configured:
            logger.warning("JusBrasil API key not configured — returning mock monitoring")
            return {
                "error": "JUSBRASIL_API_KEY not configured",
                "mock": True,
                "data": {
                    "oab": oab,
                    "estado": estado,
                    "status": "mock_monitorado",
                    "message": "Monitoring not active — API key not configured",
                },
            }

        data = await self._post(
            "/monitoramentos/oab",
            payload={"oab_numero": oab, "oab_estado": estado.upper()},
        )
        logger.info("JusBrasil monitorar_por_oab(%s/%s): %s", estado, oab, data.get("status", "ok"))
        return data

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    async def get_documentos(self, processo_id: int) -> List[Dict]:
        """
        Get court documents attached to a processo.

        Args:
            processo_id: JusBrasil internal processo ID.

        Returns:
            List of document dicts, or mock data.
        """
        if not self.is_configured:
            logger.warning("JusBrasil API key not configured — returning mock documentos")
            return [dict(_MOCK_DOCUMENTO)]

        data = await self._get(f"/processos/{processo_id}/documentos")
        docs = data.get("items", data.get("documentos", []))
        logger.info("JusBrasil get_documentos(%d): %d documents", processo_id, len(docs))
        return docs

    # ------------------------------------------------------------------
    # Webhooks
    # ------------------------------------------------------------------

    async def registrar_webhook(self, url: str, evento: str) -> Dict[str, Any]:
        """
        Register a webhook for real-time notifications from JusBrasil.

        Args:
            url: The callback URL to receive notifications.
            evento: Event type (e.g., "movimentacao", "publicacao", "documento").

        Returns:
            Dict with webhook registration status or mock confirmation.
        """
        if not self.is_configured:
            logger.warning("JusBrasil API key not configured — returning mock webhook")
            return {
                "error": "JUSBRASIL_API_KEY not configured",
                "mock": True,
                "data": {
                    "url": url,
                    "evento": evento,
                    "status": "mock_registrado",
                    "message": "Webhook not registered — API key not configured",
                },
            }

        data = await self._post(
            "/webhooks",
            payload={"url": url, "evento": evento},
        )
        logger.info("JusBrasil registrar_webhook(%s, %s): %s", url, evento, data.get("status", "ok"))
        return data

    # ------------------------------------------------------------------
    # Diários oficiais (Official journals)
    # ------------------------------------------------------------------

    async def buscar_diarios(
        self, termos: str, data: str = None, tribunal: str = None
    ) -> List[Dict]:
        """
        Search official journals (Diários de Justiça).

        Args:
            termos: Search terms (party name, OAB, keywords).
            data: Date filter (YYYY-MM-DD).
            tribunal: Optional tribunal filter.

        Returns:
            List of journal entry dicts, or mock data.
        """
        if not self.is_configured:
            logger.warning("JusBrasil API key not configured — returning mock diarios")
            mock = dict(_MOCK_DIARIO)
            mock["conteudo"] = f"MOCK — Publicação contendo: {termos}"
            return [mock]

        params: Dict[str, Any] = {"q": termos}
        if data:
            params["data"] = data
        if tribunal:
            params["tribunal"] = tribunal

        resp_data = await self._get("/diarios", params=params)
        diarios = resp_data.get("items", [])
        logger.info("JusBrasil buscar_diarios(%s): %d results", termos, len(diarios))
        return diarios


# Singleton instance
jusbrasil_client = JusBrasilClient()
