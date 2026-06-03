"""
CaseHub - Paralegal Assignment Service
Identifies the responsible paralegal for a client based on active-clients.json
"""
import json
import os
from typing import Optional, Tuple, Dict, List
import logging

logger = logging.getLogger(__name__)

# Path to active clients JSON
ACTIVE_CLIENTS_PATH = os.getenv("ACTIVE_CLIENTS_PATH", "/var/www/casehub/whatsapp-bot/client-followup/active-clients.json")


class ParalegalAssignmentService:
    """Identifies the responsible paralegal for a client"""

    def __init__(self):
        self._clients_cache: Optional[List[Dict]] = None
        self._cache_mtime: Optional[float] = None

    def _load_clients(self) -> List[Dict]:
        """Load clients from JSON file with cache invalidation"""
        try:
            current_mtime = os.path.getmtime(ACTIVE_CLIENTS_PATH)

            # Reload if file changed or cache is empty
            if self._clients_cache is None or self._cache_mtime != current_mtime:
                with open(ACTIVE_CLIENTS_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._clients_cache = data.get("clients", [])
                    self._cache_mtime = current_mtime
                    logger.info(f"Loaded {len(self._clients_cache)} clients from active-clients.json")

            return self._clients_cache
        except Exception as e:
            logger.error(f"Error loading active-clients.json: {e}")
            return []

    def _map_paralegal_to_database_key(self, paralegal: Optional[str]) -> Optional[str]:
        """
        Map paralegal/caseworker name to database key.
        - "Daniel" -> "daniel"
        - "Danielle" -> "danielle"
        - Legacy: "Juliana" -> "daniel", "Ana Clara"/"Sofia" -> "danielle"
        """
        if not paralegal:
            return None

        paralegal_lower = paralegal.lower().strip()

        if paralegal_lower == "daniel":
            return "daniel"
        elif paralegal_lower == "danielle":
            return "danielle"
        elif "juliana" in paralegal_lower:
            return "daniel"
        elif "ana" in paralegal_lower or "sofia" in paralegal_lower:
            return "danielle"

        return None

    def get_paralegal_for_email(self, sender_email: str) -> Tuple[Optional[str], Optional[Dict]]:
        """
        Find paralegal responsible for client based on sender email.

        Args:
            sender_email: Email address or full sender string like "Name <email@example.com>"

        Returns:
            Tuple of (database_key, client_info) where:
            - database_key: "juliana", "ana", or None
            - client_info: dict with client details or None
        """
        if not sender_email:
            return (None, None)

        clients = self._load_clients()
        sender_email_lower = sender_email.lower().strip()

        for client in clients:
            client_email_field = (client.get("email") or "").lower().strip()
            
            # Handle multiple emails separated by comma
            client_emails = [e.strip() for e in client_email_field.split(",") if e.strip()]
            
            for client_email in client_emails:
                if client_email and client_email in sender_email_lower:
                    paralegal = client.get("paralegal")
                    db_key = self._map_paralegal_to_database_key(paralegal)
                    return (db_key, client)

        return (None, None)

    def get_paralegal_for_client_name(self, client_name: str) -> Tuple[Optional[str], Optional[Dict]]:
        """
        Find paralegal responsible for client based on client name.

        Args:
            client_name: Client name to search for

        Returns:
            Tuple of (database_key, client_info)
        """
        if not client_name:
            return (None, None)

        clients = self._load_clients()
        client_name_lower = client_name.lower().strip()

        for client in clients:
            name = (client.get("name") or "").lower().strip()
            # Check if names match (partial match both ways)
            if name and (client_name_lower in name or name in client_name_lower):
                paralegal = client.get("paralegal")
                db_key = self._map_paralegal_to_database_key(paralegal)
                return (db_key, client)

        return (None, None)

    def get_paralegal_for_phone(self, phone: str) -> Tuple[Optional[str], Optional[Dict]]:
        """
        Find paralegal responsible for client based on phone number.

        Args:
            phone: Phone number (can include formatting)

        Returns:
            Tuple of (database_key, client_info)
        """
        if not phone:
            return (None, None)

        # Normalize phone: remove all non-digits except +
        import re
        phone_digits = re.sub(r'[^\d]', '', phone)
        if len(phone_digits) < 10:
            return (None, None)

        # Use last 10 digits for comparison
        phone_suffix = phone_digits[-10:]

        clients = self._load_clients()

        for client in clients:
            client_phone = client.get("phone") or ""
            client_phone_digits = re.sub(r'[^\d]', '', client_phone)

            if len(client_phone_digits) >= 10:
                client_suffix = client_phone_digits[-10:]
                if phone_suffix == client_suffix:
                    paralegal = client.get("paralegal")
                    db_key = self._map_paralegal_to_database_key(paralegal)
                    return (db_key, client)

        return (None, None)

    def get_all_clients(self) -> List[Dict]:
        """Get all active clients"""
        return self._load_clients()

    def get_client_by_email(self, email: str) -> Optional[Dict]:
        """Get client info by email"""
        _, client = self.get_paralegal_for_email(email)
        return client

    def get_client_by_name(self, name: str) -> Optional[Dict]:
        """Get client info by name"""
        _, client = self.get_paralegal_for_client_name(name)
        return client


# Singleton instance
_service_instance: Optional[ParalegalAssignmentService] = None


def get_paralegal_service() -> ParalegalAssignmentService:
    """Get singleton instance of ParalegalAssignmentService"""
    global _service_instance
    if _service_instance is None:
        _service_instance = ParalegalAssignmentService()
    return _service_instance
