"""
CaseHub - Reports Routes
Standard and custom reports for law practice (Immigration + Lite)
"""
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, case as sql_case
from typing import Optional
from datetime import datetime, date, timedelta
import logging

logger = logging.getLogger(__name__)
from collections import defaultdict
import csv
import io

from config import settings
from models import get_db, Client, Case, Document, Task, BillingItem, TimeEntry, User
from auth import get_current_user
from models.tenant import tenant_query

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/reports", tags=["reports"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


def get_context(request: Request, db: Session, **kwargs):
    from i18n import get_translations
    lang = request.cookies.get("lang", "pt-BR")
    t = get_translations(lang)
    user = get_current_user(request, db)
    return {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "t": t,
        "lang": lang,
        **kwargs
    }


def _scoped_query(db: Session, model, org_id: int = None):
    if org_id is None:
        return db.query(model)
    return tenant_query(db, model, org_id)


# Available standard reports
STANDARD_REPORTS = [
    {
        "id": "cases_by_status",
        "name": "Cases by Status",
        "name_pt": "Casos por Status",
        "description": "Overview of cases grouped by current status",
        "description_pt": "Visão geral dos casos agrupados por status atual",
        "icon": "fa-chart-pie",
        "category": "cases"
    },
    {
        "id": "cases_by_visa_type",
        "name": "Cases by Visa Type",
        "name_pt": "Casos por Tipo de Visto",
        "description": "Distribution of cases by visa category",
        "description_pt": "Distribuição de casos por categoria de visto",
        "icon": "fa-passport",
        "category": "cases"
    },
    {
        "id": "cases_timeline",
        "name": "Cases Timeline",
        "name_pt": "Timeline de Casos",
        "description": "New cases created over time",
        "description_pt": "Novos casos criados ao longo do tempo",
        "icon": "fa-calendar-alt",
        "category": "cases"
    },
    {
        "id": "client_demographics",
        "name": "Client Demographics",
        "name_pt": "Demografia de Clientes",
        "description": "Client distribution by country of origin",
        "description_pt": "Distribuição de clientes por país de origem",
        "icon": "fa-globe-americas",
        "category": "clients"
    },
    {
        "id": "revenue_summary",
        "name": "Revenue Summary",
        "name_pt": "Resumo de Receita",
        "description": "Billing and payments overview",
        "description_pt": "Visão geral de faturamento e pagamentos",
        "icon": "fa-dollar-sign",
        "category": "billing"
    },
    {
        "id": "time_entries",
        "name": "Time Entries Report",
        "name_pt": "Relatório de Horas",
        "description": "Time tracked by staff members",
        "description_pt": "Horas registradas por funcionários",
        "icon": "fa-clock",
        "category": "billing"
    },
    {
        "id": "tasks_overview",
        "name": "Tasks Overview",
        "name_pt": "Visão Geral de Tarefas",
        "description": "Task completion and pending items",
        "description_pt": "Conclusão de tarefas e itens pendentes",
        "icon": "fa-tasks",
        "category": "productivity"
    },
    {
        "id": "document_status",
        "name": "Document Status",
        "name_pt": "Status de Documentos",
        "description": "Document collection progress",
        "description_pt": "Progresso de coleta de documentos",
        "icon": "fa-file-alt",
        "category": "documents"
    },
    {
        "id": "upcoming_deadlines",
        "name": "Upcoming Deadlines",
        "name_pt": "Próximos Prazos",
        "description": "Cases and tasks with approaching deadlines",
        "description_pt": "Casos e tarefas com prazos próximos",
        "icon": "fa-exclamation-triangle",
        "category": "productivity"
    },
    {
        "id": "staff_productivity",
        "name": "Staff Productivity",
        "name_pt": "Produtividade da Equipe",
        "description": "Work distribution and performance metrics",
        "description_pt": "Distribuição de trabalho e métricas de desempenho",
        "icon": "fa-user-clock",
        "category": "productivity"
    }
]

# Pre-built report templates for Lite (Brazilian law firms)
LITE_REPORTS = [
    {
        "id": "processos_por_status",
        "name": "Cases by Status",
        "name_pt": "Relatório de Processos por Status",
        "description": "Pie chart of case statuses",
        "description_pt": "Gráfico de pizza com a distribuição dos processos por status atual",
        "icon": "fa-chart-pie",
        "category": "processos"
    },
    {
        "id": "produtividade",
        "name": "Productivity Report",
        "name_pt": "Relatório de Produtividade",
        "description": "Tasks completed per user/month",
        "description_pt": "Tarefas concluídas por usuário e por mês",
        "icon": "fa-user-clock",
        "category": "produtividade"
    },
    {
        "id": "financeiro_mensal",
        "name": "Monthly Financial Report",
        "name_pt": "Relatório Financeiro Mensal",
        "description": "Revenue, pending, costs by month",
        "description_pt": "Receita, valores pendentes e custos por mês",
        "icon": "fa-coins",
        "category": "financeiro"
    },
    {
        "id": "prazos",
        "name": "Deadlines Report",
        "name_pt": "Relatório de Prazos",
        "description": "Upcoming deadlines and missed deadline count",
        "description_pt": "Prazos próximos, vencidos e contagem de atrasos",
        "icon": "fa-calendar-exclamation",
        "category": "produtividade"
    },
    {
        "id": "clientes",
        "name": "Clients Report",
        "name_pt": "Relatório de Clientes",
        "description": "New clients per month, active/inactive",
        "description_pt": "Novos clientes por mês, ativos e inativos",
        "icon": "fa-users",
        "category": "clientes"
    },
]

LITE_CATEGORIES = {
    "processos": {"name": "Cases", "name_pt": "Processos"},
    "clientes": {"name": "Clients", "name_pt": "Clientes"},
    "financeiro": {"name": "Financial", "name_pt": "Financeiro"},
    "produtividade": {"name": "Productivity", "name_pt": "Produtividade"},
}


def _is_lite():
    return getattr(settings, "CASEHUB_PRODUCT", "immigration") == "lite"


@router.get("", response_class=HTMLResponse)
async def list_reports(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    if _is_lite():
        # Lite product: use Brazilian law firm report templates
        categories = {k: {**v, "reports": []} for k, v in LITE_CATEGORIES.items()}
        for report in LITE_REPORTS:
            cat = report["category"]
            if cat in categories:
                categories[cat]["reports"].append(report)
    else:
        # Immigration product: original reports
        categories = {
            "cases": {"name": "Cases", "name_pt": "Casos", "reports": []},
            "clients": {"name": "Clients", "name_pt": "Clientes", "reports": []},
            "billing": {"name": "Billing", "name_pt": "Faturamento", "reports": []},
            "documents": {"name": "Documents", "name_pt": "Documentos", "reports": []},
            "productivity": {"name": "Productivity", "name_pt": "Produtividade", "reports": []}
        }
        for report in STANDARD_REPORTS:
            cat = report["category"]
            if cat in categories:
                categories[cat]["reports"].append(report)

    return templates.TemplateResponse("app/reports/list.html", get_context(
        request, db,
        categories=categories
    ))


# ---------------------------------------------------------------------------
# Quick Report API (JSON) — lightweight stats endpoint
# IMPORTANT: Must be registered BEFORE /{report_id} to avoid path conflict
# ---------------------------------------------------------------------------

@router.get("/quick/{report_type}")
async def quick_report(
    report_type: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Return JSON with basic stats for a given report type.
    Useful for dashboard widgets and AJAX calls."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Não autorizado"})

    org_id = getattr(request.state, "org_id", None)
    today = date.today()
    start = today - timedelta(days=90)  # Last 3 months by default

    try:
        if report_type == "processos_por_status":
            query = tenant_query(db, Case, org_id).with_entities(
                Case.status, func.count(Case.id)
            ).group_by(Case.status).all()
            return JSONResponse(content={
                "report": "processos_por_status",
                "data": {s or "outro": c for s, c in query},
                "total": sum(c for _, c in query)
            })

        elif report_type == "produtividade":
            completed = _scoped_query(db, Task, org_id).with_entities(
                func.count(Task.id)
            ).filter(
                Task.completed_at >= start, Task.status == "completed"
            ).scalar() or 0
            pending = _scoped_query(db, Task, org_id).with_entities(
                func.count(Task.id)
            ).filter(
                Task.status != "completed", Task.created_at >= start
            ).scalar() or 0
            return JSONResponse(content={
                "report": "produtividade",
                "concluidas": completed,
                "pendentes": pending,
                "taxa_conclusao": round((completed / (completed + pending) * 100), 1) if (completed + pending) > 0 else 0
            })

        elif report_type == "financeiro_mensal":
            billed = float(_scoped_query(db, BillingItem, org_id).with_entities(
                func.sum(BillingItem.amount)
            ).filter(
                BillingItem.created_at >= start
            ).scalar() or 0)
            paid = float(_scoped_query(db, BillingItem, org_id).with_entities(
                func.sum(BillingItem.amount)
            ).filter(
                BillingItem.created_at >= start, BillingItem.status == "paid"
            ).scalar() or 0)
            return JSONResponse(content={
                "report": "financeiro_mensal",
                "faturado": billed,
                "pago": paid,
                "pendente": round(billed - paid, 2)
            })

        elif report_type == "prazos":
            next_7 = today + timedelta(days=7)
            urgent_cases = tenant_query(db, Case, org_id).filter(
                Case.expiration_date.isnot(None),
                Case.expiration_date >= today,
                Case.expiration_date <= next_7,
                Case.status.notin_(["approved", "denied", "closed", "archived"])
            ).count()
            urgent_tasks = tenant_query(db, Task, org_id).filter(
                Task.due_date.isnot(None),
                Task.due_date >= today,
                Task.due_date <= next_7,
                Task.status != "completed"
            ).count()
            missed = tenant_query(db, Case, org_id).filter(
                Case.expiration_date.isnot(None),
                Case.expiration_date < today,
                Case.expiration_date >= start,
                Case.status.notin_(["approved", "denied", "closed", "archived"])
            ).count()
            return JSONResponse(content={
                "report": "prazos",
                "urgentes_7dias": urgent_cases + urgent_tasks,
                "vencidos": missed,
            })

        elif report_type == "clientes":
            total = _scoped_query(db, Client, org_id).with_entities(
                func.count(Client.id)
            ).scalar() or 0
            new_this_month = _scoped_query(db, Client, org_id).with_entities(
                func.count(Client.id)
            ).filter(
                Client.created_at >= today.replace(day=1)
            ).scalar() or 0
            active = _scoped_query(db, Case, org_id).with_entities(
                func.count(func.distinct(Case.client_id))
            ).filter(
                Case.status.notin_(["closed", "denied", "archived"])
            ).scalar() or 0
            return JSONResponse(content={
                "report": "clientes",
                "total": total,
                "novos_mes": new_this_month,
                "ativos": active,
                "inativos": total - active
            })

        else:
            return JSONResponse(status_code=404, content={"error": f"Tipo de relatório desconhecido: {report_type}"})

    except Exception as e:
        logger.error("Error in quick_report(%s): %s", report_type, e)
        return JSONResponse(status_code=500, content={"error": "Erro ao gerar relatório"})


@router.get("/{report_id}", response_class=HTMLResponse)
async def view_report(
    request: Request,
    report_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Find report definition (search both lists)
    all_reports = LITE_REPORTS + STANDARD_REPORTS if _is_lite() else STANDARD_REPORTS + LITE_REPORTS
    report_def = next((r for r in all_reports if r["id"] == report_id), None)
    if not report_def:
        return RedirectResponse(url=f"{PREFIX}/reports", status_code=302)

    # Parse dates
    try:
        if start_date:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
        else:
            start = date.today() - timedelta(days=365)
        if end_date:
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
        else:
            end = date.today()
    except Exception as e:
        logger.error("Failed to parse report date range: %s", e)
        start = date.today() - timedelta(days=365)
        end = date.today()

    # Generate report data based on type
    report_data = generate_report(db, report_id, start, end, org_id=request.state.org_id)

    return templates.TemplateResponse("app/reports/view.html", get_context(
        request, db,
        report=report_def,
        data=report_data,
        start_date=start,
        end_date=end
    ))


@router.get("/{report_id}/export")
async def export_report(
    request: Request,
    report_id: str,
    format: str = "csv",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Parse dates
    try:
        if start_date:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
        else:
            start = date.today() - timedelta(days=365)
        if end_date:
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
        else:
            end = date.today()
    except Exception as e:
        logger.error("Failed to parse report date range: %s", e)
        start = date.today() - timedelta(days=365)
        end = date.today()

    # Generate report data
    report_data = generate_report(db, report_id, start, end, org_id=request.state.org_id)

    # Export to CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Write headers and data based on report type
    if "rows" in report_data:
        if report_data["rows"]:
            writer.writerow(report_data.get("headers", []))
            for row in report_data["rows"]:
                writer.writerow(row)
    elif "items" in report_data:
        if report_data["items"]:
            headers = list(report_data["items"][0].keys())
            writer.writerow(headers)
            for item in report_data["items"]:
                writer.writerow([item.get(h, "") for h in headers])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={report_id}_{start}_{end}.csv"}
    )


def generate_report(db: Session, report_id: str, start: date, end: date, org_id: int = None) -> dict:
    """Generate report data based on report type"""

    if report_id == "cases_by_status":
        return generate_cases_by_status(db, start, end, org_id)
    elif report_id == "cases_by_visa_type":
        return generate_cases_by_visa_type(db, start, end, org_id)
    elif report_id == "cases_timeline":
        return generate_cases_timeline(db, start, end, org_id)
    elif report_id == "client_demographics":
        return generate_client_demographics(db, start, end, org_id)
    elif report_id == "revenue_summary":
        return generate_revenue_summary(db, start, end, org_id)
    elif report_id == "time_entries":
        return generate_time_entries_report(db, start, end, org_id)
    elif report_id == "tasks_overview":
        return generate_tasks_overview(db, start, end, org_id)
    elif report_id == "document_status":
        return generate_document_status(db, start, end, org_id)
    elif report_id == "upcoming_deadlines":
        return generate_upcoming_deadlines(db, start, end, org_id)
    elif report_id == "staff_productivity":
        return generate_staff_productivity(db, start, end, org_id)
    # Lite reports
    elif report_id == "processos_por_status":
        return generate_processos_por_status(db, start, end, org_id)
    elif report_id == "produtividade":
        return generate_produtividade(db, start, end, org_id)
    elif report_id == "financeiro_mensal":
        return generate_financeiro_mensal(db, start, end, org_id)
    elif report_id == "prazos":
        return generate_prazos(db, start, end, org_id)
    elif report_id == "clientes":
        return generate_clientes(db, start, end, org_id)

    return {"error": "Unknown report type"}


def generate_cases_by_status(db: Session, start: date, end: date, org_id: int = None) -> dict:
    """Cases grouped by status"""
    query = db.query(
        Case.status,
        func.count(Case.id).label("count")
    ).filter(
        Case.created_at >= start,
        Case.created_at <= end
    ).group_by(Case.status).all()

    status_labels = {
        "intake": "Intake",
        "document_collection": "Document Collection",
        "drafting": "Drafting",
        "review": "Review",
        "filed": "Filed",
        "rfe": "RFE",
        "approved": "Approved",
        "denied": "Denied",
        "closed": "Closed"
    }

    chart_data = {
        "labels": [],
        "values": [],
        "colors": []
    }
    status_colors = {
        "intake": "#6c757d",
        "document_collection": "#17a2b8",
        "drafting": "#ffc107",
        "review": "#fd7e14",
        "filed": "#007bff",
        "rfe": "#dc3545",
        "approved": "#28a745",
        "denied": "#343a40",
        "closed": "#adb5bd"
    }

    total = 0
    items = []
    for status, count in query:
        label = status_labels.get(status, status or "Unknown")
        items.append({"status": label, "count": count})
        chart_data["labels"].append(label)
        chart_data["values"].append(count)
        chart_data["colors"].append(status_colors.get(status, "#6c757d"))
        total += count

    return {
        "type": "pie_chart",
        "chart_data": chart_data,
        "items": items,
        "total": total,
        "headers": ["Status", "Count"],
        "rows": [[i["status"], i["count"]] for i in items]
    }


def generate_cases_by_visa_type(db: Session, start: date, end: date, org_id: int = None) -> dict:
    """Cases grouped by visa type"""
    query = db.query(
        Case.visa_type,
        func.count(Case.id).label("count")
    ).filter(
        Case.created_at >= start,
        Case.created_at <= end,
        Case.visa_type.isnot(None),
        Case.visa_type != ""
    ).group_by(Case.visa_type).order_by(func.count(Case.id).desc()).all()

    chart_data = {
        "labels": [],
        "values": []
    }

    items = []
    total = 0
    for visa_type, count in query:
        items.append({"visa_type": visa_type, "count": count})
        chart_data["labels"].append(visa_type)
        chart_data["values"].append(count)
        total += count

    return {
        "type": "bar_chart",
        "chart_data": chart_data,
        "items": items,
        "total": total,
        "headers": ["Visa Type", "Count"],
        "rows": [[i["visa_type"], i["count"]] for i in items]
    }


def generate_cases_timeline(db: Session, start: date, end: date, org_id: int = None) -> dict:
    """Cases created over time"""
    query = db.query(
        func.date_trunc('month', Case.created_at).label("month"),
        func.count(Case.id).label("count")
    ).filter(
        Case.created_at >= start,
        Case.created_at <= end
    ).group_by(func.date_trunc('month', Case.created_at)).order_by("month").all()

    chart_data = {
        "labels": [],
        "values": []
    }

    items = []
    total = 0
    for month, count in query:
        month_str = month.strftime("%Y-%m") if month else "Unknown"
        items.append({"month": month_str, "count": count})
        chart_data["labels"].append(month_str)
        chart_data["values"].append(count)
        total += count

    return {
        "type": "line_chart",
        "chart_data": chart_data,
        "items": items,
        "total": total,
        "headers": ["Month", "New Cases"],
        "rows": [[i["month"], i["count"]] for i in items]
    }


def generate_client_demographics(db: Session, start: date, end: date, org_id: int = None) -> dict:
    """Client distribution by country of origin"""
    query = db.query(
        Client.country_of_origin,
        func.count(Client.id).label("count")
    ).filter(
        Client.created_at >= start,
        Client.created_at <= end,
        Client.country_of_origin.isnot(None),
        Client.country_of_origin != ""
    ).group_by(Client.country_of_origin).order_by(func.count(Client.id).desc()).limit(15).all()

    chart_data = {
        "labels": [],
        "values": []
    }

    items = []
    total = 0
    for country, count in query:
        items.append({"country": country, "count": count})
        chart_data["labels"].append(country)
        chart_data["values"].append(count)
        total += count

    return {
        "type": "horizontal_bar",
        "chart_data": chart_data,
        "items": items,
        "total": total,
        "headers": ["Country", "Clients"],
        "rows": [[i["country"], i["count"]] for i in items]
    }


def generate_revenue_summary(db: Session, start: date, end: date, org_id: int = None) -> dict:
    """Billing and payments overview"""
    billing_query = _scoped_query(db, BillingItem, org_id).filter(
        BillingItem.created_at >= start,
        BillingItem.created_at <= end
    )

    # Total billed
    billed = billing_query.with_entities(func.sum(BillingItem.amount)).scalar() or 0

    # Total paid
    paid = billing_query.with_entities(func.sum(BillingItem.amount)).filter(
        BillingItem.status == "paid"
    ).scalar() or 0

    # Pending
    pending = billing_query.with_entities(func.sum(BillingItem.amount)).filter(
        BillingItem.status.in_(["pending", "invoiced"])
    ).scalar() or 0

    # Monthly breakdown
    monthly = billing_query.with_entities(
        func.date_trunc('month', BillingItem.created_at).label("month"),
        func.sum(BillingItem.amount).label("total"),
        func.sum(sql_case(
            (BillingItem.status == "paid", BillingItem.amount),
            else_=0
        )).label("paid")
    ).group_by(func.date_trunc('month', BillingItem.created_at)).order_by("month").all()

    chart_data = {
        "labels": [],
        "billed": [],
        "paid": []
    }

    items = []
    for month, total, month_paid in monthly:
        month_str = month.strftime("%Y-%m") if month else "Unknown"
        items.append({
            "month": month_str,
            "billed": float(total or 0),
            "paid": float(month_paid or 0)
        })
        chart_data["labels"].append(month_str)
        chart_data["billed"].append(float(total or 0))
        chart_data["paid"].append(float(month_paid or 0))

    return {
        "type": "revenue",
        "chart_data": chart_data,
        "summary": {
            "total_billed": float(billed),
            "total_paid": float(paid),
            "total_pending": float(pending)
        },
        "items": items,
        "headers": ["Month", "Billed", "Paid"],
        "rows": [[i["month"], f"{i['billed']:.2f}", f"{i['paid']:.2f}"] for i in items]
    }


def generate_time_entries_report(db: Session, start: date, end: date, org_id: int = None) -> dict:
    """Time tracked by staff"""
    query = _scoped_query(db, TimeEntry, org_id).with_entities(
        User.name,
        func.sum(TimeEntry.hours).label("total_hours"),
        func.sum(TimeEntry.hours * TimeEntry.rate).label("total_value")
    ).join(User, TimeEntry.user_id == User.id).filter(
        TimeEntry.date >= start,
        TimeEntry.date <= end
    ).group_by(User.name).order_by(func.sum(TimeEntry.hours).desc()).all()

    chart_data = {
        "labels": [],
        "values": []
    }

    items = []
    total_hours = 0
    total_value = 0
    for name, hours, value in query:
        items.append({
            "staff": name,
            "hours": float(hours or 0),
            "value": float(value or 0)
        })
        chart_data["labels"].append(name)
        chart_data["values"].append(float(hours or 0))
        total_hours += float(hours or 0)
        total_value += float(value or 0)

    return {
        "type": "bar_chart",
        "chart_data": chart_data,
        "items": items,
        "summary": {
            "total_hours": total_hours,
            "total_value": total_value
        },
        "headers": ["Staff", "Hours", "Value"],
        "rows": [[i["staff"], f"{i['hours']:.1f}h", f"{i['value']:.2f}"] for i in items]
    }


def generate_tasks_overview(db: Session, start: date, end: date, org_id: int = None) -> dict:
    """Task completion overview"""
    # By status
    status_query = db.query(
        Task.status,
        func.count(Task.id).label("count")
    ).filter(
        Task.created_at >= start,
        Task.created_at <= end
    ).group_by(Task.status).all()

    status_data = {status: count for status, count in status_query}

    # Completed vs pending
    completed = status_data.get("completed", 0)
    pending = sum(c for s, c in status_data.items() if s != "completed")
    total = completed + pending

    # By priority
    priority_query = db.query(
        Task.priority,
        func.count(Task.id).label("count")
    ).filter(
        Task.created_at >= start,
        Task.created_at <= end,
        Task.status != "completed"
    ).group_by(Task.priority).all()

    chart_data = {
        "labels": ["Completed", "Pending"],
        "values": [completed, pending],
        "colors": ["#28a745", "#ffc107"]
    }

    items = [{"status": s, "count": c} for s, c in status_query]

    return {
        "type": "pie_chart",
        "chart_data": chart_data,
        "items": items,
        "summary": {
            "completed": completed,
            "pending": pending,
            "total": total,
            "completion_rate": (completed / total * 100) if total > 0 else 0
        },
        "priority_breakdown": {p: c for p, c in priority_query},
        "headers": ["Status", "Count"],
        "rows": [[i["status"], i["count"]] for i in items]
    }


def generate_document_status(db: Session, start: date, end: date, org_id: int = None) -> dict:
    """Document collection status"""
    query = db.query(
        Document.status,
        func.count(Document.id).label("count")
    ).filter(
        Document.created_at >= start,
        Document.created_at <= end
    ).group_by(Document.status).all()

    status_labels = {
        "pending": "Pending",
        "received": "Received",
        "reviewed": "Reviewed",
        "approved": "Approved",
        "rejected": "Rejected",
        "expired": "Expired"
    }

    chart_data = {
        "labels": [],
        "values": [],
        "colors": []
    }
    status_colors = {
        "pending": "#ffc107",
        "received": "#17a2b8",
        "reviewed": "#007bff",
        "approved": "#28a745",
        "rejected": "#dc3545",
        "expired": "#6c757d"
    }

    items = []
    total = 0
    for status, count in query:
        label = status_labels.get(status, status or "Unknown")
        items.append({"status": label, "count": count})
        chart_data["labels"].append(label)
        chart_data["values"].append(count)
        chart_data["colors"].append(status_colors.get(status, "#6c757d"))
        total += count

    return {
        "type": "pie_chart",
        "chart_data": chart_data,
        "items": items,
        "total": total,
        "headers": ["Status", "Count"],
        "rows": [[i["status"], i["count"]] for i in items]
    }


def generate_upcoming_deadlines(db: Session, start: date, end: date, org_id: int = None) -> dict:
    """Cases and tasks with approaching deadlines"""
    today = date.today()
    next_30_days = today + timedelta(days=30)

    # Case deadlines
    cases = tenant_query(db, Case, org_id).filter(
        Case.expiration_date.isnot(None),
        Case.expiration_date >= today,
        Case.expiration_date <= next_30_days,
        Case.status.notin_(["approved", "denied", "closed"])
    ).order_by(Case.expiration_date).limit(20).all()

    # Task deadlines
    tasks = tenant_query(db, Task, org_id).filter(
        Task.due_date.isnot(None),
        Task.due_date >= today,
        Task.due_date <= next_30_days,
        Task.status != "completed"
    ).order_by(Task.due_date).limit(20).all()

    case_items = [{
        "type": "Case",
        "name": c.case_name or c.case_number,
        "deadline": c.expiration_date.strftime("%Y-%m-%d") if c.expiration_date else "",
        "days_left": (c.expiration_date - today).days if c.expiration_date else 0,
        "id": c.id
    } for c in cases]

    task_items = [{
        "type": "Task",
        "name": t.title,
        "deadline": t.due_date.strftime("%Y-%m-%d") if t.due_date else "",
        "days_left": (t.due_date - today).days if t.due_date else 0,
        "id": t.id
    } for t in tasks]

    all_items = sorted(case_items + task_items, key=lambda x: x["days_left"])

    # Group by urgency
    urgent = [i for i in all_items if i["days_left"] <= 7]
    warning = [i for i in all_items if 7 < i["days_left"] <= 14]
    upcoming = [i for i in all_items if i["days_left"] > 14]

    return {
        "type": "list",
        "items": all_items,
        "summary": {
            "urgent": len(urgent),
            "warning": len(warning),
            "upcoming": len(upcoming),
            "total": len(all_items)
        },
        "grouped": {
            "urgent": urgent,
            "warning": warning,
            "upcoming": upcoming
        },
        "headers": ["Type", "Name", "Deadline", "Days Left"],
        "rows": [[i["type"], i["name"], i["deadline"], i["days_left"]] for i in all_items]
    }


def generate_staff_productivity(db: Session, start: date, end: date, org_id: int = None) -> dict:
    """Staff productivity metrics"""
    try:
        # Tasks completed per user
        tasks_query = db.query(
            User.name,
            func.count(Task.id).label("tasks")
        ).outerjoin(Task, Task.assigned_to == User.id).filter(
            Task.completed_at >= start,
            Task.completed_at <= end,
            Task.status == "completed"
        ).group_by(User.name).all()

        # Time logged per user
        time_query = db.query(
            User.name,
            func.sum(TimeEntry.hours).label("hours")
        ).join(User, TimeEntry.user_id == User.id).filter(
            TimeEntry.date >= start,
            TimeEntry.date <= end
        ).group_by(User.name).all()

        # All tasks assigned per user (total workload)
        assigned_query = db.query(
            User.name,
            func.count(Task.id).label("assigned")
        ).outerjoin(Task, Task.assigned_to == User.id).filter(
            Task.created_at >= start,
            Task.created_at <= end
        ).group_by(User.name).all()

        # Combine data
        staff_data = defaultdict(lambda: {"assigned": 0, "tasks": 0, "hours": 0})

        for name, assigned in assigned_query:
            if name:
                staff_data[name]["assigned"] = assigned

        for name, tasks in tasks_query:
            if name:
                staff_data[name]["tasks"] = tasks

        for name, hours in time_query:
            if name:
                staff_data[name]["hours"] = float(hours or 0)

        items = [
            {"name": name, **data}
            for name, data in staff_data.items()
        ]
        items.sort(key=lambda x: x["tasks"], reverse=True)

        chart_data = {
            "labels": [i["name"] for i in items[:10]],
            "assigned": [i["assigned"] for i in items[:10]],
            "tasks": [i["tasks"] for i in items[:10]]
        }

        return {
            "type": "grouped_bar",
            "chart_data": chart_data,
            "items": items,
            "headers": ["Staff", "Tasks Assigned", "Tasks Completed", "Hours Logged"],
            "rows": [[i["name"], i["assigned"], i["tasks"], f"{i['hours']:.1f}h"] for i in items]
        }
    except Exception as e:
        return {
            "type": "error",
            "error": str(e),
            "items": [],
            "headers": ["Staff", "Tasks Assigned", "Tasks Completed", "Hours Logged"],
            "rows": []
        }


# ---------------------------------------------------------------------------
# Lite Report Generators (Brazilian law firms)
# ---------------------------------------------------------------------------

def generate_processos_por_status(db: Session, start: date, end: date, org_id: int = None) -> dict:
    """Processos agrupados por status (Lite)"""
    query = tenant_query(db, Case, org_id).with_entities(
        Case.status,
        func.count(Case.id).label("count")
    ).filter(
        Case.created_at >= start,
        Case.created_at <= end
    ).group_by(Case.status).all()

    status_labels_pt = {
        "intake": "Triagem",
        "document_collection": "Coleta de Documentos",
        "drafting": "Elaboração",
        "review": "Revisão",
        "filed": "Protocolado",
        "rfe": "Diligência",
        "approved": "Deferido",
        "denied": "Indeferido",
        "closed": "Encerrado",
        "active": "Ativo",
        "suspended": "Suspenso",
        "archived": "Arquivado",
    }

    status_colors = {
        "intake": "#6c757d", "document_collection": "#17a2b8",
        "drafting": "#ffc107", "review": "#fd7e14", "filed": "#007bff",
        "rfe": "#dc3545", "approved": "#28a745", "denied": "#343a40",
        "closed": "#adb5bd", "active": "#007bff", "suspended": "#fd7e14",
        "archived": "#6c757d",
    }

    chart_data = {"labels": [], "values": [], "colors": []}
    total = 0
    items = []
    for status, count in query:
        label = status_labels_pt.get(status, status or "Outro")
        items.append({"status": label, "count": count})
        chart_data["labels"].append(label)
        chart_data["values"].append(count)
        chart_data["colors"].append(status_colors.get(status, "#6c757d"))
        total += count

    return {
        "type": "pie_chart",
        "chart_data": chart_data,
        "items": items,
        "total": total,
        "headers": ["Status", "Quantidade"],
        "rows": [[i["status"], i["count"]] for i in items]
    }


def generate_produtividade(db: Session, start: date, end: date, org_id: int = None) -> dict:
    """Tarefas concluídas por usuário (Lite)"""
    try:
        tasks_query = db.query(
            User.name,
            func.count(Task.id).label("tasks")
        ).outerjoin(Task, Task.assigned_to == User.id).filter(
            Task.completed_at >= start,
            Task.completed_at <= end,
            Task.status == "completed"
        ).group_by(User.name).order_by(func.count(Task.id).desc()).all()

        total_tasks = db.query(func.count(Task.id)).filter(
            Task.created_at >= start, Task.created_at <= end
        ).scalar() or 0

        completed_total = db.query(func.count(Task.id)).filter(
            Task.completed_at >= start, Task.completed_at <= end,
            Task.status == "completed"
        ).scalar() or 0

        pending_total = total_tasks - completed_total

        chart_data = {"labels": [], "values": []}
        items = []
        for name, tasks in tasks_query:
            if name:
                items.append({"usuario": name, "concluidas": tasks})
                chart_data["labels"].append(name)
                chart_data["values"].append(tasks)

        return {
            "type": "bar_chart",
            "chart_data": chart_data,
            "items": items,
            "summary": {
                "completed": completed_total,
                "pending": pending_total,
                "total": total_tasks,
                "completion_rate": (completed_total / total_tasks * 100) if total_tasks > 0 else 0
            },
            "headers": ["Usuário", "Tarefas Concluídas"],
            "rows": [[i["usuario"], i["concluidas"]] for i in items]
        }
    except Exception as e:
        logger.error("Error generating produtividade report: %s", e)
        return {"type": "bar_chart", "chart_data": {"labels": [], "values": []},
                "items": [], "headers": ["Usuário", "Tarefas Concluídas"], "rows": []}


def generate_financeiro_mensal(db: Session, start: date, end: date, org_id: int = None) -> dict:
    """Relatório financeiro mensal (Lite)"""
    billing_query = _scoped_query(db, BillingItem, org_id).filter(
        BillingItem.created_at >= start, BillingItem.created_at <= end
    )

    billed = billing_query.with_entities(func.sum(BillingItem.amount)).scalar() or 0

    paid = billing_query.with_entities(func.sum(BillingItem.amount)).filter(
        BillingItem.status == "paid"
    ).scalar() or 0

    pending = billing_query.with_entities(func.sum(BillingItem.amount)).filter(
        BillingItem.status.in_(["pending", "invoiced"])
    ).scalar() or 0

    monthly = billing_query.with_entities(
        func.date_trunc('month', BillingItem.created_at).label("month"),
        func.sum(BillingItem.amount).label("total"),
        func.sum(sql_case(
            (BillingItem.status == "paid", BillingItem.amount), else_=0
        )).label("paid")
    ).group_by(func.date_trunc('month', BillingItem.created_at)).order_by("month").all()

    chart_data = {"labels": [], "billed": [], "paid": []}
    items = []
    for month, total, month_paid in monthly:
        month_str = month.strftime("%m/%Y") if month else "—"
        items.append({"mes": month_str, "faturado": float(total or 0), "pago": float(month_paid or 0)})
        chart_data["labels"].append(month_str)
        chart_data["billed"].append(float(total or 0))
        chart_data["paid"].append(float(month_paid or 0))

    return {
        "type": "revenue",
        "chart_data": chart_data,
        "summary": {
            "total_billed": float(billed),
            "total_paid": float(paid),
            "total_pending": float(pending)
        },
        "items": items,
        "headers": ["Mês", "Faturado", "Pago"],
        "rows": [[i["mes"], f"R$ {i['faturado']:.2f}", f"R$ {i['pago']:.2f}"] for i in items]
    }


def generate_prazos(db: Session, start: date, end: date, org_id: int = None) -> dict:
    """Relatório de prazos (Lite)"""
    today = date.today()
    next_30 = today + timedelta(days=30)

    # Prazos futuros
    cases = tenant_query(db, Case, org_id).filter(
        Case.expiration_date.isnot(None),
        Case.expiration_date >= today,
        Case.expiration_date <= next_30,
        Case.status.notin_(["approved", "denied", "closed", "archived"])
    ).order_by(Case.expiration_date).limit(30).all()

    tasks = tenant_query(db, Task, org_id).filter(
        Task.due_date.isnot(None),
        Task.due_date >= today,
        Task.due_date <= next_30,
        Task.status != "completed"
    ).order_by(Task.due_date).limit(30).all()

    # Prazos vencidos (missed)
    missed_cases = tenant_query(db, Case, org_id).filter(
        Case.expiration_date.isnot(None),
        Case.expiration_date < today,
        Case.expiration_date >= start,
        Case.status.notin_(["approved", "denied", "closed", "archived"])
    ).count()

    missed_tasks = tenant_query(db, Task, org_id).filter(
        Task.due_date.isnot(None),
        Task.due_date < today,
        Task.due_date >= start,
        Task.status != "completed"
    ).count()

    case_items = [{
        "type": "Processo",
        "name": c.case_name or c.numero_processo or c.case_number,
        "deadline": c.expiration_date.strftime("%d/%m/%Y") if c.expiration_date else "",
        "days_left": (c.expiration_date - today).days if c.expiration_date else 0,
        "id": c.id
    } for c in cases]

    task_items = [{
        "type": "Tarefa",
        "name": t.title,
        "deadline": t.due_date.strftime("%d/%m/%Y") if t.due_date else "",
        "days_left": (t.due_date - today).days if t.due_date else 0,
        "id": t.id
    } for t in tasks]

    all_items = sorted(case_items + task_items, key=lambda x: x["days_left"])

    urgent = [i for i in all_items if i["days_left"] <= 7]
    warning = [i for i in all_items if 7 < i["days_left"] <= 14]
    upcoming = [i for i in all_items if i["days_left"] > 14]

    return {
        "type": "list",
        "items": all_items,
        "summary": {
            "urgent": len(urgent),
            "warning": len(warning),
            "upcoming": len(upcoming),
            "missed": missed_cases + missed_tasks,
            "total": len(all_items)
        },
        "grouped": {
            "urgent": urgent,
            "warning": warning,
            "upcoming": upcoming
        },
        "headers": ["Tipo", "Nome", "Prazo", "Dias Restantes"],
        "rows": [[i["type"], i["name"], i["deadline"], i["days_left"]] for i in all_items]
    }


def generate_clientes(db: Session, start: date, end: date, org_id: int = None) -> dict:
    """Relatório de clientes (Lite)"""
    # Novos clientes por mês
    monthly = db.query(
        func.date_trunc('month', Client.created_at).label("month"),
        func.count(Client.id).label("count")
    ).filter(
        Client.created_at >= start,
        Client.created_at <= end
    ).group_by(func.date_trunc('month', Client.created_at)).order_by("month").all()

    total_clients = db.query(func.count(Client.id)).scalar() or 0

    # Clientes com processos ativos
    active_clients = db.query(func.count(func.distinct(Case.client_id))).filter(
        Case.status.notin_(["closed", "denied", "archived"])
    ).scalar() or 0

    inactive_clients = total_clients - active_clients

    chart_data = {"labels": [], "values": []}
    items = []
    total_new = 0
    for month, count in monthly:
        month_str = month.strftime("%m/%Y") if month else "—"
        items.append({"mes": month_str, "novos": count})
        chart_data["labels"].append(month_str)
        chart_data["values"].append(count)
        total_new += count

    return {
        "type": "line_chart",
        "chart_data": chart_data,
        "items": items,
        "summary": {
            "total": total_clients,
            "completed": active_clients,
            "pending": inactive_clients,
            "completion_rate": (active_clients / total_clients * 100) if total_clients > 0 else 0
        },
        "headers": ["Mês", "Novos Clientes"],
        "rows": [[i["mes"], i["novos"]] for i in items]
    }
