"""
Sentinela - Canary Checker
13 business flow tests that verify actual functionality, not just HTTP 200.
Each canary returns (passed: bool, latency_ms: float, error: str|None).
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp

logger = logging.getLogger("sentinela.canary")

CANARY_TIMEOUT = aiohttp.ClientTimeout(total=10)


class CanaryChecker:
    def __init__(self, config: dict):
        self.config = config
        self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=CANARY_TIMEOUT)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def run_all(self) -> list[dict]:
        """Run all 13 canary checks. Returns list of result dicts."""
        checks = [
            ("whatsapp_connected", self.check_whatsapp_connected),
            ("casehub_login_renders", self.check_casehub_login_renders),
            ("casehub_api_responds", self.check_casehub_api),
            ("ilctools_loads", self.check_ilctools_loads),
            ("nginx_proxy_works", self.check_nginx_proxy),
            ("email_cron_recent", self.check_email_cron_recent),
            ("mariadb_responsive", self.check_mariadb),
            ("postgresql_responsive", self.check_postgresql),
            ("notion_reachable", self.check_notion_reachable),
            ("n8n_webhooks_active", self.check_n8n_webhooks),
            ("vps_monitor_api", self.check_vps_monitor),
            ("maestro_responsive", self.check_maestro),
            ("disk_space_ok", self.check_disk_space),
        ]

        results = []
        for name, check_fn in checks:
            start = time.monotonic()
            try:
                passed, error = await asyncio.wait_for(check_fn(), timeout=15)
                latency = (time.monotonic() - start) * 1000
            except asyncio.TimeoutError:
                latency = (time.monotonic() - start) * 1000
                passed, error = False, "timeout (15s)"
            except Exception as e:
                latency = (time.monotonic() - start) * 1000
                passed, error = False, str(e)

            results.append({
                "check_name": name,
                "passed": passed,
                "latency_ms": round(latency, 1),
                "error": error,
            })

        return results

    def get_canaries_for_service(self, results: list[dict], service: str) -> list[dict]:
        """Filter canary results relevant to a specific service."""
        service_canaries = self.config.get("services", {}).get(service, {}).get("canaries", [])
        return [r for r in results if r["check_name"] in service_canaries]

    # --- Individual Canary Checks ---

    async def check_whatsapp_connected(self) -> tuple[bool, str | None]:
        """#1 Priority: WhatsApp session is connected and active."""
        session = await self._get_session()
        async with session.get("http://127.0.0.1:3001/api/status") as resp:
            if resp.status != 200:
                return False, f"HTTP {resp.status}"
            data = await resp.json()
            connected = data.get("connected", False) or data.get("status") == "connected"
            if not connected:
                return False, f"WA disconnected: {data.get('status', 'unknown')}"
            return True, None

    async def check_casehub_login_renders(self) -> tuple[bool, str | None]:
        """#2: CaseHub login page renders without Jinja2 errors."""
        session = await self._get_session()
        async with session.get("http://127.0.0.1:8001/login") as resp:
            if resp.status != 200:
                return False, f"HTTP {resp.status}"
            body = await resp.text()
            # Check for Jinja2 error traces
            if "TemplateSyntaxError" in body or "UndefinedError" in body:
                return False, "Jinja2 error in login page"
            if "Internal Server Error" in body:
                return False, "500 error in login page"
            if "login" not in body.lower() and "password" not in body.lower():
                return False, "Login form not found in response"
            return True, None

    async def check_casehub_api(self) -> tuple[bool, str | None]:
        """#3: CaseHub API health endpoint."""
        session = await self._get_session()
        async with session.get("http://127.0.0.1:8001/api/health") as resp:
            if resp.status == 200:
                return True, None
            return False, f"HTTP {resp.status}"

    async def check_ilctools_loads(self) -> tuple[bool, str | None]:
        """#4: CaseHub Tools main page loads with substantial content."""
        session = await self._get_session()
        async with session.get("http://127.0.0.1:8000/") as resp:
            if resp.status != 200:
                return False, f"HTTP {resp.status}"
            body = await resp.text()
            if len(body) < 1000:
                return False, f"Response too small ({len(body)} bytes)"
            return True, None

    async def check_nginx_proxy(self) -> tuple[bool, str | None]:
        """#5: Nginx reverse proxy is functional (check actual site, not default)."""
        session = await self._get_session()
        try:
            async with session.get("http://127.0.0.1:80/casehub/",
                                   headers={"Host": "casehub.app"},
                                   allow_redirects=False) as resp:
                if resp.status in (200, 301, 302, 308):
                    return True, None
                return False, f"HTTP {resp.status}"
        except Exception as e:
            return False, str(e)

    async def check_email_cron_recent(self) -> tuple[bool, str | None]:
        """#6: Email automation ran recently. Checks heartbeat file first, then log mtime."""
        # Primary: heartbeat file written by email_automation_wrapper.sh every 5min
        heartbeat_path = Path("/var/log/casehub/email_automation.heartbeat")
        if heartbeat_path.exists():
            try:
                ts = int(heartbeat_path.read_text().strip())
                import time
                age_min = (time.time() - ts) / 60
                if age_min < 15:
                    return True, None
                return False, f"Heartbeat stale: {age_min:.0f}min ago"
            except (ValueError, OSError):
                pass

        # Fallback: check log file modification time
        log_paths = [
            "/var/log/casehub/email_automation.log",
            "/var/log/casehub/email_processor.log",
        ]
        for path in log_paths:
            p = Path(path)
            if p.exists() and p.stat().st_size > 0:
                mtime = datetime.fromtimestamp(p.stat().st_mtime)
                age = datetime.now() - mtime
                if age < timedelta(minutes=15):
                    return True, None
                return False, f"Log stale: last modified {age.total_seconds()/60:.0f}min ago"
        return False, "No email automation log found"

    async def check_mariadb(self) -> tuple[bool, str | None]:
        """#7: MariaDB responds to queries."""
        proc = await asyncio.create_subprocess_exec(
            "mysql", "-e", "SELECT 1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
        if proc.returncode == 0:
            return True, None
        return False, stderr.decode().strip()[:200]

    async def check_postgresql(self) -> tuple[bool, str | None]:
        """#8: PostgreSQL responds to queries."""
        proc = await asyncio.create_subprocess_exec(
            "sudo", "-u", "postgres", "psql", "-c", "SELECT 1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
        if proc.returncode == 0:
            return True, None
        return False, stderr.decode().strip()[:200]

    async def check_notion_reachable(self) -> tuple[bool, str | None]:
        """#9: Notion API is reachable."""
        session = await self._get_session()
        try:
            async with session.get("https://api.notion.com/v1/users",
                                   headers={"Notion-Version": "2022-06-28",
                                            "Authorization": "Bearer noop"}) as resp:
                # 401 means API is reachable (just no auth)
                if resp.status in (200, 401):
                    return True, None
                return False, f"HTTP {resp.status}"
        except Exception as e:
            return False, f"Notion unreachable: {e}"

    async def check_n8n_webhooks(self) -> tuple[bool, str | None]:
        """#10: n8n webhook endpoint responds."""
        session = await self._get_session()
        # n8n health check
        try:
            async with session.get("http://127.0.0.1:5678/healthz") as resp:
                if resp.status == 200:
                    return True, None
                return False, f"HTTP {resp.status}"
        except Exception as e:
            return False, str(e)

    async def check_vps_monitor(self) -> tuple[bool, str | None]:
        """#11: VPS Monitor API functional."""
        session = await self._get_session()
        async with session.get("http://127.0.0.1:8010/api/health") as resp:
            if resp.status == 200:
                return True, None
            return False, f"HTTP {resp.status}"

    async def check_maestro(self) -> tuple[bool, str | None]:
        """#12: Maestro health check (tries multiple endpoints)."""
        session = await self._get_session()
        for endpoint in ["/health", "/status", "/"]:
            try:
                async with session.get(f"http://127.0.0.1:8020{endpoint}") as resp:
                    if resp.status == 200:
                        return True, None
            except Exception:
                continue
        return False, "Maestro not responding on any endpoint"

    async def check_disk_space(self) -> tuple[bool, str | None]:
        """#13: Disk space > 20% free."""
        proc = await asyncio.create_subprocess_exec(
            "df", "-h", "/",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        lines = stdout.decode().strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            for part in parts:
                if part.endswith("%"):
                    used = int(part.rstrip("%"))
                    free = 100 - used
                    if free >= 20:
                        return True, None
                    return False, f"Disk {used}% used ({free}% free)"
        return False, "Could not parse df output"
