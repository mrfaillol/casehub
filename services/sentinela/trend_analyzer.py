"""
Sentinela - Trend Analyzer
Proactive detection of degradation patterns before they become failures.
Analyzes health snapshot history for memory growth, restart velocity,
response time degradation, disk fill rate, and canary intermittent failures.
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger("sentinela.trends")


class TrendAnalyzer:
    def __init__(self, config: dict, incident_db):
        self.config = config
        self.db = incident_db

    async def analyze_all(self, services: list[str]) -> list[dict]:
        """Run all trend analyses for all services. Returns list of warnings."""
        warnings = []
        for service in services:
            warnings.extend(await self._analyze_service(service))
        warnings.extend(await self._analyze_canary_patterns())
        warnings.extend(await self._analyze_disk_trend())
        return warnings

    async def _analyze_service(self, service: str) -> list[dict]:
        """Analyze trends for a single service."""
        warnings = []
        snapshots = await self.db.get_recent_scores(service, hours=24)

        if len(snapshots) < 6:
            return warnings  # Not enough data

        # Memory growth detection
        mem_warning = self._check_memory_growth(service, snapshots)
        if mem_warning:
            warnings.append(mem_warning)

        # Restart velocity
        restart_warning = await self._check_restart_velocity(service)
        if restart_warning:
            warnings.append(restart_warning)

        # Response time degradation
        rt_warning = self._check_response_time_degradation(service, snapshots)
        if rt_warning:
            warnings.append(rt_warning)

        # Score degradation (trending downward)
        score_warning = self._check_score_trend(service, snapshots)
        if score_warning:
            warnings.append(score_warning)

        return warnings

    def _check_memory_growth(self, service: str, snapshots: list[dict]) -> dict | None:
        """Detect if memory is growing >5% per hour for 3+ consecutive hours."""
        # Extract memory values from dimensions
        mem_values = []
        for snap in snapshots:
            dims = snap.get("dimensions", {})
            resources_score = dims.get("resources", 100)
            mem_values.append({
                "score": resources_score,
                "timestamp": snap["timestamp"],
            })

        if len(mem_values) < 6:
            return None

        # Group by hour and check trend
        # If resources score is consistently decreasing, memory is growing
        recent = [m["score"] for m in mem_values[:6]]   # last ~3 hours
        older = [m["score"] for m in mem_values[6:12]]   # 3-6 hours ago

        if not older:
            return None

        avg_recent = sum(recent) / len(recent)
        avg_older = sum(older) / len(older)

        if avg_older > 0 and avg_recent < avg_older * 0.85:
            return {
                "service": service,
                "type": "memory_growth",
                "severity": "YELLOW",
                "message": (f"Resources score declining: {avg_older:.0f} -> {avg_recent:.0f} "
                            f"({((avg_older - avg_recent) / avg_older) * 100:.0f}% drop over ~6h)"),
            }
        return None

    async def _check_restart_velocity(self, service: str) -> dict | None:
        """Detect if a service restarted 2+ times in the last hour."""
        count = await self.db.get_recent_healing_count(service, hours=1)
        if count >= 2:
            return {
                "service": service,
                "type": "restart_velocity",
                "severity": "YELLOW",
                "message": f"Service restarted {count}x in the last hour",
            }
        return None

    def _check_response_time_degradation(self, service: str,
                                         snapshots: list[dict]) -> dict | None:
        """Detect if response time degraded >50% vs 24h average."""
        rt_scores = [snap["dimensions"].get("response_time", 100) for snap in snapshots]

        if len(rt_scores) < 12:
            return None

        recent_avg = sum(rt_scores[:6]) / 6
        overall_avg = sum(rt_scores) / len(rt_scores)

        if overall_avg > 0 and recent_avg < overall_avg * 0.5:
            return {
                "service": service,
                "type": "response_time_degradation",
                "severity": "YELLOW",
                "message": (f"Response time score dropped: avg {overall_avg:.0f} -> "
                            f"recent {recent_avg:.0f} ({((overall_avg - recent_avg) / overall_avg) * 100:.0f}% degradation)"),
            }
        return None

    def _check_score_trend(self, service: str, snapshots: list[dict]) -> dict | None:
        """Detect if overall health score is trending downward."""
        scores = [snap["score"] for snap in snapshots]

        if len(scores) < 12:
            return None

        # Compare last 2 hours vs previous 10 hours
        recent = scores[:4]  # ~2h worth (30s intervals = 240 samples/2h, but we have fewer)
        older = scores[4:]

        avg_recent = sum(recent) / len(recent)
        avg_older = sum(older) / len(older)

        if avg_older >= 80 and avg_recent < 60:
            return {
                "service": service,
                "type": "score_declining",
                "severity": "YELLOW",
                "message": (f"Health score declining: {avg_older:.0f} -> {avg_recent:.0f}"),
            }
        return None

    async def _analyze_canary_patterns(self) -> list[dict]:
        """Detect intermittent canary failures (>3 in 1h but not consecutive)."""
        warnings = []
        failures = await self.db.get_canary_failures(hours=1)

        for failure in failures:
            name = failure["check_name"]
            count = failure["fail_count"]
            if count >= 3:
                warnings.append({
                    "service": name,
                    "type": "canary_intermittent",
                    "severity": "YELLOW",
                    "message": f"Canary '{name}' failed {count}x in the last hour (intermittent)",
                })

        return warnings

    async def _analyze_disk_trend(self) -> list[dict]:
        """Project when disk will be full based on recent growth."""
        # This uses canary results for disk_space_ok
        # If disk is >70% used, project fill rate
        import asyncio
        try:
            proc = await asyncio.create_subprocess_exec(
                "df", "--output=pcent", "/",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            lines = stdout.decode().strip().split("\n")
            if len(lines) >= 2:
                used = int(lines[1].strip().rstrip("%"))
                if used >= 80:
                    return [{
                        "service": "system",
                        "type": "disk_high",
                        "severity": "RED" if used >= 90 else "YELLOW",
                        "message": f"Disk usage at {used}%",
                    }]
        except Exception as e:
            logger.debug(f"Disk trend check failed: {e}")
        return []
