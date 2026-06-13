"""
AILA Knowledge Base Client for CaseHub Tools
Cliente HTTP para consultar a API AILA do CaseHub

INSTALACAO:
1. Copiar para /opt/casehub/ilc-tools/aila_client.py
2. Importar: from aila_client import AILAClient
"""

import httpx
from typing import Optional, List, Dict, Any
import os


class AILAClient:
    """
    Client for AILA Knowledge Base API (hosted on CaseHub)
    """

    def __init__(self, base_url: str = None):
        """
        Initialize AILA client

        Args:
            base_url: Base URL for CaseHub API (default: http://localhost:8001/casehub)
        """
        self.base_url = base_url or os.getenv(
            "CASEHUB_URL",
            "http://localhost:8001/casehub"
        )
        self.api_url = f"{self.base_url}/api/aila"
        self._status = None

    async def get_status(self) -> Dict:
        """Get AILA API status"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.api_url}/status")
            if response.status_code == 200:
                self._status = response.json()
                return self._status
            return {"available": False, "error": response.text}

    def get_status_sync(self) -> Dict:
        """Synchronous version of get_status"""
        with httpx.Client(timeout=10.0) as client:
            try:
                response = client.get(f"{self.api_url}/status")
                if response.status_code == 200:
                    self._status = response.json()
                    return self._status
            except Exception as e:
                pass
            return {"available": False}

    @property
    def is_available(self) -> bool:
        """Check if AILA API is available"""
        if self._status is None:
            self.get_status_sync()
        return self._status.get("available", False) if self._status else False

    async def search(
        self,
        query: str,
        n_results: int = 5,
        visa_type: Optional[str] = None
    ) -> List[Dict]:
        """
        Search AILA knowledge base

        Args:
            query: Search query
            n_results: Number of results to return
            visa_type: Optional visa type filter

        Returns:
            List of search results with content, source, relevance
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            params = {
                "query": query,
                "n_results": n_results
            }
            if visa_type:
                params["visa_type"] = visa_type

            response = await client.get(f"{self.api_url}/search", params=params)

            if response.status_code == 200:
                data = response.json()
                return data.get("results", [])
            return []

    def search_sync(
        self,
        query: str,
        n_results: int = 5,
        visa_type: Optional[str] = None
    ) -> List[Dict]:
        """Synchronous version of search"""
        with httpx.Client(timeout=30.0) as client:
            try:
                params = {
                    "query": query,
                    "n_results": n_results
                }
                if visa_type:
                    params["visa_type"] = visa_type

                response = client.get(f"{self.api_url}/search", params=params)

                if response.status_code == 200:
                    data = response.json()
                    return data.get("results", [])
            except Exception as e:
                print(f"[AILAClient] Search error: {e}")
            return []

    async def get_requirements(self, visa_type: str) -> Optional[Dict]:
        """
        Get requirements for a visa type

        Args:
            visa_type: Visa type code (e.g., "EB-1A", "H-1B")

        Returns:
            Requirements dict or None if not found
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(f"{self.api_url}/requirements/{visa_type}")

            if response.status_code == 200:
                return response.json()
            return None

    def get_requirements_sync(self, visa_type: str) -> Optional[Dict]:
        """Synchronous version of get_requirements"""
        with httpx.Client(timeout=15.0) as client:
            try:
                response = client.get(f"{self.api_url}/requirements/{visa_type}")
                if response.status_code == 200:
                    return response.json()
            except Exception:
                pass
            return None

    async def get_context(
        self,
        visa_type: str,
        topic: str = "requirements"
    ) -> Optional[str]:
        """
        Get AILA context for LLM prompts

        Args:
            visa_type: Visa type
            topic: Specific topic (requirements, eligibility, processing, etc.)

        Returns:
            Context string for LLM or None
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.api_url}/context/{visa_type}",
                params={"topic": topic}
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("context")
            return None

    def get_context_sync(
        self,
        visa_type: str,
        topic: str = "requirements"
    ) -> Optional[str]:
        """Synchronous version of get_context"""
        with httpx.Client(timeout=30.0) as client:
            try:
                response = client.get(
                    f"{self.api_url}/context/{visa_type}",
                    params={"topic": topic}
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("context")
            except Exception:
                pass
            return None

    async def get_fees(self, visa_type: str) -> Optional[Dict]:
        """Get filing fees for a visa type"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.api_url}/fees/{visa_type}")

            if response.status_code == 200:
                return response.json()
            return None

    def get_fees_sync(self, visa_type: str) -> Optional[Dict]:
        """Synchronous version of get_fees"""
        with httpx.Client(timeout=10.0) as client:
            try:
                response = client.get(f"{self.api_url}/fees/{visa_type}")
                if response.status_code == 200:
                    return response.json()
            except Exception:
                pass
            return None

    async def check_eligibility(self, profile: Dict) -> Optional[Dict]:
        """
        Check eligibility for a visa type

        Args:
            profile: Applicant profile with criteria

        Returns:
            Eligibility result or None
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.api_url}/eligibility",
                json=profile
            )

            if response.status_code == 200:
                return response.json()
            return None

    def check_eligibility_sync(self, profile: Dict) -> Optional[Dict]:
        """Synchronous version of check_eligibility"""
        with httpx.Client(timeout=30.0) as client:
            try:
                response = client.post(
                    f"{self.api_url}/eligibility",
                    json=profile
                )
                if response.status_code == 200:
                    return response.json()
            except Exception:
                pass
            return None

    # =========================================================================
    # LOR GENERATOR HELPERS
    # =========================================================================

    def get_national_importance_context(
        self,
        field: str,
        visa_type: str = "EB-2 NIW"
    ) -> Dict[str, Any]:
        """
        Get context for LOR national importance section

        Args:
            field: Applicant's field of work
            visa_type: Type of visa (default EB-2 NIW)

        Returns:
            Dict with statistics, policies, and talking points
        """
        result = {
            "statistics": [],
            "policies": [],
            "talking_points": [],
            "sources": []
        }

        # Search for field-specific national importance
        stats_results = self.search_sync(
            f"{field} national importance statistics government workforce",
            n_results=3
        )
        for r in stats_results:
            result["statistics"].append(r.get("content", "")[:500])
            result["sources"].append(r.get("source", ""))

        # Search for executive orders and policies
        policy_results = self.search_sync(
            f"{field} executive order policy priority government",
            n_results=2
        )
        for r in policy_results:
            result["policies"].append(r.get("content", "")[:500])
            result["sources"].append(r.get("source", ""))

        # Search for Matter of Dhanasar prong 3 language
        prong3_results = self.search_sync(
            f"Matter of Dhanasar prong 3 national interest waiver benefit",
            n_results=2
        )
        for r in prong3_results:
            result["talking_points"].append(r.get("content", "")[:300])

        # Deduplicate sources
        result["sources"] = list(set(result["sources"]))

        return result

    def get_prong_language(self, prong: int, field: str) -> Optional[str]:
        """
        Get template language for Matter of Dhanasar prongs

        Args:
            prong: 1, 2, or 3
            field: Applicant's field

        Returns:
            Template language or None
        """
        prong_queries = {
            1: f"Matter of Dhanasar prong 1 substantial merit national importance {field}",
            2: f"Matter of Dhanasar prong 2 well positioned advance {field}",
            3: f"Matter of Dhanasar prong 3 balance factors waive labor certification {field}"
        }

        query = prong_queries.get(prong)
        if not query:
            return None

        results = self.search_sync(query, n_results=2)
        if results:
            return results[0].get("content", "")[:800]
        return None


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

# Create default client instance
_default_client = None


def get_aila_client() -> AILAClient:
    """Get or create default AILA client"""
    global _default_client
    if _default_client is None:
        _default_client = AILAClient()
    return _default_client


# =============================================================================
# STANDALONE TEST
# =============================================================================

if __name__ == "__main__":
    import asyncio

    async def test():
        client = AILAClient("http://localhost:8001/casehub")

        print("=== Testing AILA Client ===\n")

        # Test status
        status = await client.get_status()
        print(f"Status: {status}\n")

        if status.get("available"):
            # Test search
            results = await client.search("H-1B specialty occupation requirements")
            print(f"Search results: {len(results)} found")
            for r in results[:2]:
                print(f"  - {r.get('source')}: {r.get('content', '')[:100]}...")

            # Test requirements
            req = await client.get_requirements("EB-1A")
            if req:
                print(f"\nEB-1A requirements: {len(req.get('required_docs', []))} docs needed")

            # Test fees
            fees = await client.get_fees("H-1B")
            if fees:
                print(f"\nH-1B fees: ${fees.get('total_without_premium', 0)} without premium")

    asyncio.run(test())
