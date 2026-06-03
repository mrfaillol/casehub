"""
PM2 Process Monitor Collector
Collects status and metrics from PM2 managed processes
"""
import subprocess
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from config import SERVICES


class PM2Collector:
    """Collects PM2 process information"""

    def __init__(self):
        self._last_data = None
        self._last_update = None

    def collect(self) -> Dict[str, Any]:
        """Collect all PM2 process information"""
        try:
            result = subprocess.run(
                ["pm2", "jlist"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                return {"error": "PM2 command failed", "processes": []}

            processes = json.loads(result.stdout)

            parsed = []
            for proc in processes:
                pm2_env = proc.get("pm2_env", {})
                monit = proc.get("monit", {})

                parsed.append({
                    "name": proc.get("name", "unknown"),
                    "pm_id": proc.get("pm_id"),
                    "status": pm2_env.get("status", "unknown"),
                    "cpu": monit.get("cpu", 0),
                    "memory_mb": round(monit.get("memory", 0) / (1024**2), 1),
                    "uptime_ms": pm2_env.get("pm_uptime", 0),
                    "uptime_formatted": self._format_uptime(pm2_env.get("pm_uptime", 0)),
                    "restarts": pm2_env.get("restart_time", 0),
                    "pid": proc.get("pid"),
                    "exec_mode": pm2_env.get("exec_mode", "unknown"),
                    "node_version": pm2_env.get("node_version", "N/A"),
                    "created_at": pm2_env.get("created_at"),
                })

            self._last_data = {
                "timestamp": datetime.now().isoformat(),
                "processes": parsed,
                "total": len(parsed),
                "online": sum(1 for p in parsed if p["status"] == "online"),
                "errored": sum(1 for p in parsed if p["status"] == "errored"),
                "stopped": sum(1 for p in parsed if p["status"] == "stopped"),
            }
            self._last_update = datetime.now()

            return self._last_data

        except subprocess.TimeoutExpired:
            return {"error": "PM2 command timed out", "processes": []}
        except json.JSONDecodeError:
            return {"error": "Failed to parse PM2 output", "processes": []}
        except FileNotFoundError:
            return {"error": "PM2 not found", "processes": []}
        except Exception as e:
            return {"error": str(e), "processes": []}

    def get_process(self, name: str) -> Optional[Dict[str, Any]]:
        """Get specific process by name"""
        data = self.collect()
        for proc in data.get("processes", []):
            if proc["name"] == name:
                return proc
        return None

    def restart_process(self, name: str) -> Dict[str, Any]:
        """Restart a PM2 process"""
        try:
            result = subprocess.run(
                ["pm2", "restart", name],
                capture_output=True,
                text=True,
                timeout=30
            )

            return {
                "success": result.returncode == 0,
                "message": result.stdout if result.returncode == 0 else result.stderr,
                "process": name
            }
        except Exception as e:
            return {
                "success": False,
                "message": str(e),
                "process": name
            }

    def get_logs(self, name: str, lines: int = 50) -> Dict[str, Any]:
        """Get recent logs for a process"""
        try:
            result = subprocess.run(
                ["pm2", "logs", name, "--lines", str(lines), "--nostream"],
                capture_output=True,
                text=True,
                timeout=10
            )

            return {
                "process": name,
                "logs": result.stdout + result.stderr,
                "success": True
            }
        except Exception as e:
            return {
                "process": name,
                "logs": "",
                "success": False,
                "error": str(e)
            }

    def stop_process(self, name: str) -> Dict[str, Any]:
        """Stop a PM2 process"""
        try:
            result = subprocess.run(
                ["pm2", "stop", name],
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                "success": result.returncode == 0,
                "message": result.stdout if result.returncode == 0 else result.stderr,
                "process": name,
                "action": "stop"
            }
        except Exception as e:
            return {"success": False, "message": str(e), "process": name, "action": "stop"}

    def start_process(self, name: str) -> Dict[str, Any]:
        """Start a PM2 process"""
        try:
            result = subprocess.run(
                ["pm2", "start", name],
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                "success": result.returncode == 0,
                "message": result.stdout if result.returncode == 0 else result.stderr,
                "process": name,
                "action": "start"
            }
        except Exception as e:
            return {"success": False, "message": str(e), "process": name, "action": "start"}

    def delete_process(self, name: str) -> Dict[str, Any]:
        """Delete a PM2 process"""
        try:
            result = subprocess.run(
                ["pm2", "delete", name],
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                "success": result.returncode == 0,
                "message": result.stdout if result.returncode == 0 else result.stderr,
                "process": name,
                "action": "delete"
            }
        except Exception as e:
            return {"success": False, "message": str(e), "process": name, "action": "delete"}

    def get_process_info(self, name: str) -> Dict[str, Any]:
        """Get detailed process info including env vars"""
        try:
            result = subprocess.run(
                ["pm2", "show", name, "--format=json"],
                capture_output=True,
                text=True,
                timeout=10
            )

            # pm2 show doesn't support json format, parse text output
            info = {
                "process": name,
                "raw_output": result.stdout,
                "success": result.returncode == 0
            }

            # Extract env vars from pm2 prettylist
            env_result = subprocess.run(
                ["pm2", "env", name],
                capture_output=True,
                text=True,
                timeout=10
            )
            if env_result.returncode == 0:
                env_vars = {}
                for line in env_result.stdout.split('\n'):
                    if '=' in line:
                        key, _, value = line.partition('=')
                        env_vars[key.strip()] = value.strip()
                info["env_vars"] = env_vars

            return info
        except Exception as e:
            return {"success": False, "error": str(e), "process": name}

    def flush_logs(self, name: str = None) -> Dict[str, Any]:
        """Flush logs for a process or all processes"""
        try:
            cmd = ["pm2", "flush"]
            if name:
                cmd.append(name)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return {
                "success": result.returncode == 0,
                "message": result.stdout if result.returncode == 0 else result.stderr,
                "action": "flush"
            }
        except Exception as e:
            return {"success": False, "message": str(e), "action": "flush"}

    def reload_process(self, name: str) -> Dict[str, Any]:
        """Reload a PM2 process with 0-downtime (graceful reload)"""
        try:
            result = subprocess.run(
                ["pm2", "reload", name],
                capture_output=True,
                text=True,
                timeout=60
            )
            return {
                "success": result.returncode == 0,
                "message": result.stdout if result.returncode == 0 else result.stderr,
                "process": name,
                "action": "reload"
            }
        except Exception as e:
            return {"success": False, "message": str(e), "process": name, "action": "reload"}

    def scale_process(self, name: str, instances: int) -> Dict[str, Any]:
        """Scale a PM2 process to N instances"""
        try:
            result = subprocess.run(
                ["pm2", "scale", name, str(instances)],
                capture_output=True,
                text=True,
                timeout=60
            )
            return {
                "success": result.returncode == 0,
                "message": result.stdout if result.returncode == 0 else result.stderr,
                "process": name,
                "instances": instances,
                "action": "scale"
            }
        except Exception as e:
            return {"success": False, "message": str(e), "process": name, "action": "scale"}

    def describe_process(self, name: str) -> Dict[str, Any]:
        """Get full PM2 describe output for a process"""
        try:
            result = subprocess.run(
                ["pm2", "describe", name],
                capture_output=True,
                text=True,
                timeout=10
            )

            # Also get monit info
            monit_result = subprocess.run(
                ["pm2", "monit", name, "--no-daemon"],
                capture_output=True,
                text=True,
                timeout=5
            )

            return {
                "success": result.returncode == 0,
                "process": name,
                "describe": result.stdout,
                "monit": monit_result.stdout if monit_result.returncode == 0 else None,
                "action": "describe"
            }
        except Exception as e:
            return {"success": False, "error": str(e), "process": name, "action": "describe"}

    def save(self) -> Dict[str, Any]:
        """Save current PM2 process list (pm2 save)"""
        try:
            result = subprocess.run(
                ["pm2", "save"],
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                "success": result.returncode == 0,
                "message": result.stdout if result.returncode == 0 else result.stderr,
                "action": "save"
            }
        except Exception as e:
            return {"success": False, "message": str(e), "action": "save"}

    def reset_restart_count(self, name: str) -> Dict[str, Any]:
        """Reset restart count for a process"""
        try:
            result = subprocess.run(
                ["pm2", "reset", name],
                capture_output=True,
                text=True,
                timeout=10
            )
            return {
                "success": result.returncode == 0,
                "message": result.stdout if result.returncode == 0 else result.stderr,
                "process": name,
                "action": "reset"
            }
        except Exception as e:
            return {"success": False, "message": str(e), "process": name, "action": "reset"}

    def set_memory_limit(self, name: str, max_memory: str) -> Dict[str, Any]:
        """Set memory limit for a process (e.g., '500M', '1G')"""
        try:
            # Stop the process first
            self.stop_process(name)
            # Restart with memory limit
            result = subprocess.run(
                ["pm2", "start", name, "--max-memory-restart", max_memory],
                capture_output=True,
                text=True,
                timeout=60
            )
            return {
                "success": result.returncode == 0,
                "message": result.stdout if result.returncode == 0 else result.stderr,
                "process": name,
                "max_memory": max_memory,
                "action": "set_memory_limit"
            }
        except Exception as e:
            return {"success": False, "message": str(e), "process": name, "action": "set_memory_limit"}

    @staticmethod
    def _format_uptime(uptime_ms: int) -> str:
        """Format uptime from milliseconds"""
        if not uptime_ms:
            return "N/A"

        now = datetime.now().timestamp() * 1000
        uptime_seconds = (now - uptime_ms) / 1000

        if uptime_seconds < 0:
            return "N/A"

        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")

        return " ".join(parts) if parts else "< 1m"


# Singleton instance
pm2_collector = PM2Collector()
