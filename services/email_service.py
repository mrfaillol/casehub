"""
CaseHub - Email Notification Service
"""
import re
import logging
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date, timedelta
from typing import List, Optional
from jinja2 import Template

from config import settings

logger = logging.getLogger(__name__)

# Email configuration from settings
SMTP_HOST = settings.SMTP_HOST
SMTP_PORT = settings.SMTP_PORT
SMTP_USER = settings.SMTP_USER
SMTP_PASSWORD = settings.SMTP_PASS
SMTP_FROM = settings.SMTP_USER or settings.ORG_EMAIL
SMTP_FROM_NAME = settings.SMTP_FROM_NAME or f"{settings.ORG_NAME} CaseHub"


class EmailService:
    """Service for sending email notifications."""

    def __init__(self):
        self.host = SMTP_HOST
        self.port = SMTP_PORT
        self.user = SMTP_USER
        self.password = SMTP_PASSWORD
        self.from_email = SMTP_FROM
        self.from_name = SMTP_FROM_NAME

    def is_configured(self) -> bool:
        """Check if email is properly configured."""
        return bool(self.user and self.password)

    def _validate_email_input(self, to_email: str, subject: str):
        """Validate email inputs to prevent header injection attacks."""
        if '\n' in to_email or '\r' in to_email:
            raise ValueError("Invalid email address")
        if '\n' in subject or '\r' in subject:
            raise ValueError("Invalid subject")
        # Basic email format validation
        email_pattern = re.compile(r'^[^@\s,]+@[^@\s,]+\.[^@\s,]+$')
        for addr in to_email.split(','):
            addr = addr.strip()
            if addr and not email_pattern.match(addr):
                raise ValueError(f"Invalid email format: {addr}")

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        cc_email: Optional[str] = None,
        bcc_email: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None
    ) -> dict:
        """Send an email with optional threading support."""
        if not self.is_configured():
            return {"success": False, "error": "Email not configured"}

        try:
            self._validate_email_input(to_email, subject)
        except ValueError as e:
            logger.warning(f"Email validation failed: {e}")
            return {"success": False, "error": str(e)}

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = to_email
            msg["Reply-To"] = to_email
            if cc_email:
                msg["Cc"] = cc_email

            # Add threading headers if replying to an email
            if in_reply_to:
                msg["In-Reply-To"] = in_reply_to
                if references:
                    msg["References"] = f"{references} {in_reply_to}"
                else:
                    msg["References"] = in_reply_to

            # Add text version
            if text_content:
                part1 = MIMEText(text_content, "plain")
                msg.attach(part1)

            # Add HTML version
            part2 = MIMEText(html_content, "html")
            msg.attach(part2)

            # Build recipient list (envelope recipients for SMTP)
            to_list = [e.strip() for e in to_email.split(",") if e.strip()]
            recipients = to_list
            if cc_email:
                cc_list = [e.strip() for e in cc_email.split(",") if e.strip()]
                recipients.extend(cc_list)
            if bcc_email:
                bcc_addrs = [e.strip() for e in bcc_email.split(",") if e.strip()]
                recipients.extend(bcc_addrs)

            context = ssl.create_default_context()
            with smtplib.SMTP(self.host, self.port) as server:
                server.starttls(context=context)
                server.login(self.user, self.password)
                server.sendmail(self.from_email, recipients, msg.as_string())

            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def send_via_google(
        self,
        org_id: int,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> dict:
        """Send via the org's connected Google (Gmail API) office account.

        Best-effort OAuth send: no SMTP password, sender = the office account
        connected for this org. Returns the GoogleCalendarService status dict
        (e.g. {'success': False, 'error': 'needs_gmail_consent'}). Never raises;
        never logs token material. Used as the primary path when SMTP is not
        configured."""
        if not org_id:
            return {"success": False, "error": "no_org"}
        try:
            self._validate_email_input(to_email, subject)
        except ValueError as e:
            logger.warning(f"Email validation failed: {e}")
            return {"success": False, "error": str(e)}
        try:
            from services.google_calendar import GoogleCalendarService
            gcal = GoogleCalendarService(org_id=org_id)
            return gcal.send_email_as_office(
                to_email=to_email,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
            )
        except Exception as e:  # noqa: BLE001 — best-effort, never crash caller
            logger.warning("Google send routing failed for org %s: %s", org_id, type(e).__name__)
            return {"success": False, "error": "google_send_failed"}

    def _deliver(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        org_id: Optional[int] = None,
    ) -> dict:
        """Deliver a transactional e-mail, preferring SMTP when configured and
        falling back to the org's Google office account (Gmail API/OAuth).

        Routing:
          - SMTP configured  → SMTP (legacy path preserved as fallback).
          - SMTP NOT configured + org_id given → Gmail API as the office account.
          - neither available → {'success': False, 'error': 'no_transport'}.
        """
        if self.is_configured():
            return self.send_email(to_email, subject, html_content, text_content=text_content)
        if org_id:
            return self.send_via_google(org_id, to_email, subject, html_content, text_content=text_content)
        return {"success": False, "error": "no_transport"}

    def send_welcome_credentials(
        self,
        to_email: str,
        user_name: str,
        login_email: str,
        password: str,
        login_url: str,
        org_name: Optional[str] = None,
        org_id: Optional[int] = None,
    ) -> dict:
        """Send welcome email with login credentials to a newly created user.

        Used when an admin/superadmin creates a user. Plain, welcoming
        language for non-technical recipients. The password is delivered
        only through this channel (per Equipe CaseHub's request); it is never logged.
        """
        org = org_name or settings.ORG_NAME
        subject = f"Seu acesso ao CaseHub — {org}"
        first_name = (user_name or "").strip().split(" ")[0] or "Olá"

        html = f"""
        <!DOCTYPE html>
        <html lang="pt-br">
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #1C2447; color: #fff; padding: 24px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ padding: 24px; background: #f8f9fa; }}
                .creds {{ background: #fff; border: 1px solid #e3e6ea; border-radius: 8px; padding: 16px 20px; margin: 18px 0; }}
                .creds p {{ margin: 6px 0; }}
                .label {{ color: #6c757d; font-size: 13px; }}
                .value {{ font-size: 16px; font-weight: bold; color: #1C2447; word-break: break-all; }}
                .btn {{ display: inline-block; padding: 12px 24px; background: #1C2447; color: #fff !important; text-decoration: none; border-radius: 6px; font-weight: bold; }}
                .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #888; }}
                .tip {{ font-size: 13px; color: #6c757d; margin-top: 16px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Bem-vindo(a) ao CaseHub</h1>
                </div>
                <div class="content">
                    <p>{first_name}, sua conta no CaseHub de <strong>{org}</strong> foi criada.</p>
                    <p>Use os dados abaixo para entrar:</p>
                    <div class="creds">
                        <p><span class="label">Endereço de acesso (login):</span><br>
                           <span class="value">{login_email}</span></p>
                        <p><span class="label">Senha:</span><br>
                           <span class="value">{password}</span></p>
                    </div>
                    <p style="text-align:center; margin: 24px 0;">
                        <a href="{login_url}" class="btn">Entrar no CaseHub</a>
                    </p>
                    <p class="tip">Se o botão não funcionar, copie e cole este endereço no navegador:<br>{login_url}</p>
                    <p class="tip">Por segurança, recomendamos trocar sua senha após o primeiro acesso, em Configurações.</p>
                </div>
                <div class="footer">
                    <p>Este e-mail foi enviado automaticamente porque sua conta foi criada no CaseHub.</p>
                    <p>{org}</p>
                </div>
            </div>
        </body>
        </html>
        """

        text = (
            f"{first_name}, sua conta no CaseHub de {org} foi criada.\n\n"
            f"Endereço de acesso (login): {login_email}\n"
            f"Senha: {password}\n\n"
            f"Entre por: {login_url}\n\n"
            f"Por segurança, recomendamos trocar sua senha após o primeiro acesso."
        )

        # Prefer SMTP if ever configured; otherwise send as the org's Google
        # office account (Gmail API/OAuth). The password is delivered only
        # through this channel and is never logged.
        return self._deliver(to_email, subject, html, text_content=text, org_id=org_id)

    def send_password_reset(
        self,
        to_email: str,
        reset_url: str,
        org_name: Optional[str] = None,
        org_id: Optional[int] = None,
        expiry_hours: int = 1,
    ) -> dict:
        """Send a password-reset link to a user who requested one.

        Mirrors send_welcome_credentials: plain, welcoming PT-BR language for
        non-technical recipients, delivered via SMTP when configured and
        otherwise as the org's connected Google office account (Gmail API/OAuth).
        Never raises. The reset_url must be host-derived (the tenant subdomain),
        never settings.BASE_URL, so the link points back to the right host.
        """
        org = org_name or settings.ORG_NAME
        subject = f"Redefinição de senha — CaseHub {org}"

        html = f"""
        <!DOCTYPE html>
        <html lang="pt-br">
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #1C2447; color: #fff; padding: 24px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ padding: 24px; background: #f8f9fa; }}
                .btn {{ display: inline-block; padding: 12px 24px; background: #1C2447; color: #fff !important; text-decoration: none; border-radius: 6px; font-weight: bold; }}
                .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #888; }}
                .tip {{ font-size: 13px; color: #6c757d; margin-top: 16px; word-break: break-all; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Redefinição de senha</h1>
                </div>
                <div class="content">
                    <p>Recebemos um pedido para redefinir a senha da sua conta no CaseHub de <strong>{org}</strong>.</p>
                    <p>Clique no botão abaixo para criar uma nova senha (o link é válido por {expiry_hours} hora):</p>
                    <p style="text-align:center; margin: 24px 0;">
                        <a href="{reset_url}" class="btn">Criar nova senha</a>
                    </p>
                    <p class="tip">Se o botão não funcionar, copie e cole este endereço no navegador:<br>{reset_url}</p>
                    <p class="tip">Se você não pediu essa redefinição, pode ignorar este e-mail com segurança — sua senha continua a mesma.</p>
                </div>
                <div class="footer">
                    <p>Este e-mail foi enviado automaticamente a pedido de redefinição de senha no CaseHub.</p>
                    <p>{org}</p>
                </div>
            </div>
        </body>
        </html>
        """

        text = (
            f"Recebemos um pedido para redefinir a senha da sua conta no CaseHub de {org}.\n\n"
            f"Crie uma nova senha por este link (válido por {expiry_hours} hora):\n"
            f"{reset_url}\n\n"
            f"Se você não pediu essa redefinição, pode ignorar este e-mail — sua senha continua a mesma."
        )

        # Delivered only through this channel; the reset link is never logged.
        return self._deliver(to_email, subject, html, text_content=text, org_id=org_id)

    def send_deadline_reminder(
        self,
        to_email: str,
        task_title: str,
        due_date: date,
        case_name: str,
        days_until: int
    ) -> dict:
        """Send a deadline reminder email."""
        subject = f"⏰ Deadline Reminder: {task_title}"

        if days_until == 0:
            urgency = "TODAY"
            urgency_class = "danger"
        elif days_until == 1:
            urgency = "TOMORROW"
            urgency_class = "warning"
        else:
            urgency = f"in {days_until} days"
            urgency_class = "info"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #0d6efd; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background: #f8f9fa; }}
                .urgency {{ font-size: 24px; font-weight: bold; color: {'#dc3545' if urgency_class == 'danger' else '#ffc107' if urgency_class == 'warning' else '#17a2b8'}; }}
                .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #666; }}
                .btn {{ display: inline-block; padding: 10px 20px; background: #0d6efd; color: white; text-decoration: none; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>⏰ Deadline Reminder</h1>
                </div>
                <div class="content">
                    <p class="urgency">Due {urgency.upper()}</p>
                    <h2>{task_title}</h2>
                    <p><strong>Case:</strong> {case_name}</p>
                    <p><strong>Due Date:</strong> {due_date.strftime('%B %d, %Y')}</p>
                    <p style="margin-top: 20px;">
                        <a href="{settings.BASE_URL}{settings.PREFIX}/tasks" class="btn">View Tasks</a>
                    </p>
                </div>
                <div class="footer">
                    <p>This is an automated notification from {settings.ORG_NAME} CaseHub.</p>
                    <p>{settings.ORG_NAME} | {settings.ORG_DOMAIN}</p>
                </div>
            </div>
        </body>
        </html>
        """

        return self.send_email(to_email, subject, html)

    def send_case_status_change(
        self,
        to_email: str,
        case_name: str,
        old_status: str,
        new_status: str,
        changed_by: str
    ) -> dict:
        """Send notification when case status changes."""
        subject = f"📋 Case Status Update: {case_name}"

        status_colors = {
            "approved": "#198754",
            "denied": "#dc3545",
            "rfe": "#ffc107",
            "filed": "#0d6efd",
            "pending": "#6c757d",
            "intake": "#17a2b8"
        }

        color = status_colors.get(new_status.lower(), "#6c757d")

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #0d6efd; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background: #f8f9fa; }}
                .status-badge {{ display: inline-block; padding: 5px 15px; border-radius: 20px; font-weight: bold; color: white; background: {color}; }}
                .arrow {{ font-size: 24px; margin: 0 10px; }}
                .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #666; }}
                .btn {{ display: inline-block; padding: 10px 20px; background: #0d6efd; color: white; text-decoration: none; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📋 Case Status Update</h1>
                </div>
                <div class="content">
                    <h2>{case_name}</h2>
                    <p style="text-align: center; font-size: 18px;">
                        <span style="text-decoration: line-through; color: #999;">{old_status.upper()}</span>
                        <span class="arrow">→</span>
                        <span class="status-badge">{new_status.upper()}</span>
                    </p>
                    <p><strong>Changed by:</strong> {changed_by}</p>
                    <p><strong>Date:</strong> {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
                    <p style="margin-top: 20px; text-align: center;">
                        <a href="{settings.BASE_URL}{settings.PREFIX}/cases" class="btn">View Case</a>
                    </p>
                </div>
                <div class="footer">
                    <p>This is an automated notification from {settings.ORG_NAME} CaseHub.</p>
                    <p>{settings.ORG_NAME} | {settings.ORG_DOMAIN}</p>
                </div>
            </div>
        </body>
        </html>
        """

        return self.send_email(to_email, subject, html)

    def send_task_assigned(
        self,
        to_email: str,
        task_title: str,
        case_name: str,
        due_date: Optional[date],
        assigned_by: str,
        priority: str
    ) -> dict:
        """Send notification when task is assigned."""
        subject = f"📝 New Task Assigned: {task_title}"

        priority_colors = {
            "urgent": "#dc3545",
            "high": "#ffc107",
            "medium": "#17a2b8",
            "low": "#6c757d"
        }
        color = priority_colors.get(priority.lower(), "#6c757d")

        due_str = due_date.strftime('%B %d, %Y') if due_date else "Not set"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #198754; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background: #f8f9fa; }}
                .priority {{ display: inline-block; padding: 3px 10px; border-radius: 10px; font-size: 12px; font-weight: bold; color: white; background: {color}; }}
                .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #666; }}
                .btn {{ display: inline-block; padding: 10px 20px; background: #198754; color: white; text-decoration: none; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📝 New Task Assigned</h1>
                </div>
                <div class="content">
                    <h2>{task_title} <span class="priority">{priority.upper()}</span></h2>
                    <p><strong>Case:</strong> {case_name}</p>
                    <p><strong>Due Date:</strong> {due_str}</p>
                    <p><strong>Assigned by:</strong> {assigned_by}</p>
                    <p style="margin-top: 20px; text-align: center;">
                        <a href="{settings.BASE_URL}{settings.PREFIX}/tasks" class="btn">View Task</a>
                    </p>
                </div>
                <div class="footer">
                    <p>This is an automated notification from {settings.ORG_NAME} CaseHub.</p>
                    <p>{settings.ORG_NAME} | {settings.ORG_DOMAIN}</p>
                </div>
            </div>
        </body>
        </html>
        """

        return self.send_email(to_email, subject, html)

    def send_rfe_alert(
        self,
        to_email: str,
        case_name: str,
        client_name: str,
        visa_type: str
    ) -> dict:
        """Send alert when case receives RFE."""
        subject = f"⚠️ RFE Received: {case_name}"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #ffc107; color: #000; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background: #f8f9fa; }}
                .alert-box {{ background: #fff3cd; border: 1px solid #ffc107; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #666; }}
                .btn {{ display: inline-block; padding: 10px 20px; background: #ffc107; color: #000; text-decoration: none; border-radius: 5px; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>⚠️ Request for Evidence (RFE)</h1>
                </div>
                <div class="content">
                    <div class="alert-box">
                        <strong>A case has received an RFE and requires immediate attention.</strong>
                    </div>
                    <h2>{case_name}</h2>
                    <p><strong>Client:</strong> {client_name}</p>
                    <p><strong>Visa Type:</strong> {visa_type}</p>
                    <p><strong>Date:</strong> {datetime.now().strftime('%B %d, %Y')}</p>
                    <p style="margin-top: 20px; text-align: center;">
                        <a href="{settings.BASE_URL}{settings.PREFIX}/cases" class="btn">View Case Details</a>
                    </p>
                </div>
                <div class="footer">
                    <p>This is an automated notification from {settings.ORG_NAME} CaseHub.</p>
                    <p>{settings.ORG_NAME} | {settings.ORG_DOMAIN}</p>
                </div>
            </div>
        </body>
        </html>
        """

        return self.send_email(to_email, subject, html)

    def send_weekly_summary(
        self,
        to_email: str,
        user_name: str,
        stats: dict
    ) -> dict:
        """Send weekly summary email."""
        subject = "📊 Your Weekly CaseHub Summary"

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #0d6efd; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background: #f8f9fa; }}
                .stats-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 20px 0; }}
                .stat-box {{ background: white; padding: 15px; border-radius: 5px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
                .stat-number {{ font-size: 32px; font-weight: bold; color: #0d6efd; }}
                .stat-label {{ font-size: 12px; color: #666; }}
                .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #666; }}
                .btn {{ display: inline-block; padding: 10px 20px; background: #0d6efd; color: white; text-decoration: none; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 Weekly Summary</h1>
                    <p>Hello, {user_name}!</p>
                </div>
                <div class="content">
                    <p>Here's your weekly overview for the past 7 days:</p>
                    <div class="stats-grid">
                        <div class="stat-box">
                            <div class="stat-number">{stats.get('new_cases', 0)}</div>
                            <div class="stat-label">New Cases</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-number">{stats.get('completed_tasks', 0)}</div>
                            <div class="stat-label">Tasks Completed</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-number">{stats.get('pending_tasks', 0)}</div>
                            <div class="stat-label">Pending Tasks</div>
                        </div>
                        <div class="stat-box">
                            <div class="stat-number" style="color: #dc3545;">{stats.get('overdue_tasks', 0)}</div>
                            <div class="stat-label">Overdue Tasks</div>
                        </div>
                    </div>
                    <p style="margin-top: 20px; text-align: center;">
                        <a href="{settings.BASE_URL}{settings.PREFIX}/dashboard" class="btn">Go to Dashboard</a>
                    </p>
                </div>
                <div class="footer">
                    <p>This is your weekly summary from {settings.ORG_NAME} CaseHub.</p>
                    <p>{settings.ORG_NAME} | {settings.ORG_DOMAIN}</p>
                </div>
            </div>
        </body>
        </html>
        """

        return self.send_email(to_email, subject, html)


# Singleton instance
email_service = EmailService()
