"""
System Metrics Collector
Collects CPU, RAM, Disk, Network, and Load metrics using psutil
"""
import psutil
import time
from datetime import datetime
from collections import deque
from typing import Dict, Any, List

from config import HISTORY_MAX_POINTS


class SystemCollector:
    """Collects system metrics using psutil"""

    def __init__(self):
        self.history: Dict[str, deque] = {
            "cpu": deque(maxlen=HISTORY_MAX_POINTS),
            "ram": deque(maxlen=HISTORY_MAX_POINTS),
            "network_in": deque(maxlen=HISTORY_MAX_POINTS),
            "network_out": deque(maxlen=HISTORY_MAX_POINTS),
        }
        self._last_net_io = psutil.net_io_counters()
        self._last_net_time = time.time()

    def collect(self) -> Dict[str, Any]:
        """Collect all system metrics"""
        now = datetime.now()
        timestamp = now.isoformat()

        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()

        # RAM
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()

        # Disk
        disk = psutil.disk_usage('/')

        # Load Average
        load_avg = psutil.getloadavg()

        # Network
        net_io = psutil.net_io_counters()
        current_time = time.time()
        time_delta = current_time - self._last_net_time

        if time_delta > 0:
            bytes_in_per_sec = (net_io.bytes_recv - self._last_net_io.bytes_recv) / time_delta
            bytes_out_per_sec = (net_io.bytes_sent - self._last_net_io.bytes_sent) / time_delta
        else:
            bytes_in_per_sec = 0
            bytes_out_per_sec = 0

        self._last_net_io = net_io
        self._last_net_time = current_time

        # Network connections
        try:
            connections = len(psutil.net_connections())
        except (psutil.AccessDenied, PermissionError):
            connections = 0

        # Boot time
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime_seconds = (now - boot_time).total_seconds()

        # Store in history
        self.history["cpu"].append({"time": timestamp, "value": cpu_percent})
        self.history["ram"].append({"time": timestamp, "value": memory.percent})
        self.history["network_in"].append({"time": timestamp, "value": bytes_in_per_sec})
        self.history["network_out"].append({"time": timestamp, "value": bytes_out_per_sec})

        return {
            "timestamp": timestamp,
            "cpu": {
                "percent": cpu_percent,
                "count": cpu_count,
                "frequency_mhz": cpu_freq.current if cpu_freq else None,
            },
            "memory": {
                "total_gb": round(memory.total / (1024**3), 2),
                "used_gb": round(memory.used / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "percent": memory.percent,
            },
            "swap": {
                "total_gb": round(swap.total / (1024**3), 2),
                "used_gb": round(swap.used / (1024**3), 2),
                "percent": swap.percent,
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 2),
                "used_gb": round(disk.used / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "percent": disk.percent,
            },
            "load": {
                "1min": round(load_avg[0], 2),
                "5min": round(load_avg[1], 2),
                "15min": round(load_avg[2], 2),
            },
            "network": {
                "bytes_in_per_sec": round(bytes_in_per_sec),
                "bytes_out_per_sec": round(bytes_out_per_sec),
                "mb_in_per_sec": round(bytes_in_per_sec / (1024**2), 2),
                "mb_out_per_sec": round(bytes_out_per_sec / (1024**2), 2),
                "total_recv_gb": round(net_io.bytes_recv / (1024**3), 2),
                "total_sent_gb": round(net_io.bytes_sent / (1024**3), 2),
                "connections": connections,
            },
            "uptime": {
                "boot_time": boot_time.isoformat(),
                "uptime_seconds": int(uptime_seconds),
                "uptime_formatted": self._format_uptime(uptime_seconds),
            }
        }

    def get_history(self, metric: str = None) -> Dict[str, List]:
        """Get historical data for metrics"""
        if metric and metric in self.history:
            return {metric: list(self.history[metric])}
        return {k: list(v) for k, v in self.history.items()}

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        """Format uptime in human readable format"""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")

        return " ".join(parts) if parts else "< 1m"


# Singleton instance
system_collector = SystemCollector()
