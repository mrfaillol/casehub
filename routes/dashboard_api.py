"""
CaseHub Lite - Widget Dashboard API
Returns HTML snippets for individual dashboard widgets.
"""
import html
from datetime import datetime, date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from models import get_db, Case, Task, BillingItem, Client
from auth import get_current_user
from models.tenant import tenant_query
from services.dashboard_metrics import cached_widget_html

router = APIRouter(prefix="/api/widget", tags=["widgets"])


@router.get("/{widget_id}", response_class=HTMLResponse)
async def get_widget_data(widget_id: str, request: Request, db: Session = Depends(get_db)):
    """Return HTML content for a specific widget."""
    user = get_current_user(request, db)
    if not user:
        return HTMLResponse("<div style='color:#999;text-align:center;'>Sessao expirada</div>", status_code=401)

    org_id = request.state.org_id
    today = date.today()

    handlers = {
        "welcome": _widget_welcome,
        "prazo-countdown": _widget_prazos,
        "process-status": _widget_process_status,
        "revenue-chart": _widget_revenue,
        "task-kanban": _widget_tasks,
        "calendar-events": _widget_calendar,
        "activity-feed": _widget_activity,
    }

    handler = handlers.get(widget_id)
    if handler:
        html = cached_widget_html(
            widget_id=widget_id,
            org_id=org_id,
            user_id=user.id,
            renderer=lambda: handler(db, org_id, user, today),
        )
        return HTMLResponse(html)

    return HTMLResponse("", status_code=404)


def _widget_welcome(db, org_id, user, today):
    name = user.name.split(' ')[0] if user.name else 'Doutor'
    try:
        from zoneinfo import ZoneInfo
        hour = datetime.now(ZoneInfo("America/Sao_Paulo")).hour
    except Exception:
        hour = datetime.now().hour
    if hour < 12:
        greeting = "Bom dia"
    elif hour < 18:
        greeting = "Boa tarde"
    else:
        greeting = "Boa noite"
    return f"""<div style="padding:8px">
        <h2 style="font-family:'Instrument Serif',Georgia,serif;font-weight:400;margin:0;">{greeting}, {html.escape(str(name))}</h2>
        <p style="color:#888;margin:4px 0 0;">Painel de controle do escritório</p>
    </div>"""


def _widget_prazos(db, org_id, user, today):
    from models import Reminder
    try:
        start = datetime.combine(today, datetime.min.time())
        end = datetime.combine(today + timedelta(days=7), datetime.max.time())
        upcoming = tenant_query(db, Reminder, org_id).filter(
            Reminder.due_date >= start,
            Reminder.due_date <= end,
            Reminder.is_completed.is_(False),
        ).order_by(Reminder.due_date.asc()).limit(5).all()

        if not upcoming:
            return '<div style="padding:4px;color:#999;text-align:center;">Nenhum prazo nos proximos 7 dias.</div>'

        items = ""
        for r in upcoming:
            due_date = r.due_date.date() if hasattr(r.due_date, "date") else r.due_date
            days_left = (due_date - today).days
            color = "#EF4444" if days_left <= 1 else "#F59E0B" if days_left <= 3 else "#10B981"
            items += f"""<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 4px;border-bottom:1px solid #f3f4f6;">
                <span style="font-size:13px;">{r.title or 'Sem titulo'}</span>
                <span style="font-size:11px;font-weight:600;color:{color};">{days_left}d</span>
            </div>"""
        return items
    except Exception:
        return '<div style="padding:4px;color:#999;text-align:center;">Nenhum prazo cadastrado.</div>'


def _widget_process_status(db, org_id, user, today):
    try:
        total = tenant_query(db, Case, org_id).count()
        active = tenant_query(db, Case, org_id).filter(Case.status.notin_(["approved", "denied", "closed"])).count()
        closed = total - active

        return f"""<div style="padding:4px;">
            <div style="display:flex;justify-content:space-around;text-align:center;">
                <div><div style="font-size:2rem;font-weight:700;color:#0EA5E9;">{total}</div><div style="font-size:11px;color:#888;">Total</div></div>
                <div><div style="font-size:2rem;font-weight:700;color:#10B981;">{active}</div><div style="font-size:11px;color:#888;">Ativos</div></div>
                <div><div style="font-size:2rem;font-weight:700;color:#6B7280;">{closed}</div><div style="font-size:11px;color:#888;">Encerrados</div></div>
            </div>
        </div>"""
    except Exception:
        return '<div style="padding:4px;color:#999;text-align:center;">Nenhum processo cadastrado.</div>'


def _widget_revenue(db, org_id, user, today):
    try:
        first_day = today.replace(day=1)
        total_paid = tenant_query(db, BillingItem, org_id).filter(
            BillingItem.status == "paid",
            BillingItem.paid_date >= first_day,
        ).with_entities(func.sum(BillingItem.amount)).scalar() or 0

        pending = tenant_query(db, BillingItem, org_id).filter(
            BillingItem.status.in_(["pending", "invoiced"]),
        ).with_entities(func.sum(BillingItem.amount)).scalar() or 0

        return f"""<div style="padding:4px;">
            <div style="margin-bottom:12px;">
                <div style="font-size:11px;color:#888;text-transform:uppercase;">Recebido este mes</div>
                <div style="font-size:1.8rem;font-weight:700;color:#10B981;">R$ {float(total_paid):,.2f}</div>
            </div>
            <div>
                <div style="font-size:11px;color:#888;text-transform:uppercase;">Pendente</div>
                <div style="font-size:1.8rem;font-weight:700;color:#F59E0B;">R$ {float(pending):,.2f}</div>
            </div>
        </div>"""
    except Exception:
        return '<div style="padding:4px;color:#999;text-align:center;">Dados financeiros indisponiveis.</div>'


def _widget_tasks(db, org_id, user, today):
    try:
        pending = tenant_query(db, Task, org_id).filter(
            Task.status != "completed",
        ).order_by(Task.due_date.asc().nullslast()).limit(5).all()

        if not pending:
            return '<div style="padding:4px;color:#999;text-align:center;">Nenhuma tarefa pendente.</div>'

        items = ""
        for t in pending:
            due = ""
            if t.due_date:
                days = (t.due_date - today).days
                color = "#EF4444" if days < 0 else "#F59E0B" if days <= 2 else "#888"
                due = f'<span style="font-size:10px;color:{color};">{t.due_date.strftime("%d/%m")}</span>'
            items += f"""<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 4px;border-bottom:1px solid #f3f4f6;">
                <span style="font-size:13px;">{t.title or 'Sem titulo'}</span>
                {due}
            </div>"""
        return items
    except Exception:
        return '<div style="padding:4px;color:#999;text-align:center;">Erro ao carregar tarefas.</div>'


def _widget_calendar(db, org_id, user, today):
    return '<div style="padding:4px;color:#999;text-align:center;">Nenhum evento proximo.</div>'


def _widget_activity(db, org_id, user, today):
    try:
        recent_clients = tenant_query(db, Client, org_id).order_by(Client.created_at.desc()).limit(3).all()
        if not recent_clients:
            return '<div style="padding:4px;color:#999;text-align:center;">Nenhuma atividade recente.</div>'

        items = ""
        for c in recent_clients:
            name = f"{c.first_name} {c.last_name}" if c.first_name else "Cliente"
            dt = c.created_at.strftime("%d/%m %H:%M") if c.created_at else ""
            items += f"""<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 4px;border-bottom:1px solid #f3f4f6;">
                <span style="font-size:13px;">Novo cliente: {name}</span>
                <span style="font-size:10px;color:#888;">{dt}</span>
            </div>"""
        return items
    except Exception:
        return '<div style="padding:4px;color:#999;text-align:center;">Atividade recente indisponivel.</div>'
