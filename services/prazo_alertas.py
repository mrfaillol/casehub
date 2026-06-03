"""
CaseHub — Automated Prazo/Deadline Alerts
Runs daily via cron or APScheduler.
Sends email notifications for prazos vencing in 1, 3, or 7 days.
"""
import logging
from datetime import date, timedelta
from pathlib import Path

from jinja2 import Template
from sqlalchemy import text

from models.base import SessionLocal
from services.notifications import send_email
from config import settings

logger = logging.getLogger(__name__)

ALERT_DAYS = [7, 3, 1, 0]  # Send alerts at these thresholds

TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "emails" / "prazo_alerta.html"


def render_prazo_email(prazo, dias_restantes: int) -> str:
    """Render the prazo alert email template with context."""
    try:
        template_html = TEMPLATE_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.error("Email template not found: %s", TEMPLATE_PATH)
        return ""

    # Resolve org name
    org_name = getattr(prazo, "org_name", None) or "CaseHub"

    template = Template(template_html)
    return template.render(
        org_name=org_name,
        responsavel=prazo.responsavel or "Responsável",
        tipo_prazo=prazo.tipo_prazo or "Prazo processual",
        numero_processo=prazo.numero_processo or "—",
        cliente=prazo.cliente or "—",
        data_vencimento=prazo.data_vencimento.strftime("%d/%m/%Y") if prazo.data_vencimento else "—",
        dias_restantes=dias_restantes,
        base_url=settings.BASE_URL.rstrip("/") if settings.BASE_URL else "",
    )


def check_and_alert_prazos():
    """Check all pending prazos and send alerts for approaching deadlines."""
    db = SessionLocal()
    try:
        today = date.today()

        # Query pending prazos with related case/client info and org name
        result = db.execute(text("""
            SELECT p.id, p.tipo_prazo, p.data_vencimento, p.responsavel,
                   p.status, p.case_id, p.org_id,
                   c.first_name || ' ' || c.last_name AS cliente,
                   cs.case_number AS numero_processo,
                   o.name AS org_name
            FROM prazos_processuais p
            LEFT JOIN cases cs ON p.case_id = cs.id
            LEFT JOIN clients c ON cs.client_id = c.id
            LEFT JOIN organizations o ON p.org_id = o.id
            WHERE p.status IN ('pendente', 'em_andamento')
            AND p.data_vencimento BETWEEN :today AND :max_date
        """), {"today": today, "max_date": today + timedelta(days=max(ALERT_DAYS))})

        prazos = result.fetchall()
        alerts_sent = 0

        for prazo in prazos:
            dias_restantes = (prazo.data_vencimento - today).days

            if dias_restantes in ALERT_DAYS:
                # Get responsible user's email
                user_result = db.execute(text(
                    "SELECT email FROM users WHERE name = :name AND org_id = :org_id LIMIT 1"
                ), {"name": prazo.responsavel, "org_id": prazo.org_id})
                user = user_result.fetchone()

                if user and user.email:
                    try:
                        html_body = render_prazo_email(prazo, dias_restantes)
                        if not html_body:
                            logger.warning("Empty email body for prazo %s — skipping", prazo.id)
                            continue

                        send_email(
                            to_email=user.email,
                            subject=f"⏰ Prazo {'HOJE' if dias_restantes == 0 else f'em {dias_restantes} dias'}: {prazo.tipo_prazo}",
                            html_body=html_body,
                        )
                        alerts_sent += 1
                    except Exception as e:
                        logger.error("Failed to send alert for prazo %s: %s", prazo.id, e)
                else:
                    logger.debug(
                        "No email found for responsavel '%s' (org_id=%s) — prazo %s skipped",
                        prazo.responsavel, prazo.org_id, prazo.id,
                    )

        logger.info("Prazo alerts: checked %d prazos, sent %d alerts", len(prazos), alerts_sent)
        return alerts_sent

    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sent = check_and_alert_prazos()
    print(f"Alerts sent: {sent}")
