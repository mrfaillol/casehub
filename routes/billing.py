"""
CaseHub - Billing Routes
"""
from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func
from typing import Optional
from datetime import datetime, date, timedelta
from decimal import Decimal
import json

from models import get_db, Client, Case, User, BillingItem, TimeEntry
from auth import get_current_user
from models.tenant import tenant_query
from core.currency import format_currency
from config import settings

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/billing", tags=["billing"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py
templates.env.globals["now"] = lambda: date.today()
# templates.env.globals["PREFIX"] = PREFIX  # Configured in template_config.py

def parse_date(date_str: str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None

@router.get("", response_class=HTMLResponse)
async def billing_dashboard(
    request: Request,
    case_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    # Get billing items
    query = tenant_query(db, BillingItem, request.state.org_id)
    if case_id:
        query = query.filter(BillingItem.case_id == case_id)
    if status:
        query = query.filter(BillingItem.status == status)
    
    billing_items = query.order_by(BillingItem.created_at.desc()).limit(50).all()
    
    # Calculate totals
    total_pending = tenant_query(db, BillingItem, request.state.org_id).with_entities(sql_func.sum(BillingItem.amount)).filter(
        BillingItem.status == "pending",
        BillingItem.item_type != "payment"
    ).scalar() or Decimal('0')
    
    total_paid = tenant_query(db, BillingItem, request.state.org_id).with_entities(sql_func.sum(BillingItem.amount)).filter(
        BillingItem.status == "paid",
        BillingItem.item_type != "payment"
    ).scalar() or Decimal('0')
    
    total_payments = tenant_query(db, BillingItem, request.state.org_id).with_entities(sql_func.sum(BillingItem.amount)).filter(
        BillingItem.item_type == "payment"
    ).scalar() or Decimal('0')
    
    # Total billed (all non-payment items regardless of status)
    total_billed = tenant_query(db, BillingItem, request.state.org_id).with_entities(sql_func.sum(BillingItem.amount)).filter(
        BillingItem.item_type != "payment"
    ).scalar() or Decimal('0')

    # Overdue items: pending/invoiced with due_date in the past
    today = date.today()
    total_overdue = tenant_query(db, BillingItem, request.state.org_id).with_entities(sql_func.sum(BillingItem.amount)).filter(
        BillingItem.status.in_(["pending", "invoiced"]),
        BillingItem.item_type != "payment",
        BillingItem.due_date < today
    ).scalar() or Decimal('0')

    # Pending/overdue items for "Contas a receber" table
    receivables_query = tenant_query(db, BillingItem, request.state.org_id).filter(
        BillingItem.status.in_(["pending", "invoiced"]),
        BillingItem.item_type != "payment"
    ).order_by(BillingItem.due_date.asc().nullslast())
    receivables = receivables_query.limit(50).all()

    # Monthly revenue (last 6 months) — sum of paid items grouped by month
    six_months_ago = today - timedelta(days=180)
    monthly_revenue_rows = tenant_query(db, BillingItem, request.state.org_id).with_entities(
        sql_func.date_trunc('month', BillingItem.paid_date).label('month'),
        sql_func.sum(BillingItem.amount).label('total')
    ).filter(
        BillingItem.status == "paid",
        BillingItem.item_type != "payment",
        BillingItem.paid_date >= six_months_ago
    ).group_by('month').order_by('month').all()

    # Build chart data (fill missing months with 0)
    monthly_labels = []
    monthly_values = []
    revenue_by_month = {}
    for row in monthly_revenue_rows:
        if row.month:
            key = row.month.strftime('%Y-%m')
            revenue_by_month[key] = float(row.total or 0)

    for i in range(5, -1, -1):
        d = today - timedelta(days=30 * i)
        key = d.strftime('%Y-%m')
        label = d.strftime('%b/%y')
        monthly_labels.append(label)
        monthly_values.append(revenue_by_month.get(key, 0))

    # Get recent time entries
    time_entries = tenant_query(db, TimeEntry, request.state.org_id).order_by(TimeEntry.date.desc()).limit(20).all()

    # Calculate billable hours
    billable_hours = tenant_query(db, TimeEntry, request.state.org_id).with_entities(sql_func.sum(TimeEntry.hours)).filter(
        TimeEntry.billable == True
    ).scalar() or Decimal('0')

    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).all()
    billing_currency = settings.DEFAULT_CURRENCY or ("BRL" if settings.CASEHUB_PRODUCT == "lite" else "USD")

    return templates.TemplateResponse("app/billing/dashboard.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "billing_items": billing_items,
        "time_entries": time_entries,
        "receivables": receivables,
        "cases": cases,
        "today": today,
        "stats": {
            "total_billed": total_billed,
            "total_pending": total_pending,
            "total_paid": total_paid,
            "total_overdue": total_overdue,
            "total_payments": total_payments,
            "billable_hours": billable_hours,
            "currency": billing_currency,
            "total_billed_formatted": format_currency(total_billed, billing_currency),
            "total_pending_formatted": format_currency(total_pending, billing_currency),
            "total_paid_formatted": format_currency(total_paid, billing_currency),
            "total_overdue_formatted": format_currency(total_overdue, billing_currency),
        },
        "chart_labels": json.dumps(monthly_labels),
        "chart_values": json.dumps(monthly_values),
        "selected_case_id": case_id,
        "selected_status": status
    })

@router.get("/items/new", response_class=HTMLResponse)
async def new_billing_item(
    request: Request,
    case_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).all()
    
    return templates.TemplateResponse("app/billing/item_form.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "item": None,
        "cases": cases,
        "selected_case_id": case_id,
        "action": "Create"
    })

@router.post("/items/new")
async def create_billing_item(
    request: Request,
    case_id: int = Form(...),
    description: str = Form(...),
    amount: float = Form(...),
    item_type: str = Form("fee"),
    status: str = Form("pending"),
    due_date: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    item = BillingItem(
        case_id=case_id,
        description=description,
        amount=amount,
        item_type=item_type,
        status=status,
        due_date=parse_date(due_date),
        notes=notes,
        paid_date=date.today() if status == "paid" else None,
        org_id=request.state.org_id)
    db.add(item)
    db.commit()
    
    return RedirectResponse(url=f"{PREFIX}/billing", status_code=302)

@router.get("/items/{item_id}/edit", response_class=HTMLResponse)
async def edit_billing_item_form(request: Request, item_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    item = tenant_query(db, BillingItem, request.state.org_id).filter(BillingItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Billing item not found")
    
    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).all()
    
    return templates.TemplateResponse("app/billing/item_form.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "item": item,
        "cases": cases,
        "selected_case_id": None,
        "action": "Update"
    })

@router.post("/items/{item_id}/edit")
async def update_billing_item(
    request: Request,
    item_id: int,
    case_id: int = Form(...),
    description: str = Form(...),
    amount: float = Form(...),
    item_type: str = Form("fee"),
    status: str = Form("pending"),
    due_date: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    item = tenant_query(db, BillingItem, request.state.org_id).filter(BillingItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Billing item not found")
    
    # Track status change
    was_paid = item.status == "paid"
    
    item.case_id = case_id
    item.description = description
    item.amount = amount
    item.item_type = item_type
    item.status = status
    item.due_date = parse_date(due_date)
    item.notes = notes
    
    # Set paid_date when marking as paid
    if status == "paid" and not was_paid:
        item.paid_date = date.today()
    elif status != "paid":
        item.paid_date = None
    
    db.commit()
    
    return RedirectResponse(url=f"{PREFIX}/billing", status_code=302)

@router.post("/items/{item_id}/delete")
async def delete_billing_item(request: Request, item_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    item = tenant_query(db, BillingItem, request.state.org_id).filter(BillingItem.id == item_id).first()
    if item:
        db.delete(item)
        db.commit()
    
    return RedirectResponse(url=f"{PREFIX}/billing", status_code=302)

@router.post("/items/{item_id}/mark-paid")
async def mark_billing_item_paid(request: Request, item_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    item = tenant_query(db, BillingItem, request.state.org_id).filter(BillingItem.id == item_id).first()
    if item:
        item.status = "paid"
        item.paid_date = date.today()
        db.commit()
    
    return RedirectResponse(url=f"{PREFIX}/billing", status_code=302)

# Time Entries
@router.get("/time/new", response_class=HTMLResponse)
async def new_time_entry(
    request: Request,
    case_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    cases = tenant_query(db, Case, request.state.org_id).order_by(Case.created_at.desc()).all()
    users = tenant_query(db, User, request.state.org_id).filter(User.enabled == True).all()
    
    return templates.TemplateResponse("app/billing/time_form.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "entry": None,
        "cases": cases,
        "users": users,
        "selected_case_id": case_id,
        "action": "Create"
    })

@router.post("/time/new")
async def create_time_entry(
    request: Request,
    case_id: int = Form(...),
    user_id: str = Form(None),
    description: str = Form(...),
    hours: float = Form(...),
    rate: str = Form(None),
    entry_date: str = Form(...),
    billable: bool = Form(True),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Convert form strings to proper types
    user_id = form_int(user_id)
    rate = form_float(rate)

    entry = TimeEntry(
        case_id=case_id,
        user_id=user_id if user_id else user.id,
        description=description,
        hours=hours,
        rate=rate,
        date=parse_date(entry_date) or date.today(),
        billable=billable,
        org_id=request.state.org_id)
    db.add(entry)
    db.commit()
    
    return RedirectResponse(url=f"{PREFIX}/billing", status_code=302)

@router.post("/time/{entry_id}/delete")
async def delete_time_entry(request: Request, entry_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)
    
    entry = tenant_query(db, TimeEntry, request.state.org_id).filter(TimeEntry.id == entry_id).first()
    if entry:
        db.delete(entry)
        db.commit()
    
    return RedirectResponse(url=f"{PREFIX}/billing", status_code=302)
