"""
Nginx Metrics Collector
Collects metrics from Nginx access and error logs for casehub.app
"""
import subprocess
from datetime import datetime
from typing import Dict, Any, List


class NginxCollector:
    """Collects Nginx metrics"""

    def __init__(self):
        self._last_results = {}
        self.access_log = "/var/log/nginx/casehub.app.access.log"
        self.error_log = "/var/log/nginx/casehub.app.error.log"

    def _run_cmd(self, cmd: str) -> str:
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            return result.stdout.strip()
        except:
            return ""

    def get_recent_requests(self, minutes: int = 5) -> Dict[str, Any]:
        try:
            output = self._run_cmd(f"tail -2000 {self.access_log} 2>/dev/null | wc -l")
            total_recent = int(output) if output else 0
            return {
                "requests_last_5min": min(total_recent, 500),
                "requests_per_minute": round(min(total_recent, 500) / minutes, 1)
            }
        except Exception as e:
            return {"error": str(e), "requests_last_5min": 0, "requests_per_minute": 0}

    def get_status_codes(self) -> Dict[str, int]:
        try:
            # Read logs and parse status codes using Python instead of awk
            output = self._run_cmd(f"tail -10000 {self.access_log} 2>/dev/null")
            
            codes = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0}
            for line in output.split('\n'):
                if line:
                    parts = line.split()
                    if len(parts) >= 9:
                        code = parts[8]  # Status code is field 9 (0-indexed: 8)
                        if code.startswith('2'):
                            codes["2xx"] += 1
                        elif code.startswith('3'):
                            codes["3xx"] += 1
                        elif code.startswith('4'):
                            codes["4xx"] += 1
                        elif code.startswith('5'):
                            codes["5xx"] += 1
            return codes
        except Exception as e:
            return {"error": str(e), "2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0}

    def get_error_count(self) -> Dict[str, Any]:
        try:
            output = self._run_cmd(f"tail -1000 {self.error_log} 2>/dev/null | wc -l")
            count = int(output) if output else 0
            
            last_error = self._run_cmd(f"tail -1 {self.error_log} 2>/dev/null")
            last_error = last_error[:200] if last_error else "No recent errors"
            
            return {
                "error_count_recent": count,
                "last_error": last_error
            }
        except Exception as e:
            return {"error": str(e), "error_count_recent": 0, "last_error": ""}

    def get_top_endpoints(self, limit: int = 5) -> List[Dict[str, Any]]:
        try:
            output = self._run_cmd(f"tail -5000 {self.access_log} 2>/dev/null")
            
            # Count endpoints using Python
            from collections import Counter
            paths = []
            for line in output.split('\n'):
                if line:
                    parts = line.split()
                    if len(parts) >= 7:
                        path = parts[6]  # Request path is field 7 (0-indexed: 6)
                        paths.append(path)
            
            counter = Counter(paths)
            endpoints = []
            for path, count in counter.most_common(limit):
                endpoints.append({
                    "count": count,
                    "path": path[:60]
                })
            return endpoints
        except Exception as e:
            return []

    def collect_all(self) -> Dict[str, Any]:
        requests = self.get_recent_requests()
        status_codes = self.get_status_codes()
        errors = self.get_error_count()
        top_endpoints = self.get_top_endpoints()
        
        total_requests = sum(status_codes.values())
        error_rate = (status_codes.get("4xx", 0) + status_codes.get("5xx", 0)) / max(total_requests, 1) * 100
        
        health = "healthy" if error_rate < 10 else "warning" if error_rate < 20 else "critical"
        
        result = {
            "status": health,
            "requests": requests,
            "status_codes": status_codes,
            "errors": errors,
            "top_endpoints": top_endpoints,
            "error_rate_percent": round(error_rate, 2),
            "collected_at": datetime.now().isoformat()
        }
        
        self._last_results = result
        return result

    def get_last_results(self) -> Dict[str, Any]:
        return self._last_results


nginx_collector = NginxCollector()
