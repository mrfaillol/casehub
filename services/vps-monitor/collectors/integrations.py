"""
External Integrations Health Collector
Checks health of external APIs: Moskit CRM, Google Gemini, etc.
"""
import os
import httpx
from datetime import datetime
from typing import Dict, Any


class IntegrationsCollector:
    """Collects health status of external integrations"""

    def __init__(self):
        self._client = None
        self._last_results = {}
        
        # API configurations
        self.moskit_config = {
            "base_url": "https://api.moskitcrm.com/v2",
            "api_key": os.environ.get('MOSKIT_API_KEY', '')
        }
        
        self.gemini_config = {
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "api_key": os.environ.get('GOOGLE_API_KEY', '')
        }

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def check_moskit(self) -> Dict[str, Any]:
        """Check Moskit CRM API health"""
        client = await self._get_client()
        try:
            start = datetime.now()
            response = await client.get(
                f"{self.moskit_config['base_url']}/users",
                headers={"apikey": self.moskit_config["api_key"]}
            )
            elapsed = (datetime.now() - start).total_seconds() * 1000
            
            if response.status_code == 200:
                data = response.json()
                user_count = len(data) if isinstance(data, list) else 0
                active_users = sum(1 for u in data if u.get("active", False)) if isinstance(data, list) else 0
                return {
                    "name": "Moskit CRM",
                    "status": "healthy",
                    "status_code": response.status_code,
                    "response_time_ms": round(elapsed, 1),
                    "total_users": user_count,
                    "active_users": active_users,
                    "checked_at": datetime.now().isoformat()
                }
            else:
                return {
                    "name": "Moskit CRM",
                    "status": "unhealthy",
                    "status_code": response.status_code,
                    "response_time_ms": round(elapsed, 1),
                    "error": response.text[:200],
                    "checked_at": datetime.now().isoformat()
                }
        except Exception as e:
            return {
                "name": "Moskit CRM",
                "status": "error",
                "error": str(e),
                "checked_at": datetime.now().isoformat()
            }

    async def check_gemini(self) -> Dict[str, Any]:
        """Check Google Gemini API health"""
        client = await self._get_client()
        try:
            start = datetime.now()
            response = await client.get(
                f"{self.gemini_config['base_url']}/models",
                params={"key": self.gemini_config["api_key"]}
            )
            elapsed = (datetime.now() - start).total_seconds() * 1000
            
            if response.status_code == 200:
                data = response.json()
                models = [m.get("name", "").split("/")[-1] for m in data.get("models", [])[:5]]
                return {
                    "name": "Google Gemini",
                    "status": "healthy",
                    "status_code": response.status_code,
                    "response_time_ms": round(elapsed, 1),
                    "models_available": len(data.get("models", [])),
                    "sample_models": models,
                    "checked_at": datetime.now().isoformat()
                }
            else:
                return {
                    "name": "Google Gemini",
                    "status": "unhealthy",
                    "status_code": response.status_code,
                    "response_time_ms": round(elapsed, 1),
                    "error": response.text[:200],
                    "checked_at": datetime.now().isoformat()
                }
        except Exception as e:
            return {
                "name": "Google Gemini",
                "status": "error",
                "error": str(e),
                "checked_at": datetime.now().isoformat()
            }

    async def check_calendly(self) -> Dict[str, Any]:
        """Check Calendly API health (if token available)"""
        return {
            "name": "Calendly",
            "status": "not_configured",
            "message": "OAuth token required",
            "checked_at": datetime.now().isoformat()
        }

    async def check_stripe(self) -> Dict[str, Any]:
        """Check Stripe API health (basic connectivity)"""
        client = await self._get_client()
        try:
            start = datetime.now()
            response = await client.get("https://api.stripe.com/")
            elapsed = (datetime.now() - start).total_seconds() * 1000
            
            return {
                "name": "Stripe",
                "status": "reachable",
                "status_code": response.status_code,
                "response_time_ms": round(elapsed, 1),
                "message": "API reachable",
                "checked_at": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "name": "Stripe",
                "status": "error",
                "error": str(e),
                "checked_at": datetime.now().isoformat()
            }

    async def collect_all(self) -> Dict[str, Any]:
        """Collect health status of all integrations"""
        moskit = await self.check_moskit()
        gemini = await self.check_gemini()
        calendly = await self.check_calendly()
        stripe = await self.check_stripe()
        
        all_checks = [moskit, gemini, stripe]
        healthy = sum(1 for c in all_checks if c.get("status") in ["healthy", "reachable"])
        
        result = {
            "moskit": moskit,
            "gemini": gemini,
            "calendly": calendly,
            "stripe": stripe,
            "summary": {
                "total": len(all_checks),
                "healthy": healthy,
                "unhealthy": len(all_checks) - healthy
            },
            "collected_at": datetime.now().isoformat()
        }
        
        self._last_results = result
        return result

    def get_last_results(self) -> Dict[str, Any]:
        return self._last_results


# Singleton instance
integrations_collector = IntegrationsCollector()
