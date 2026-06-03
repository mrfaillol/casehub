"""
Application Metrics Collector
Collects specific metrics from CaseHub, CaseHub Tools, and Intake
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List
import os
import re
import glob
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from config import DATABASE_URL


class ApplicationsCollector:
    """Collects application-specific metrics"""

    def __init__(self):
        self._engine = None
        self._Session = None

    def _get_session(self):
        """Get database session"""
        if self._engine is None:
            self._engine = create_engine(DATABASE_URL)
            self._Session = sessionmaker(bind=self._engine)
        return self._Session()

    def collect_casehub(self) -> Dict[str, Any]:
        """Collect CaseHub metrics from database"""
        try:
            session = self._get_session()

            # Total counts
            clients_total = session.execute(text("SELECT COUNT(*) FROM clients")).scalar() or 0
            cases_total = session.execute(text("SELECT COUNT(*) FROM cases")).scalar() or 0
            cases_active = session.execute(
                text("SELECT COUNT(*) FROM cases WHERE status != 'closed'")
            ).scalar() or 0

            # Cases by status
            cases_by_status = {}
            status_result = session.execute(text("""
                SELECT status, COUNT(*) as count
                FROM cases
                GROUP BY status
            """))
            for row in status_result:
                cases_by_status[row.status or "unknown"] = row.count

            # Cases created today
            today = datetime.now().date()
            cases_today = session.execute(
                text("SELECT COUNT(*) FROM cases WHERE DATE(submitted_at) = :today"),
                {"today": today}
            ).scalar() or 0

            # Recent activity (last 24h)
            yesterday = datetime.now() - timedelta(hours=24)
            try:
                recent_activity = session.execute(
                    text("""
                        SELECT COUNT(*) FROM audit_log
                        WHERE created_at > :since
                    """),
                    {"since": yesterday}
                ).scalar() or 0
            except:
                recent_activity = 0

            # Active sessions
            try:
                active_sessions = session.execute(
                    text("""
                        SELECT COUNT(*) FROM portal_sessions
                        WHERE expires_at > NOW()
                    """)
                ).scalar() or 0
            except:
                active_sessions = 0

            session.close()

            return {
                "timestamp": datetime.now().isoformat(),
                "clients": {
                    "total": clients_total,
                },
                "cases": {
                    "total": cases_total,
                    "active": cases_active,
                    "today": cases_today,
                    "by_status": cases_by_status,
                },
                "activity": {
                    "last_24h": recent_activity,
                    "active_sessions": active_sessions,
                }
            }

        except Exception as e:
            return {
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
            }

    def collect_intake(self) -> Dict[str, Any]:
        """Collect Intake package metrics"""
        try:
            session = self._get_session()

            # Package counts by status
            packages_by_status = {}
            try:
                status_result = session.execute(text("""
                    SELECT status, COUNT(*) as count
                    FROM intake_packages
                    GROUP BY status
                """))
                for row in status_result:
                    packages_by_status[row.status or "unknown"] = row.count
            except:
                pass

            total_packages = sum(packages_by_status.values())

            # Packages created today
            today = datetime.now().date()
            try:
                packages_today = session.execute(
                    text("SELECT COUNT(*) FROM intake_packages WHERE DATE(submitted_at) = :today"),
                    {"today": today}
                ).scalar() or 0
            except:
                packages_today = 0

            # Submissions today
            try:
                submissions_today = session.execute(
                    text("""
                        SELECT COUNT(*) FROM intake_responses
                        WHERE DATE(submitted_at) = :today
                    """),
                    {"today": today}
                ).scalar() or 0
            except:
                submissions_today = 0

            # Completion rate
            completed = packages_by_status.get("completed", 0)
            completion_rate = round(completed / total_packages * 100) if total_packages > 0 else 0

            session.close()

            return {
                "timestamp": datetime.now().isoformat(),
                "packages": {
                    "total": total_packages,
                    "by_status": packages_by_status,
                    "today": packages_today,
                },
                "submissions": {
                    "today": submissions_today,
                },
                "metrics": {
                    "completion_rate": completion_rate,
                }
            }

        except Exception as e:
            return {
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
            }

    def collect_tools(self) -> Dict[str, Any]:
        """Collect CaseHub Tools metrics from logs and filesystem"""
        try:
            # Count generated documents in output directory
            output_dir = os.getenv("APP_BASE_PATH", "/opt/casehub") + "/ilc-tools/output"
            files_today = 0
            total_files = 0
            today = datetime.now().date()

            if os.path.exists(output_dir):
                for f in os.listdir(output_dir):
                    filepath = os.path.join(output_dir, f)
                    if os.path.isfile(filepath) and (f.endswith('.docx') or f.endswith('.pdf')):
                        total_files += 1
                        mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                        if mtime.date() == today:
                            files_today += 1

            # Parse CaseHub Tools daily log for requests
            requests_last_hour = 0
            sessions_today = 0
            log_dir = os.getenv("APP_BASE_PATH", "/opt/casehub") + "/ilc-tools/logs"
            today_str = datetime.now().strftime("%Y%m%d")
            today_log = os.path.join(log_dir, f"ilc_{today_str}.log")

            if os.path.exists(today_log):
                try:
                    one_hour_ago = datetime.now() - timedelta(hours=1)
                    with open(today_log, 'r') as f:
                        for line in f:
                            # Count sessions created today
                            if 'Session created for' in line:
                                sessions_today += 1
                            # Count requests in last hour
                            match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                            if match:
                                try:
                                    log_time = datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S')
                                    if log_time > one_hour_ago:
                                        requests_last_hour += 1
                                except:
                                    pass
                except:
                    pass

            # Also count from PM2 logs for last hour
            pm2_log = "/root/.pm2/logs/ilc-tools-out.log"
            if os.path.exists(pm2_log):
                try:
                    one_hour_ago = datetime.now() - timedelta(hours=1)
                    with open(pm2_log, 'r') as f:
                        lines = f.readlines()[-500:]  # Last 500 lines
                        for line in lines:
                            # Skip health checks from monitor
                            if '127.0.0.1' in line and 'GET / HTTP' in line:
                                continue
                            if 'HTTP/1.1' in line and '200 OK' in line:
                                # Parse timestamp from uvicorn format
                                match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                                if match:
                                    try:
                                        log_time = datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S')
                                        if log_time > one_hour_ago:
                                            requests_last_hour += 1
                                    except:
                                        pass
                except:
                    pass

            return {
                "timestamp": datetime.now().isoformat(),
                "documents": {
                    "generated_today": files_today,
                    "total_files": total_files,
                },
                "requests": {
                    "last_hour": requests_last_hour,
                },
                "sessions": {
                    "today": sessions_today,
                },
            }

        except Exception as e:
            return {
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
            }

    def get_recent_activity(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent activity from all application logs"""
        activities = []

        # Parse CaseHub Tools log
        log_dir = os.getenv("APP_BASE_PATH", "/opt/casehub") + "/ilc-tools/logs"
        today_str = datetime.now().strftime("%Y%m%d")
        today_log = os.path.join(log_dir, f"ilc_{today_str}.log")

        if os.path.exists(today_log):
            try:
                with open(today_log, 'r') as f:
                    lines = f.readlines()[-50:]
                    for line in lines:
                        match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ - (\w+) - (.+)', line)
                        if match:
                            timestamp, level, message = match.groups()
                            # Filter meaningful events
                            if any(x in message for x in ['Session created', 'LOR', 'PDF', 'generated', 'created']):
                                activities.append({
                                    "timestamp": timestamp,
                                    "service": "tools",
                                    "level": level,
                                    "message": message[:100],
                                })
            except:
                pass

        # Parse CaseHub PM2 log
        casehub_log = "/root/.pm2/logs/casehub-out.log"
        if os.path.exists(casehub_log):
            try:
                with open(casehub_log, 'r') as f:
                    lines = f.readlines()[-100:]
                    for line in lines:
                        # Look for meaningful requests (not just health checks)
                        if 'POST' in line or ('GET' in line and '/login' not in line and '200 OK' in line):
                            # Extract request path
                            match = re.search(r'"(GET|POST|PUT|DELETE) ([^"]+) HTTP', line)
                            if match:
                                method, path = match.groups()
                                # Skip static files and health checks
                                if '/static/' in path or path == '/':
                                    continue
                                # Get timestamp
                                time_match = re.search(r'(\d{2}:\d{2}:\d{2})', line)
                                timestamp = time_match.group(1) if time_match else datetime.now().strftime('%H:%M:%S')
                                activities.append({
                                    "timestamp": timestamp,
                                    "service": "casehub",
                                    "level": "INFO",
                                    "message": f"{method} {path}",
                                })
            except:
                pass

        # Sort by timestamp (most recent first) and limit
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        return activities[:limit]

    def collect_all(self) -> Dict[str, Any]:
        """Collect metrics from all applications"""
        return {
            "timestamp": datetime.now().isoformat(),
            "casehub": self.collect_casehub(),
            "intake": self.collect_intake(),
            "tools": self.collect_tools(),
            "recent_activity": self.get_recent_activity(),
        }


# Singleton instance
applications_collector = ApplicationsCollector()
