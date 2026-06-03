"""
Sentinela - Signal Collector
Aggregates health signals from all 5 existing monitoring systems into
a normalized format for the health scorer.
"""
import os

import asyncio
import json
import logging
import subprocess
from pathlib import Path

import aiohttp

logger = logging.getLogger("sentinela.collector")

# Default timeouts for API calls
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=5)


class SignalCollector:
    def __init__(self, config: dict):
        self.config = config
        self.services = config.get("services", {})
        self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=HTTP_TIMEOUT)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def collect_all(self) -> dict:
        """Collect signals for all configured services. Returns dict keyed by service name."""
        tasks = {name: self._collect_service(name, svc_config)
                 for name, svc_config in self.services.items()}
        results = {}
        for name, coro in tasks.items():
            try:
                results[name] = await coro
            except Exception as e:
                logger.error(f"Failed to collect signals for {name}: {e}")
                results[name] = self._empty_signals()
        return results

    async def _collect_service(self, name: str, svc_config: dict) -> dict:
        """Collect all signal dimensions for a single service."""
        port = svc_config.get("port")
        health_ep = svc_config.get("health_endpoint", "/")

        # Run collection tasks in parallel
        pm2_task = self._get_pm2_status(name)
        http_task = self._check_http(port, health_ep) if port else asyncio.coroutine(lambda: {})()
        vps_monitor_task = self._get_from_vps_monitor(name)

        pm2_data, http_data, monitor_data = await asyncio.gather(
            pm2_task, http_task, vps_monitor_task,
            return_exceptions=True
        )

        # Handle exceptions from gather
        if isinstance(pm2_data, Exception):
            logger.warning(f"PM2 data failed for {name}: {pm2_data}")
            pm2_data = {}
        if isinstance(http_data, Exception):
            logger.warning(f"HTTP check failed for {name}: {http_data}")
            http_data = {}
        if isinstance(monitor_data, Exception):
            logger.warning(f"Monitor data failed for {name}: {monitor_data}")
            monitor_data = {}

        # Use actual PM2 restart_count + uptime-based estimation
        uptime_ms = pm2_data.get("uptime", 0)
        actual_restarts = pm2_data.get("restart_count", 0)
        if uptime_ms > 0 and uptime_ms < 86400000:
            restart_estimate = min(int(86400000 / max(uptime_ms, 1)), 100)
        else:
            restart_estimate = 0

        # Per-service memory limit from config
        memory_limit = svc_config.get("memory_limit_mb", 300)
        mem_mb = pm2_data.get("memory", 0) / (1024 * 1024) if pm2_data.get("memory") else 0
        cpu_pct = pm2_data.get("cpu", 0)

        # Merge resources from monitor with PM2 data
        resources = monitor_data.get("resources", {})
        if not resources.get("memory_mb"):
            resources["memory_mb"] = mem_mb
        if not resources.get("cpu_percent"):
            resources["cpu_percent"] = cpu_pct
        resources["memory_limit_mb"] = memory_limit

        return {
            "pm2": pm2_data,
            "http": http_data,
            "response_time_ms": http_data.get("response_time_ms", 0),
            "resources": resources,
            "restart_count_24h": restart_estimate,
            "actual_restart_count": actual_restarts,
            "uptime_ms": uptime_ms,
            "canaries": [],  # filled later by canary_checker
        }

    async def _get_pm2_status(self, service_name: str) -> dict:
        """Get PM2 process status. First tries VPS Monitor API, falls back to pm2 jlist."""
        try:
            session = await self._get_session()
            async with session.get("http://127.0.0.1:8010/api/pm2") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    processes = data if isinstance(data, list) else data.get("processes", [])
                    for proc in processes:
                        pname = proc.get("name", "")
                        if pname == service_name:
                            uptime_val = proc.get("uptime", 0)
                            uptime_ms = self._parse_uptime_to_ms(uptime_val)
                            return {
                                "status": proc.get("status", "unknown"),
                                "cpu": proc.get("cpu", 0),
                                "memory": proc.get("memory", 0),
                                "restart_count": proc.get("restarts", 0),
                                "uptime": uptime_ms,
                            }
        except Exception as e:
            logger.debug(f"VPS Monitor PM2 API failed, trying pm2 jlist: {e}")

        # Fallback: direct pm2 jlist
        try:
            result = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "pm2", "jlist",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                ),
                timeout=5
            )
            stdout, _ = await result.communicate()
            processes = json.loads(stdout.decode())
            for proc in processes:
                if proc.get("name") == service_name:
                    pm2_env = proc.get("pm2_env", {})
                    monit = proc.get("monit", {})
                    # pm_uptime is epoch timestamp in ms when process started
                    pm_uptime = pm2_env.get("pm_uptime", 0)
                    if pm_uptime > 0:
                        import time
                        uptime_ms = int(time.time() * 1000) - pm_uptime
                    else:
                        uptime_ms = 0
                    return {
                        "status": pm2_env.get("status", "unknown"),
                        "cpu": monit.get("cpu", 0),
                        "memory": monit.get("memory", 0),
                        "restart_count": pm2_env.get("restart_time", 0),
                        "uptime": uptime_ms,
                    }
        except Exception as e:
            logger.warning(f"pm2 jlist fallback failed: {e}")

        return {"status": "unknown"}

    @staticmethod
    def _parse_uptime_to_ms(uptime_val) -> int:
        """Parse PM2 uptime value to milliseconds. Handles strings like '5h', '3D', '45m', '10s'."""
        if isinstance(uptime_val, (int, float)):
            return int(uptime_val)
        if not isinstance(uptime_val, str):
            return 0
        uptime_str = uptime_val.strip()
        try:
            if uptime_str.endswith("D"):
                return int(float(uptime_str[:-1]) * 86400000)
            elif uptime_str.endswith("h"):
                return int(float(uptime_str[:-1]) * 3600000)
            elif uptime_str.endswith("m"):
                return int(float(uptime_str[:-1]) * 60000)
            elif uptime_str.endswith("s"):
                return int(float(uptime_str[:-1]) * 1000)
            else:
                return int(uptime_str)
        except (ValueError, IndexError):
            return 0

    async def _check_http(self, port: int, endpoint: str) -> dict:
        """Check HTTP health endpoint. Returns status code, body validation, and response time."""
        import time
        url = f"http://127.0.0.1:{port}{endpoint}"
        start = time.monotonic()
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                elapsed = (time.monotonic() - start) * 1000
                body = await resp.text()
                return {
                    "status_code": resp.status,
                    "body_valid": len(body) > 0,
                    "body_length": len(body),
                    "response_time_ms": elapsed,
                }
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return {
                "status_code": 0,
                "body_valid": False,
                "error": str(e),
                "response_time_ms": elapsed,
            }

    async def _get_from_vps_monitor(self, service_name: str) -> dict:
        """Get resource data from VPS Monitor API."""
        try:
            session = await self._get_session()
            async with session.get("http://127.0.0.1:8010/api/pm2") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    processes = data if isinstance(data, list) else data.get("processes", [])
                    for proc in processes:
                        if proc.get("name") == service_name:
                            mem_bytes = proc.get("memory", 0)
                            return {
                                "resources": {
                                    "cpu_percent": proc.get("cpu", 0),
                                    "memory_mb": mem_bytes / (1024 * 1024) if mem_bytes else 0,
                                    "memory_limit_mb": 300,
                                }
                            }
        except Exception as e:
            logger.debug(f"VPS Monitor resource query failed for {service_name}: {e}")
        return {"resources": {"cpu_percent": 0, "memory_mb": 0, "memory_limit_mb": 300}}

    async def get_auto_healer_state(self) -> dict:
        """Read auto-healer state.json for recent actions."""
        state_path = os.getenv("APP_BASE_PATH", "/opt/casehub") + "/auto-healer/state.json"
        try:
            text = Path(state_path).read_text()
            return json.loads(text)
        except Exception as e:
            logger.debug(f"Auto-healer state read failed: {e}")
            return {}

    def _empty_signals(self) -> dict:
        return {
            "pm2": {"status": "unknown"},
            "http": {"status_code": 0, "body_valid": False},
            "response_time_ms": 0,
            "resources": {"cpu_percent": 0, "memory_mb": 0, "memory_limit_mb": 300},
            "restart_count_24h": 0,
            "canaries": [],
        }
