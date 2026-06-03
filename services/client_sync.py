"""
CaseHub - Client Sync Service
Syncs client emails from active-clients.json to CaseHub database
"""
import json
import os
import logging
from typing import Dict, List
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
ACTIVE_CLIENTS_PATH = os.getenv("ACTIVE_CLIENTS_PATH", "/var/www/casehub/whatsapp-bot/client-followup/active-clients.json")


class ClientSyncService:
    def __init__(self, db: Session):
        self.db = db
    
    def _load_active_clients(self) -> List[Dict]:
        try:
            with open(ACTIVE_CLIENTS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("clients", [])
        except Exception as e:
            logger.error(f"Error loading active-clients.json: {e}")
            return []
    
    def _normalize_name(self, name: str) -> str:
        if not name:
            return ""
        return " ".join(name.lower().split())
    
    def sync_client_emails(self) -> Dict:
        result = {"checked": 0, "updated": 0, "errors": [], "updates": []}
        
        active_clients = self._load_active_clients()
        casehub_clients = self.db.execute(text(
            "SELECT id, first_name, last_name, email FROM clients"
        )).fetchall()
        
        casehub_by_name = {}
        for c in casehub_clients:
            fn = c.first_name or ""
            ln = c.last_name or ""
            full_name = self._normalize_name(f"{fn} {ln}")
            if full_name:
                casehub_by_name[full_name] = {"id": c.id, "email": c.email}
        
        for ac in active_clients:
            result["checked"] += 1
            ac_name = self._normalize_name(ac.get("name", ""))
            ac_email = ac.get("email", "")
            
            if not ac_name or not ac_email:
                continue
            
            primary_email = ac_email.split(",")[0].strip().lower()
            
            if ac_name in casehub_by_name:
                ch_client = casehub_by_name[ac_name]
                ch_email = (ch_client["email"] or "").lower().strip()
                
                if ch_email != primary_email:
                    try:
                        self.db.execute(text(
                            "UPDATE clients SET email = :email WHERE id = :id"
                        ), {"email": primary_email, "id": ch_client["id"]})
                        self.db.commit()
                        result["updated"] += 1
                        result["updates"].append({
                            "name": ac.get("name"),
                            "old_email": ch_email,
                            "new_email": primary_email
                        })
                    except Exception as e:
                        result["errors"].append(str(e))
        
        return result
    
    def reprocess_failed_emails(self) -> Dict:
        result = {"found": 0, "relinked": 0, "errors": []}
        
        emails = self.db.execute(text("""
            SELECT id, sender, subject FROM email_messages
            WHERE notion_task_id = 'NO_PARALEGAL'
            AND direction = 'inbound'
        """)).fetchall()
        
        result["found"] = len(emails)
        
        clients = self.db.execute(text("""
            SELECT id, email FROM clients
            WHERE email IS NOT NULL AND email != ''
        """)).fetchall()
        
        client_by_email = {}
        for c in clients:
            if c.email:
                for email in c.email.lower().split(","):
                    client_by_email[email.strip()] = c.id
        
        for em in emails:
            sender = (em.sender or "").lower()
            for client_email, client_id in client_by_email.items():
                if client_email in sender:
                    try:
                        self.db.execute(text("""
                            UPDATE email_messages
                            SET client_id = :cid, notion_task_id = NULL
                            WHERE id = :eid
                        """), {"cid": client_id, "eid": em.id})
                        self.db.commit()
                        result["relinked"] += 1
                    except Exception as e:
                        result["errors"].append(str(e))
                    break
        
        return result


def run_client_sync(db: Session) -> Dict:
    service = ClientSyncService(db)
    return {
        "email_sync": service.sync_client_emails(),
        "reprocess": service.reprocess_failed_emails()
    }
