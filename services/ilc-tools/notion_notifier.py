#!/usr/bin/env python3
"""
Notion Notifier - CaseHub
Creates tasks, communications, and documents in Notion databases.
"""

import os
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Notion Configuration
NOTION_CONFIG = {
    "token": os.environ.get('NOTION_API_KEY', ''),
    "databases": {
        "tarefas": "2c3cd945-9a03-81be-b06c-de8684558cfe",
        "comunicacoes": "2c3cd945-9a03-81bf-b319-c8400c746694",
        "documentos": "2c3cd945-9a03-8108-88fc-c624faf3d9f4",
        "clientes": "2c3cd945-9a03-81ec-a81e-fe6829c791ef",
        "casos": "2c3cd945-9a03-813e-9658-eeb0c0c29a67"
    },
    "team_ids": {
        "Ana Clara": "2c3cd945-9a03-8151-b705-ee44298fafcb",
        "Juliana": "2c3cd945-9a03-81a1-a33d-f40e394afd0e"
    },
    "team_emails": {
        "Ana Clara": "anacleal.2025@gmail.com",
        "Juliana": "juliana.moreschi.2025@gmail.com"
    }
}

# API Headers
def get_headers():
    return {
        "Authorization": f"Bearer {NOTION_CONFIG['token']}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }


class NotionNotifier:
    """Handles all Notion API interactions for email processing."""

    def __init__(self):
        self.base_url = "https://api.notion.com/v1"
        self.headers = get_headers()

    def _make_request(self, method: str, endpoint: str, data: dict = None) -> dict:
        """Make a request to Notion API."""
        url = f"{self.base_url}/{endpoint}"
        try:
            if method == "POST":
                response = requests.post(url, headers=self.headers, json=data)
            elif method == "GET":
                response = requests.get(url, headers=self.headers, params=data)
            elif method == "PATCH":
                response = requests.patch(url, headers=self.headers, json=data)
            else:
                raise ValueError(f"Unsupported method: {method}")

            if response.status_code in [200, 201]:
                return {"success": True, "data": response.json()}
            else:
                logger.error(f"Notion API error: {response.status_code} - {response.text}")
                return {"success": False, "error": response.text, "status_code": response.status_code}
        except Exception as e:
            logger.error(f"Request error: {e}")
            return {"success": False, "error": str(e)}

    def create_task(
        self,
        title: str,
        client_name: str,
        paralegal: str,
        priority: str = "Alta",
        task_type: str = "Comunicação",
        deadline_days: int = 1,
        notes: str = "",
        origem: str = "Email"
    ) -> dict:
        """
        Create a task in the Tarefas database.

        Args:
            title: Task title
            client_name: Client name for reference
            paralegal: Name of paralegal (Ana Clara, Juliana)
            priority: Urgente, Alta, Media, Baixa
            task_type: Coleta de Documentos, Preparacao de Formulario, Revisao, Filing, Follow-up, Comunicação, Outro
            deadline_days: Days until deadline
            notes: Additional notes
        """
        deadline = (datetime.now() + timedelta(days=deadline_days)).strftime("%Y-%m-%d")

        properties = {
            "Tarefa": {
                "title": [{"text": {"content": title}}]
            },
            "Status": {
                "select": {"name": "A Fazer"}
            },
            "Prioridade": {
                "select": {"name": priority}
            },
            "Tipo": {
                "select": {"name": task_type}
            },
            "Deadline": {
                "date": {"start": deadline}
            },
            "Data de Criação": {
                "date": {"start": datetime.now().strftime("%Y-%m-%d")}
            },
            "Origem": {
                "select": {"name": origem}
            }
        }

        if notes:
            properties["Notas"] = {
                "rich_text": [{"text": {"content": notes[:2000]}}]
            }

        data = {
            "parent": {"database_id": NOTION_CONFIG["databases"]["tarefas"]},
            "properties": properties
        }

        result = self._make_request("POST", "pages", data)

        if result["success"]:
            logger.info(f"Task created: {title} for {paralegal}")
            return {"success": True, "task_id": result["data"]["id"]}
        else:
            return result

    def create_communication(
        self,
        subject: str,
        comm_type: str = "Email Recebido",
        direction: str = "Entrada",
        content: str = "",
        status: str = "Pendente",
        email_date: datetime = None,
        notes: str = "",
        linked_to: str = None
    ) -> dict:
        """
        Create a communication record in the Comunicacoes database.

        Args:
            subject: Email subject
            comm_type: Email Enviado, Email Recebido, SMS Enviado, SMS Recebido, WhatsApp, Ligacao, Reuniao, Nota Interna
            direction: Entrada, Saida
            content: Email body preview
            status: Enviado, Entregue, Lido, Respondido, Falhou, Pendente
            email_date: Date/time of communication
            notes: Additional notes
        """
        if email_date is None:
            email_date = datetime.now()

        properties = {
            "Assunto": {
                "title": [{"text": {"content": subject[:100]}}]
            },
            "Tipo": {
                "select": {"name": comm_type}
            },
            "Direção": {
                "select": {"name": direction}
            },
            "Status": {
                "select": {"name": status}
            },
            "Data/Hora": {
                "date": {"start": email_date.isoformat()}
            }
        }

        if content:
            properties["Conteúdo"] = {
                "rich_text": [{"text": {"content": content[:2000]}}]
            }

        if notes:
            properties["Notas"] = {
                "rich_text": [{"text": {"content": notes[:2000]}}]
            }

        if linked_to:
            properties["Linked to"] = {
                "select": {"name": linked_to}
            }

        data = {
            "parent": {"database_id": NOTION_CONFIG["databases"]["comunicacoes"]},
            "properties": properties
        }

        result = self._make_request("POST", "pages", data)

        if result["success"]:
            logger.info(f"Communication created: {subject}" + (f" [Linked to: {linked_to}]" if linked_to else ""))
            return {"success": True, "comm_id": result["data"]["id"]}
        else:
            return result

    def create_document(
        self,
        document_name: str,
        document_type: str = "Outro",
        file_path: str = "",
        file_url: str = "",
        status: str = "Recebido",
        notes: str = ""
    ) -> dict:
        """
        Create a document record in the Documentos database.

        Args:
            document_name: Name of the document
            document_type: Passaporte, I-94, Visa, EAD Card, Green Card, Birth Certificate,
                          Marriage Certificate, Diploma, Transcript, Employment Letter,
                          Tax Return, Pay Stub, Bank Statement, Recommendation Letter,
                          Evidence, USCIS Form, Receipt Notice, Approval Notice, RFE, Outro
            file_path: Local path to file (for reference)
            file_url: External URL to file (if hosted)
            status: Pendente, Recebido, Em Revisao, Aprovado, Rejeitado, Expirado
            notes: Additional notes
        """
        properties = {
            "Nome do Documento": {
                "title": [{"text": {"content": document_name[:100]}}]
            },
            "Tipo": {
                "select": {"name": document_type}
            },
            "Status": {
                "select": {"name": status}
            },
            "Data de Upload": {
                "date": {"start": datetime.now().strftime("%Y-%m-%d")}
            }
        }

        # Add file if URL provided (Notion external file)
        if file_url:
            properties["Arquivo"] = {
                "files": [{
                    "name": document_name,
                    "type": "external",
                    "external": {"url": file_url}
                }]
            }

        notes_text = notes or ""
        if file_path:
            notes_text += f"\nLocal path: {file_path}"

        if notes_text.strip():
            properties["Notas"] = {
                "rich_text": [{"text": {"content": notes_text.strip()[:2000]}}]
            }

        data = {
            "parent": {"database_id": NOTION_CONFIG["databases"]["documentos"]},
            "properties": properties
        }

        result = self._make_request("POST", "pages", data)

        if result["success"]:
            logger.info(f"Document created: {document_name}")
            return {"success": True, "doc_id": result["data"]["id"]}
        else:
            return result

    def process_email_notification(
        self,
        client_name: str,
        client_email: str,
        paralegal: str,
        subject: str,
        body_preview: str,
        email_date: datetime,
        attachments: List[Dict[str, Any]] = None,
        linked_to: str = None,
        original_message_id: str = None
    ) -> dict:
        """
        Process a complete email notification: create communication, task, and documents.

        Args:
            client_name: Client name
            client_email: Client email address
            paralegal: Paralegal responsible (Ana Clara, Sofia, Juliana)
            subject: Email subject
            body_preview: Email body preview
            email_date: When email was received
            attachments: List of attachment info dicts with keys: name, type, path, url
            linked_to: Partner firm name if applicable
            original_message_id: Message-ID of original email for threading
        """
        results = {
            "communication": None,
            "task": None,
            "documents": []
        }

        attachments = attachments or []
        attachment_count = len(attachments)
        attachment_names = [a.get("name", "unknown") for a in attachments]

        # 1. Create Communication record
        comm_notes = f"De: {client_email}"
        if attachment_count > 0:
            comm_notes += f"\nAnexos ({attachment_count}): {', '.join(attachment_names)}"

        comm_result = self.create_communication(
            subject=subject,
            comm_type="Email Recebido",
            direction="Entrada",
            content=body_preview,
            status="Pendente",
            email_date=email_date,
            notes=comm_notes,
            linked_to=linked_to
        )
        results["communication"] = comm_result

        # 2. Create Task for paralegal
        # Determine priority based on content
        priority = "Alta"
        if any(word in subject.lower() for word in ["rfe", "urgent", "urgente", "deadline"]):
            priority = "Urgente"

        task_title = f"Responder email de {client_name}"
        task_notes = f"Email recebido em {email_date.strftime('%d/%m/%Y %H:%M')}\n"
        task_notes += f"Assunto: {subject}\n"
        task_notes += f"De: {client_email}\n"
        if attachment_count > 0:
            task_notes += f"Anexos: {attachment_count} arquivo(s)"

        task_result = self.create_task(
            title=task_title,
            client_name=client_name,
            paralegal=paralegal,
            priority=priority,
            task_type="Comunicação",
            deadline_days=1,
            notes=task_notes
        )
        results["task"] = task_result

        # 2.1 Send email notification to caseworker
        if task_result.get("success"):
            notification_sent = self.send_caseworker_notification(
                paralegal=paralegal,
                client_name=client_name,
                client_email=client_email,
                subject=subject,
                attachment_count=attachment_count,
                task_id=task_result.get("task_id"),
                original_message_id=original_message_id
            )
            results["notification_sent"] = notification_sent

        # 3. Create Document records for each attachment
        for attachment in attachments:
            doc_name = f"{attachment.get('type', 'Documento')} - {client_name}"
            doc_notes = f"Recebido via email em {email_date.strftime('%d/%m/%Y')}\n"
            doc_notes += f"Arquivo original: {attachment.get('name', 'unknown')}"

            doc_result = self.create_document(
                document_name=doc_name,
                document_type=attachment.get("type", "Outro"),
                file_path=attachment.get("path", ""),
                file_url=attachment.get("url", ""),
                status="Recebido",
                notes=doc_notes
            )
            results["documents"].append(doc_result)

        # Log summary
        success_count = sum([
            1 if results["communication"] and results["communication"].get("success") else 0,
            1 if results["task"] and results["task"].get("success") else 0,
            sum(1 for d in results["documents"] if d.get("success"))
        ])
        total_count = 2 + len(attachments)

        logger.info(f"Email notification processed for {client_name}: {success_count}/{total_count} items created")

        return results

    def find_client_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Search for a client in the Clientes database by email.
        """
        data = {
            "filter": {
                "property": "Email",
                "email": {"equals": email.lower()}
            }
        }

        result = self._make_request(
            "POST",
            f"databases/{NOTION_CONFIG['databases']['clientes']}/query",
            data
        )

        if result["success"] and result["data"].get("results"):
            return result["data"]["results"][0]
        return None

    def send_caseworker_notification(
        self,
        paralegal: str,
        client_name: str,
        client_email: str,
        subject: str,
        attachment_count: int,
        task_id: str = None,
        original_message_id: str = None
    ) -> bool:
        """
        Send email notification to caseworker about new client email.
        Uses Gmail SMTP. Threads with original email using In-Reply-To/References.
        """
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        import re

        gmail_email = os.getenv("GMAIL_CENTER_EMAIL", "info@casehub.app")
        gmail_password = os.getenv("GMAIL_CENTER_APP_PASSWORD")

        if not gmail_password:
            logger.warning("GMAIL_CENTER_APP_PASSWORD not configured, skipping email notification")
            return False

        caseworker_email = NOTION_CONFIG["team_emails"].get(paralegal)
        if not caseworker_email:
            logger.warning(f"No email configured for paralegal: {paralegal}")
            return False

        # Build email content
        attachment_text = f"{attachment_count} anexo(s)" if attachment_count > 0 else "sem anexos"

        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px;">
            <h2 style="color: #2563eb;">📋 Tarefa Criada no Notion</h2>
            <p>Uma tarefa foi criada automaticamente para este email.</p>

            <div style="background: #f3f4f6; padding: 16px; border-radius: 8px; margin: 16px 0;">
                <p><strong>Cliente:</strong> {client_name}</p>
                <p><strong>Paralegal:</strong> {paralegal}</p>
                <p><strong>Anexos:</strong> {attachment_text}</p>
            </div>

            <p style="color: #6b7280; font-size: 12px; margin-top: 24px;">
                Immigration Law Center - Notificacao Automatica
            </p>
        </div>
        """

        try:
            msg = MIMEMultipart("alternative")

            # Use Re: subject to thread with original email
            clean_subject = re.sub(r'^(Re:\s*)+', '', subject, flags=re.IGNORECASE).strip()
            msg["Subject"] = f"Re: {clean_subject}"
            msg["From"] = f"CaseHub Sistema <{gmail_email}>"
            msg["To"] = caseworker_email
            msg["Cc"] = gmail_email  # CC to info@ so it appears in inbox

            # Threading headers - this makes it appear in the same thread
            if original_message_id:
                msg["In-Reply-To"] = original_message_id
                msg["References"] = original_message_id

            msg.attach(MIMEText(html_content, "html"))

            # Send to both caseworker and info@ (CC)
            recipients = [caseworker_email, gmail_email]

            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(gmail_email, gmail_password)
                server.sendmail(gmail_email, recipients, msg.as_string())

            logger.info(f"Notification sent to {paralegal} ({caseworker_email}) + CC to {gmail_email}")
            return True

        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return False


# Convenience functions for direct usage
def notify_new_email(
    client_name: str,
    client_email: str,
    paralegal: str,
    subject: str,
    body_preview: str,
    email_date: datetime = None,
    attachments: List[Dict[str, Any]] = None
) -> dict:
    """
    Convenience function to notify about a new email.
    """
    notifier = NotionNotifier()
    return notifier.process_email_notification(
        client_name=client_name,
        client_email=client_email,
        paralegal=paralegal,
        subject=subject,
        body_preview=body_preview,
        email_date=email_date or datetime.now(),
        attachments=attachments
    )


if __name__ == "__main__":
    # Test the notifier
    logging.basicConfig(level=logging.INFO)

    print("Testing Notion Notifier...")

    notifier = NotionNotifier()

    # Test creating a task
    result = notifier.create_task(
        title="[TESTE] Responder email de teste",
        client_name="Teste Client",
        paralegal="Juliana",
        priority="Media",
        task_type="Comunicação",
        deadline_days=1,
        notes="Este e um teste do sistema de notificacoes"
    )

    print(f"Task creation result: {result}")
