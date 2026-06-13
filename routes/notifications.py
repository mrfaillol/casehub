"""
CaseHub - Notifications Routes
"""
from datetime import date, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from models import get_db, User, Task, Case, Client
from models.notification import Notification
from auth import get_current_user
from models.tenant import tenant_query
from services.email_service import email_service
from sqlalchemy import text
from config import settings

router = APIRouter(prefix="/notifications", tags=["notifications"])


def is_email_configured(db: Session) -> bool:
    """Check if any email method is configured (SMTP or IMAP accounts)."""
    # Check SMTP
    if email_service.is_configured():
        return True
    # Check for IMAP accounts
    try:
        result = db.execute(text("SELECT COUNT(*) FROM email_accounts WHERE enabled = TRUE"))
        count = result.scalar()
        return count > 0
    except Exception as e:
        logger.error("Failed to check IMAP accounts: %s", e)
        return False
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py
# PREFIX = "/casehub"  # Imported from template_config.py


def get_context(request: Request, db: Session, **kwargs):
    """Build template context."""
    from i18n import get_translations
    lang = request.cookies.get("lang", "en")
    user = get_current_user(request, db)
    return {
        "request": request,
        "PREFIX": PREFIX,
        "lang": lang,
        "t": get_translations(lang),
        "user": user,
        **kwargs
    }


@router.get("", response_class=HTMLResponse)
async def notification_settings(request: Request, db: Session = Depends(get_db)):
    """Notification settings page."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Get notification preferences (stored in user metadata or separate table)
    prefs = {
        "deadline_reminders": True,
        "task_assignments": True,
        "case_status_changes": True,
        "rfe_alerts": True,
        "weekly_summary": True,
        "reminder_days": [1, 3, 7]  # Days before deadline
    }

    # Puxar notificações anteriores e hotfixes do usuário para o histórico (Onda de melhorias/Central de Notificações)
    notifications = (
        tenant_query(db, Notification, request.state.org_id)
        .filter(Notification.user_id == user.id)
        .order_by(desc(Notification.created_at))
        .limit(30)
        .all()
    )

    hotfixes = (
        tenant_query(db, Notification, request.state.org_id)
        .filter(
            Notification.user_id == user.id,
            Notification.notification_type == "hotfix"
        )
        .order_by(desc(Notification.created_at))
        .limit(20)
        .all()
    )

    return templates.TemplateResponse("app/notifications/settings.html", {
        **get_context(request, db),
        "prefs": prefs,
        "notifications": notifications,
        "hotfixes": hotfixes,
        "email_configured": is_email_configured(db)
    })


@router.post("/save")
async def save_notification_settings(
    request: Request,
    deadline_reminders: bool = Form(False),
    task_assignments: bool = Form(False),
    case_status_changes: bool = Form(False),
    rfe_alerts: bool = Form(False),
    weekly_summary: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Save notification preferences."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # In a real app, save these to the database
    # For now, just redirect back with success message
    return RedirectResponse(
        url=f"{PREFIX}/notifications?saved=true",
        status_code=302
    )


@router.post("/test")
async def send_test_notification(
    request: Request,
    db: Session = Depends(get_db)
):
    """Send a test notification email."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not email_service.is_configured():
        raise HTTPException(status_code=400, detail="Email not configured")

    result = email_service.send_email(
        to_email=user.email,
        subject="🧪 Test Notification from CaseHub",
        html_content=f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h1>Test Notification</h1>
            <p>Hello {user.name or user.email},</p>
            <p>This is a test notification from CaseHub to confirm your email settings are working correctly.</p>
            <p>If you received this email, your notifications are properly configured!</p>
            <hr>
            <p style="color: #666; font-size: 12px;">CaseHub - {settings.ORG_NAME}</p>
        </body>
        </html>
        """
    )

    if result["success"]:
        return {"status": "success", "message": "Test email sent"}
    else:
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to send email"))


@router.get("/check-deadlines")
async def check_deadlines(
    request: Request,
    db: Session = Depends(get_db)
):
    """Check and send deadline reminders (called by cron job)."""
    user = get_current_user(request, db)
    if not user or user.user_type != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    if not email_service.is_configured():
        return {"status": "skipped", "reason": "Email not configured"}

    today = date.today()
    reminder_days = [0, 1, 3, 7]  # Days before deadline to send reminders
    sent_count = 0
    errors = []

    # Admin fallback only depends on org, not on the task — cache it once for
    # the whole call so we don't issue the same query per task without an
    # assignee.
    _admin_fallback = (
        tenant_query(db, User, request.state.org_id)
        .filter(User.user_type == "admin").first()
    )

    for days in reminder_days:
        check_date = today + timedelta(days=days)

        # Find tasks due on check_date
        tasks = tenant_query(db, Task, request.state.org_id).filter(
            Task.status != "completed",
            Task.due_date == check_date
        ).all()

        # Batch the per-task case and assignee lookups that ran inside the
        # loop below (two N+1s). Fetch only the rows actually referenced.
        task_case_ids = {t.case_id for t in tasks if t.case_id}
        tasks_cases_by_id = {
            c.id: c
            for c in tenant_query(db, Case, request.state.org_id)
            .filter(Case.id.in_(task_case_ids)).all()
        } if task_case_ids else {}
        task_user_ids = {t.assigned_to for t in tasks if t.assigned_to}
        tasks_users_by_id = {
            u.id: u
            for u in tenant_query(db, User, request.state.org_id)
            .filter(User.id.in_(task_user_ids)).all()
        } if task_user_ids else {}

        for task in tasks:
            # Get case info
            case = tasks_cases_by_id.get(task.case_id) if task.case_id else None
            case_name = case.case_name or case.case_number if case else "N/A"

            # Get user to notify (task assignee or admin)
            notify_user = tasks_users_by_id.get(task.assigned_to) if task.assigned_to else None
            if not notify_user:
                notify_user = _admin_fallback

            if notify_user and notify_user.email:
                result = email_service.send_deadline_reminder(
                    to_email=notify_user.email,
                    task_title=task.title,
                    due_date=task.due_date,
                    case_name=case_name,
                    days_until=days
                )
                if result["success"]:
                    sent_count += 1
                else:
                    errors.append(f"Task {task.id}: {result.get('error')}")

    return {
        "status": "completed",
        "emails_sent": sent_count,
        "errors": errors if errors else None
    }


@router.get("/upcoming", response_class=HTMLResponse)
async def upcoming_notifications(request: Request, db: Session = Depends(get_db)):
    """View upcoming notifications that would be sent."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    today = date.today()
    week_ahead = today + timedelta(days=7)

    # Tasks due in next 7 days
    upcoming_tasks = tenant_query(db, Task, request.state.org_id).filter(
        Task.status != "completed",
        Task.due_date >= today,
        Task.due_date <= week_ahead
    ).order_by(Task.due_date.asc()).all()

    # Overdue tasks
    overdue_tasks = tenant_query(db, Task, request.state.org_id).filter(
        Task.status != "completed",
        Task.due_date < today
    ).order_by(Task.due_date.desc()).all()

    # RFE cases
    rfe_cases = tenant_query(db, Case, request.state.org_id).filter(Case.status == "rfe").all()

    return templates.TemplateResponse("app/notifications/upcoming.html", {
        **get_context(request, db),
        "upcoming_tasks": upcoming_tasks,
        "overdue_tasks": overdue_tasks,
        "rfe_cases": rfe_cases
    })


@router.get("/hotfix", response_class=HTMLResponse)
async def hotfix_notifications(request: Request, db: Session = Depends(get_db)):
    """Read-only feed of in-app patch notes (notification_type='hotfix').

    Agrupa as notas de atualização que a equipe recebe a cada deploy do alpha,
    em linguagem leiga. Org-scoped (tenant_query) — toda a organização vê os
    mesmos patch notes, independente de para qual usuário a linha foi semeada.
    Não cria nem altera dados; apenas lê o que já existe na tabela notifications.

    Por que NÃO filtrar por user_id: o seeder (scripts/seed_patch_notes.py)
    cria uma cópia da nota para CADA usuário da org. Filtrar por user_id deixava
    a página vazia para qualquer usuário sem cópia própria (ex.: criado depois
    do seed). Patch notes são anúncios da org inteira — todos devem ver. Como há
    uma linha por (usuário × nota), deduplicamos por título para mostrar cada
    novidade uma única vez. Isolamento org_id é mantido via tenant_query.
    """
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Todas as hotfix da ORG (não só do usuário), mais recentes primeiro.
    rows = (
        tenant_query(db, Notification, request.state.org_id)
        .filter(Notification.notification_type == "hotfix")
        .order_by(desc(Notification.created_at))
        .all()
    )

    # Dedup por título: o seeder grava uma linha por usuário, então o mesmo
    # patch note aparece N vezes. Mantemos a primeira ocorrência (a mais
    # recente, pois 'rows' já vem ordenado desc) e preservamos a ordem
    # cronológica do feed.
    hotfixes = []
    seen_titles = set()
    for n in rows:
        key = (n.title or "").strip().lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        hotfixes.append(n)
        if len(hotfixes) >= 100:
            break

    return templates.TemplateResponse("app/notifications/hotfix.html", {
        **get_context(request, db),
        "hotfixes": hotfixes,
    })
