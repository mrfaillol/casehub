"""
Sentinela - Smart Healer
Dependency-aware healing with circuit breaker, pre-diagnosis,
and pattern lookup before taking action.
CRITICAL: NEVER uses pm2 delete. Only pm2 restart.
"""

import asyncio
import logging
import time

logger = logging.getLogger("sentinela.healer")

# Dependency graph: key depends on values
DEPENDENCIES = {
    "casehub": ["mariadb", "nginx"],
    "whatsapp-bot": ["mariadb", "nginx"],
    "ilc-tools": ["postgresql", "nginx"],
    "n8n": ["nginx"],
    "vps-monitor": ["nginx"],
}

# Services that can only be escalated, never auto-restarted
ESCALATE_ONLY = {"mariadb", "postgresql", "nginx"}


class SmartHealer:
    def __init__(self, config: dict, incident_db, alert_manager):
        self.config = config
        self.db = incident_db
        self.alerts = alert_manager
        healing_cfg = config.get("healing", {})
        self.enabled = healing_cfg.get("auto_heal_enabled", False)
        self.allowed = set(healing_cfg.get("auto_restart_allowed", []))
        self.max_attempts = healing_cfg.get("circuit_breaker_max_attempts", 3)
        self.window_hours = healing_cfg.get("circuit_breaker_window_hours", 1)

    async def evaluate_and_heal(self, service: str, score: float,
                                dimensions: dict, all_scores: dict) -> dict:
        """
        Evaluate whether a service needs healing and take action if appropriate.

        Returns dict with:
            - action_taken: str (none, restart, escalate)
            - reason: str
            - details: str
        """
        from health_scorer import severity_from_score, RED

        severity = severity_from_score(score)

        # Only act on RED or CRITICAL
        if severity in ("GREEN", "YELLOW"):
            return {"action_taken": "none", "reason": "score acceptable", "details": ""}

        if not self.enabled:
            await self.alerts.alert(severity, f"Score {score:.0f} - auto-heal disabled", service)
            return {"action_taken": "none", "reason": "auto-heal disabled", "details": ""}

        # Step 0: Crash loop detection
        actual_restarts = signals.get("actual_restart_count", 0) if hasattr(self, '_last_signals') else 0
        uptime_ms = signals.get("uptime_ms", 0) if hasattr(self, '_last_signals') else 0
        # If many restarts AND short uptime, it's a crash loop - don't restart, escalate
        if dimensions.get("stability", 100) == 0 and dimensions.get("resources", 100) < 30:
            msg = (f"Crash loop detected: {service} (stability=0, resources={dimensions.get('resources', 0):.0f}). "
                   f"NOT restarting - escalating for manual intervention.")
            logger.warning(msg)
            await self.alerts.alert("CRITICAL", msg, service)
            return {"action_taken": "escalate", "reason": "crash_loop_detected", "details": msg}

        # Step 1: Check circuit breaker
        recent_count = await self.db.get_recent_healing_count(service, self.window_hours)
        if recent_count >= self.max_attempts:
            msg = (f"Circuit breaker OPEN: {service} restarted {recent_count}x "
                   f"in last {self.window_hours}h (max {self.max_attempts})")
            logger.warning(msg)
            await self.alerts.alert("CRITICAL", msg, service)
            return {"action_taken": "escalate", "reason": "circuit breaker", "details": msg}

        # Step 2: Check dependencies first
        deps = DEPENDENCIES.get(service, [])
        for dep in deps:
            dep_score_data = all_scores.get(dep, {})
            dep_score = dep_score_data.get("score", 100)
            if dep_score < RED:
                msg = f"Dependency {dep} is unhealthy (score {dep_score:.0f}). Fix {dep} first."
                logger.info(msg)
                await self.alerts.alert(severity, msg, service)
                # Try to heal dependency instead
                if dep not in ESCALATE_ONLY:
                    return await self.evaluate_and_heal(
                        dep, dep_score, dep_score_data.get("dimensions", {}), all_scores
                    )
                return {"action_taken": "escalate", "reason": f"dependency {dep} failing",
                        "details": msg}

        # Step 3: Check if service is in allowed list
        if service not in self.allowed:
            msg = f"Service {service} not in auto-restart allowed list"
            await self.alerts.alert(severity, f"Score {score:.0f} - {msg}", service)
            return {"action_taken": "escalate", "reason": msg, "details": ""}

        if service in ESCALATE_ONLY:
            msg = f"Service {service} is escalate-only - manual intervention required"
            await self.alerts.alert("CRITICAL", f"Score {score:.0f} - {msg}", service)
            return {"action_taken": "escalate", "reason": msg, "details": ""}

        # Step 4: Check for known pattern with fix
        fingerprint = self.db.make_fingerprint(service, "low_score", f"score={int(score)}")
        pattern = await self.db.get_pattern(fingerprint)
        if pattern and pattern.get("fix_action") and pattern.get("success_rate", 0) > 0.5:
            fix_action = pattern["fix_action"]
            logger.info(f"Known pattern for {service}: {fix_action} "
                        f"(success rate: {pattern['success_rate']:.0%})")

        # Step 5: Diagnose which dimension is failing
        failing_dim = self._identify_failing_dimension(dimensions)

        # Step 6: Take action
        action = "pm2_restart"
        if failing_dim == "http_health" and dimensions.get("pm2_status", 0) >= 80:
            # PM2 is fine but HTTP is failing - might be app crash loop
            action = "pm2_restart"
        elif failing_dim == "pm2_status":
            action = "pm2_restart"

        return await self._execute_action(service, action, score, failing_dim)

    def _identify_failing_dimension(self, dimensions: dict) -> str:
        """Find the dimension contributing most to the low score."""
        worst = None
        worst_score = 100
        for dim, score in dimensions.items():
            if score < worst_score:
                worst_score = score
                worst = dim
        return worst or "unknown"

    async def _execute_action(self, service: str, action: str,
                              score: float, reason: str) -> dict:
        """Execute a healing action. Returns result dict."""
        start = time.monotonic()

        # Create incident first
        incident_id = await self.db.create_incident(
            service=service,
            incident_type="auto_heal",
            severity="RED",
            details=f"Score {score:.0f}, failing dimension: {reason}",
            symptoms=f"score={int(score)}"
        )

        if action == "pm2_restart":
            result = await self._pm2_restart(service)
        elif action == "nginx_reload":
            result = await self._nginx_reload()
        else:
            result = f"Unknown action: {action}"

        duration = (time.monotonic() - start) * 1000

        success = "success" in str(result).lower() or "ok" in str(result).lower()

        # Log the healing action
        await self.db.log_healing_action(
            incident_id=incident_id,
            service=service,
            action=action,
            result=str(result),
            duration_ms=duration
        )

        # Update pattern
        fingerprint = self.db.make_fingerprint(service, "low_score", f"score={int(score)}")
        await self.db.update_pattern_fix(fingerprint, action, success)

        if success:
            await self.db.resolve_incident(incident_id)
            msg = f"Auto-healed {service}: {action} (was score {score:.0f}, reason: {reason})"
            logger.info(msg)
            await self.alerts.alert("YELLOW", msg, service)
        else:
            msg = f"Healing FAILED for {service}: {action} returned {result}"
            logger.error(msg)
            await self.alerts.alert("CRITICAL", msg, service)

        return {
            "action_taken": action,
            "reason": reason,
            "details": str(result),
            "success": success,
            "duration_ms": duration,
        }

    async def _pm2_restart(self, service: str) -> str:
        """Restart a service via PM2. NEVER delete."""
        logger.info(f"Executing: pm2 restart {service}")
        try:
            proc = await asyncio.create_subprocess_exec(
                "pm2", "restart", service,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode == 0:
                # Wait a bit for service to come up
                await asyncio.sleep(5)
                return f"success: pm2 restart {service}"
            return f"failed (exit {proc.returncode}): {stderr.decode()[:200]}"
        except asyncio.TimeoutError:
            return "failed: pm2 restart timed out (30s)"
        except Exception as e:
            return f"failed: {e}"

    async def _nginx_reload(self) -> str:
        """Reload nginx config after testing."""
        # Test first
        test = await asyncio.create_subprocess_exec(
            "nginx", "-t",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await test.communicate()
        if test.returncode != 0:
            return f"nginx -t failed: {stderr.decode()[:200]}"

        # Reload
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "reload", "nginx",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode == 0:
            return "success: nginx reloaded"
        return f"failed: {stderr.decode()[:200]}"
