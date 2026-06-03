"""
Database Metrics Collector
Collects metrics from MySQL and PostgreSQL databases
"""
import os
import mysql.connector
import psycopg2
from datetime import datetime
from typing import Dict, Any


class DatabaseCollector:
    """Collects database metrics"""

    def __init__(self):
        self._last_results = {}

        # MySQL config (WhatsApp Bot database)
        self.mysql_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "user": os.environ["DB_USER"],
            "password": os.environ["DB_PASSWORD"],
            "database": os.environ["DB_NAME"]
        }

        # PostgreSQL config (CaseHub database)
        self.pg_config = {
            "host": os.getenv("PG_HOST", "localhost"),
            "port": int(os.getenv("PG_PORT", "5432")),
            "user": os.environ["PG_USER"],
            "password": os.environ["PG_PASSWORD"],
            "database": os.environ["PG_DATABASE"]
        }

    def get_mysql_metrics(self) -> Dict[str, Any]:
        """Get MySQL database metrics"""
        try:
            conn = mysql.connector.connect(**self.mysql_config)
            cursor = conn.cursor(dictionary=True)
            
            # Active connections
            cursor.execute("SHOW PROCESSLIST")
            processes = cursor.fetchall()
            active_connections = len(processes)
            
            # Database size
            cursor.execute("""
                SELECT 
                    ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) as size_mb
                FROM information_schema.tables 
                WHERE table_schema = %s
            """, (self.mysql_config["database"],))
            size_result = cursor.fetchone()
            db_size_mb = size_result["size_mb"] if size_result else 0
            
            # Table counts
            cursor.execute("""
                SELECT COUNT(*) as count FROM information_schema.tables 
                WHERE table_schema = %s
            """, (self.mysql_config["database"],))
            table_count = cursor.fetchone()["count"]
            
            # Row counts for main tables
            cursor.execute("SELECT COUNT(*) as count FROM leads")
            leads_count = cursor.fetchone()["count"]
            
            cursor.execute("SELECT COUNT(*) as count FROM conversations")
            conversations_count = cursor.fetchone()["count"]
            
            cursor.close()
            conn.close()
            
            return {
                "name": "MySQL (WhatsApp)",
                "status": "healthy",
                "active_connections": active_connections,
                "database_size_mb": float(db_size_mb) if db_size_mb else 0,
                "table_count": table_count,
                "leads_total": leads_count,
                "conversations_total": conversations_count,
                "checked_at": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "name": "MySQL (WhatsApp)",
                "status": "error",
                "error": str(e),
                "checked_at": datetime.now().isoformat()
            }

    def get_postgres_metrics(self) -> Dict[str, Any]:
        """Get PostgreSQL database metrics"""
        try:
            conn = psycopg2.connect(**self.pg_config)
            cursor = conn.cursor()
            
            # Active connections
            cursor.execute("""
                SELECT COUNT(*) FROM pg_stat_activity 
                WHERE datname = %s AND state = 'active'
            """, (self.pg_config["database"],))
            active_connections = cursor.fetchone()[0]
            
            # Total connections
            cursor.execute("""
                SELECT COUNT(*) FROM pg_stat_activity 
                WHERE datname = %s
            """, (self.pg_config["database"],))
            total_connections = cursor.fetchone()[0]
            
            # Database size
            cursor.execute("""
                SELECT pg_size_pretty(pg_database_size(%s)) as size
            """, (self.pg_config["database"],))
            db_size = cursor.fetchone()[0]
            
            # Table count
            cursor.execute("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            table_count = cursor.fetchone()[0]
            
            # Row counts for main tables
            cursor.execute("SELECT COUNT(*) FROM clients")
            clients_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM cases")
            cases_count = cursor.fetchone()[0]
            
            cursor.close()
            conn.close()
            
            return {
                "name": "PostgreSQL (CaseHub)",
                "status": "healthy",
                "active_connections": active_connections,
                "total_connections": total_connections,
                "database_size": db_size,
                "table_count": table_count,
                "clients_total": clients_count,
                "cases_total": cases_count,
                "checked_at": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "name": "PostgreSQL (CaseHub)",
                "status": "error",
                "error": str(e),
                "checked_at": datetime.now().isoformat()
            }

    def get_redis_metrics(self) -> Dict[str, Any]:
        """Get Redis metrics"""
        try:
            import redis
            r = redis.Redis(host="localhost", port=6379, decode_responses=True)
            info = r.info()
            
            return {
                "name": "Redis",
                "status": "healthy",
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "N/A"),
                "total_keys": r.dbsize(),
                "uptime_days": info.get("uptime_in_days", 0),
                "checked_at": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "name": "Redis",
                "status": "error",
                "error": str(e),
                "checked_at": datetime.now().isoformat()
            }

    def collect_all(self) -> Dict[str, Any]:
        """Collect all database metrics including Redis"""
        mysql = self.get_mysql_metrics()
        postgres = self.get_postgres_metrics()
        redis_data = self.get_redis_metrics()
        
        databases = [mysql, postgres, redis_data]
        healthy = sum(1 for db in databases if db.get("status") == "healthy")
        
        result = {
            "mysql": mysql,
            "postgres": postgres,
            "redis": redis_data,
            "summary": {
                "total": 3,
                "healthy": healthy,
                "unhealthy": 3 - healthy
            },
            "collected_at": datetime.now().isoformat()
        }
        
        self._last_results = result
        return result

    def get_last_results(self) -> Dict[str, Any]:
        return self._last_results


# Singleton instance
database_collector = DatabaseCollector()
