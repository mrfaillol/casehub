"""
Services Health Check Collector
Performs HTTP health checks on services
"""
import httpx
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

from config import SERVICES


class ServicesCollector:
    """Performs health checks on services via HTTP"""

    def __init__(self):
        self._client = None
        self._last_results = {}

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=5.0)
        return self._client

    async def check_service(self, service_key: str) -> Dict[str, Any]:
        """Check health of a single service"""
        service = SERVICES.get(service_key)
        if not service:
            return {"error": f"Unknown service: {service_key}"}

        health_url = service.get("health_url")
        if not health_url:
            return {
                "name": service["name"],
                "status": "unknown",
                "message": "No health endpoint configured",
                "response_time_ms": None,
            }

        client = await self._get_client()

        try:
            start = datetime.now()
            response = await client.get(health_url)
            elapsed = (datetime.now() - start).total_seconds() * 1000

            is_healthy = response.status_code == 200

            try:
                data = response.json()
            except:
                data = {"raw": response.text[:500]}

            result = {
                "name": service["name"],
                "status": "healthy" if is_healthy else "unhealthy",
                "status_code": response.status_code,
                "response_time_ms": round(elapsed, 1),
                "url": health_url,
                "data": data,
                "checked_at": datetime.now().isoformat(),
            }

        except httpx.ConnectError:
            result = {
                "name": service["name"],
                "status": "offline",
                "message": "Connection refused",
                "url": health_url,
                "response_time_ms": None,
                "checked_at": datetime.now().isoformat(),
            }
        except httpx.TimeoutException:
            result = {
                "name": service["name"],
                "status": "timeout",
                "message": "Request timed out",
                "url": health_url,
                "response_time_ms": None,
                "checked_at": datetime.now().isoformat(),
            }
        except Exception as e:
            result = {
                "name": service["name"],
                "status": "error",
                "message": str(e),
                "url": health_url,
                "response_time_ms": None,
                "checked_at": datetime.now().isoformat(),
            }

        self._last_results[service_key] = result
        return result

    async def check_all(self) -> Dict[str, Any]:
        """Check health of all services"""
        tasks = [self.check_service(key) for key in SERVICES.keys()]
        results = await asyncio.gather(*tasks)

        services_dict = {}
        for key, result in zip(SERVICES.keys(), results):
            services_dict[key] = result

        healthy = sum(1 for r in results if r.get("status") == "healthy")
        total = len(results)

        return {
            "timestamp": datetime.now().isoformat(),
            "services": services_dict,
            "summary": {
                "total": total,
                "healthy": healthy,
                "unhealthy": total - healthy,
                "health_percent": round(healthy / total * 100) if total > 0 else 0,
            }
        }

    def get_last_result(self, service_key: str) -> Optional[Dict[str, Any]]:
        """Get last cached result for a service"""
        return self._last_results.get(service_key)

    async def close(self):
        """Close HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton instance
services_collector = ServicesCollector()
