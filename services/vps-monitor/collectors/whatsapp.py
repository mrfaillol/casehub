"""
WhatsApp Bot Metrics Collector
Collects metrics from WhatsApp bot API and MySQL database
"""
import os
import httpx
import mysql.connector
from datetime import datetime
from typing import Dict, Any


class WhatsAppCollector:
    """Collects WhatsApp bot metrics"""

    def __init__(self):
        self._client = None
        self._db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "user": os.environ["DB_USER"],
            "password": os.environ["DB_PASSWORD"],
            "database": os.environ["DB_NAME"]
        }
        self._last_results = {}

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=5.0)
        return self._client

    async def get_status(self) -> Dict[str, Any]:
        """Get WhatsApp connection status from API"""
        client = await self._get_client()
        try:
            response = await client.get("http://localhost:3001/api/status")
            data = response.json()
            return {
                "connected": data.get("connected", False),
                "isReady": data.get("isReady", False),
                "status": data.get("status", "unknown"),
                "hasQrCode": data.get("hasQrCode", False),
                "version": data.get("version", "unknown"),
                "ok": data.get("ok", False)
            }
        except Exception as e:
            return {
                "connected": False,
                "isReady": False,
                "status": "error",
                "error": str(e)
            }

    def get_db_stats(self) -> Dict[str, Any]:
        """Get statistics from MySQL database"""
        try:
            conn = mysql.connector.connect(**self._db_config)
            cursor = conn.cursor(dictionary=True)

            # Mensagens hoje (tabela: conversations)
            cursor.execute("""
                SELECT COUNT(*) as count FROM conversations
                WHERE DATE(created_at) = CURDATE()
            """)
            messages_today = cursor.fetchone()["count"]

            # Leads hoje
            cursor.execute("""
                SELECT COUNT(*) as count FROM leads
                WHERE DATE(created_at) = CURDATE()
            """)
            leads_today = cursor.fetchone()["count"]

            # Leads esta semana
            cursor.execute("""
                SELECT COUNT(*) as count FROM leads
                WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            """)
            leads_week = cursor.fetchone()["count"]

            # Conversas ativas (não fechadas)
            cursor.execute("""
                SELECT COUNT(*) as count FROM leads
                WHERE conversation_state NOT IN ('closed', 'qualified', '')
                AND conversation_state IS NOT NULL
            """)
            active_conversations = cursor.fetchone()["count"]

            # Última mensagem
            cursor.execute("""
                SELECT MAX(created_at) as last_msg FROM conversations
            """)
            last_message = cursor.fetchone()["last_msg"]
            if last_message:
                last_message = last_message.isoformat() if hasattr(last_message, 'isoformat') else str(last_message)

            # Total de leads
            cursor.execute("SELECT COUNT(*) as count FROM leads")
            total_leads = cursor.fetchone()["count"]

            # Total de mensagens
            cursor.execute("SELECT COUNT(*) as count FROM conversations")
            total_messages = cursor.fetchone()["count"]

            # Leads aguardando humano
            cursor.execute("""
                SELECT COUNT(*) as count FROM leads
                WHERE human_takeover = 1 OR conversation_state = 'awaiting_human'
            """)
            awaiting_human = cursor.fetchone()["count"]

            # Leads qualificadas
            cursor.execute("""
                SELECT COUNT(*) as count FROM leads
                WHERE lead_status IN ('qualified', 'hot')
            """)
            qualified_leads = cursor.fetchone()["count"]

            # Mensagens por hora (últimas 24h)
            cursor.execute("""
                SELECT 
                    HOUR(created_at) as hour,
                    COUNT(*) as count
                FROM conversations
                WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
                GROUP BY HOUR(created_at)
                ORDER BY hour
            """)
            hourly_messages = {row["hour"]: row["count"] for row in cursor.fetchall()}

            cursor.close()
            conn.close()

            return {
                "messages_today": messages_today,
                "leads_today": leads_today,
                "leads_week": leads_week,
                "active_conversations": active_conversations,
                "awaiting_human": awaiting_human,
                "qualified_leads": qualified_leads,
                "last_message": last_message,
                "total_leads": total_leads,
                "total_messages": total_messages,
                "hourly_messages": hourly_messages
            }
        except Exception as e:
            return {
                "error": str(e),
                "messages_today": 0,
                "leads_today": 0,
                "leads_week": 0,
                "active_conversations": 0,
                "awaiting_human": 0,
                "qualified_leads": 0,
                "last_message": None,
                "total_leads": 0,
                "total_messages": 0,
                "hourly_messages": {}
            }

    async def collect(self) -> Dict[str, Any]:
        """Collect all WhatsApp metrics"""
        status = await self.get_status()
        stats = self.get_db_stats()
        
        result = {
            **status,
            **stats,
            "collected_at": datetime.now().isoformat()
        }
        
        self._last_results = result
        return result

    def get_last_results(self) -> Dict[str, Any]:
        """Get last collected results"""
        return self._last_results


# Singleton instance
whatsapp_collector = WhatsAppCollector()
