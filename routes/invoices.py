"""
CaseHub - Invoice Routes
Generate and manage invoices from billing items
"""
from datetime import date, datetime
from typing import Optional
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from models import get_db, Client, Case, BillingItem, TimeEntry, User
from auth import get_current_user
from models.tenant import tenant_query
from i18n import get_translations
from config import settings
from core.currency import format_currency

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/invoices", tags=["invoices"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


def get_context(request: Request, db: Session, **kwargs):
    """Build template context."""
    # Use product-aware language resolution
    cookie_lang = request.cookies.get("lang")
    if cookie_lang:
        lang = cookie_lang
    else:
        product_state = getattr(getattr(request, "app", None), "state", None)
        if product_state and getattr(product_state, "product", None) == "lite":
            lang = "pt"
        else:
            lang = "en"
    user = get_current_user(request, db)
    return {
        "request": request,
        "PREFIX": PREFIX,
        "lang": lang,
        "t": get_translations(lang),
        "user": user,
        **kwargs
    }


def generate_invoice_number():
    """Generate unique invoice number."""
    today = date.today()
    return f"INV-{today.strftime('%Y%m')}-{datetime.now().strftime('%H%M%S')}"


@router.get("", response_class=HTMLResponse)
async def invoice_list(
    request: Request,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all invoices."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Get invoices (billing items with invoice_number)
    query = db.execute(text("""
        SELECT
            invoice_number,
            MIN(case_id) as case_id,
            MIN(created_at) as created_at,
            SUM(amount) as total,
            MAX(status) as status,
            COUNT(*) as item_count
        FROM billing_items
        WHERE invoice_number IS NOT NULL AND org_id = :org_id
        GROUP BY invoice_number
        ORDER BY MIN(created_at) DESC
    """), {"org_id": request.state.org_id})
    invoices = query.fetchall()

    # Calculate totals
    total_invoiced = sum(float(inv.total or 0) for inv in invoices)
    total_paid = sum(float(inv.total or 0) for inv in invoices if inv.status == 'paid')
    total_pending = sum(float(inv.total or 0) for inv in invoices if inv.status != 'paid')

    return templates.TemplateResponse("app/invoices/list.html", {
        **get_context(request, db),
        "invoices": invoices,
        "stats": {
            "total_invoiced": total_invoiced,
            "total_paid": total_paid,
            "total_pending": total_pending,
            "count": len(invoices)
        },
        "filter_status": status
    })


@router.get("/new", response_class=HTMLResponse)
async def new_invoice_form(
    request: Request,
    case_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Form to create new invoice."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Get cases with pending billing items
    cases = tenant_query(db, Case, request.state.org_id).all()

    # If case_id provided, get unbilled items for that case
    unbilled_items = []
    unbilled_time = []
    selected_case = None

    if case_id:
        selected_case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
        unbilled_items = tenant_query(db, BillingItem, request.state.org_id).filter(
            BillingItem.case_id == case_id,
            BillingItem.status == "pending",
            BillingItem.invoice_number.is_(None)
        ).all()
        unbilled_time = tenant_query(db, TimeEntry, request.state.org_id).filter(
            TimeEntry.case_id == case_id,
            TimeEntry.billable == True
        ).all()

    return templates.TemplateResponse("app/invoices/new.html", {
        **get_context(request, db),
        "cases": cases,
        "selected_case": selected_case,
        "unbilled_items": unbilled_items,
        "unbilled_time": unbilled_time,
        "invoice_number": generate_invoice_number()
    })


@router.post("/new")
async def create_invoice(
    request: Request,
    case_id: int = Form(...),
    invoice_number: str = Form(...),
    due_date: str = Form(None),
    notes: str = Form(None),
    item_ids: str = Form(""),  # Comma-separated billing item IDs
    include_time: bool = Form(False),
    time_rate: float = Form(0),
    db: Session = Depends(get_db)
):
    """Create a new invoice from selected billing items."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Get the case
    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Parse due date
    try:
        due = datetime.strptime(due_date, "%Y-%m-%d").date() if due_date else None
    except Exception as e:
        logger.error("Failed to parse invoice due_date '%s': %s", due_date, e)
        due = None

    # Update selected billing items with invoice number
    if item_ids:
        ids = [int(i) for i in item_ids.split(",") if i.strip().isdigit()]
        if ids:
            db.execute(text("""
                UPDATE billing_items
                SET invoice_number = :inv, status = 'invoiced', due_date = :due
                WHERE id IN :ids AND case_id = :case_id AND org_id = :org_id
            """), {"inv": invoice_number, "due": due, "ids": tuple(ids), "case_id": case_id, "org_id": request.state.org_id})

    # Convert time entries to billing items if requested
    if include_time and time_rate > 0:
        time_entries = tenant_query(db, TimeEntry, request.state.org_id).filter(
            TimeEntry.case_id == case_id,
            TimeEntry.billable == True
        ).all()

        # Get org currency - use org setting, fall back to product default
        org = getattr(getattr(request, "state", None), "org", None)
        product_defaults = getattr(getattr(request, "app", None), "state", None)
        default_currency = getattr(product_defaults, "product_defaults", {}).get("currency", "USD") if product_defaults else "USD"
        if isinstance(org, dict):
            _currency = org.get("currency", default_currency) or default_currency
        else:
            _currency = getattr(org, "currency", default_currency) or default_currency

        from core.currency import currency_symbol as _cs
        _sym = _cs(_currency)

        for entry in time_entries:
            amount = float(entry.hours) * time_rate
            billing_item = BillingItem(
                case_id=case_id,
                description=f"Time: {entry.description} ({entry.hours} hrs @ {_sym}{time_rate}/hr)",
                amount=amount,
                item_type="time",
                status="invoiced",
                invoice_number=invoice_number,
                due_date=due,
                notes=f"Date: {entry.date}",
        org_id=request.state.org_id)
            db.add(billing_item)
            # Mark time entry as billed
            entry.billable = False

    db.commit()

    return RedirectResponse(url=f"{PREFIX}/invoices/{invoice_number}", status_code=302)


@router.get("/{invoice_number}", response_class=HTMLResponse)
async def view_invoice(request: Request, invoice_number: str, db: Session = Depends(get_db)):
    """View invoice details."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Get invoice items
    items = tenant_query(db, BillingItem, request.state.org_id).filter(
        BillingItem.invoice_number == invoice_number
    ).all()

    if not items:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Get case and client info
    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == items[0].case_id).first()
    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first() if case else None

    # Calculate totals
    subtotal = sum(float(item.amount) for item in items)
    total = subtotal  # Add tax calculation if needed

    return templates.TemplateResponse("app/invoices/view.html", {
        **get_context(request, db),
        "invoice_number": invoice_number,
        "items": items,
        "case": case,
        "client": client,
        "subtotal": subtotal,
        "total": total,
        "status": items[0].status if items else "pending",
        "due_date": items[0].due_date if items else None
    })


@router.get("/{invoice_number}/print", response_class=HTMLResponse)
async def print_invoice(request: Request, invoice_number: str, db: Session = Depends(get_db)):
    """Printable invoice view."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    items = tenant_query(db, BillingItem, request.state.org_id).filter(
        BillingItem.invoice_number == invoice_number
    ).all()

    if not items:
        raise HTTPException(status_code=404, detail="Invoice not found")

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == items[0].case_id).first()
    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first() if case else None

    subtotal = sum(float(item.amount) for item in items)

    return templates.TemplateResponse("app/invoices/print.html", {
        **get_context(request, db),
        "invoice_number": invoice_number,
        "items": items,
        "case": case,
        "client": client,
        "subtotal": subtotal,
        "total": subtotal,
        "due_date": items[0].due_date if items else None,
        "invoice_date": items[0].created_at if items else datetime.now()
    })


@router.post("/{invoice_number}/mark-paid")
async def mark_invoice_paid(request: Request, invoice_number: str, db: Session = Depends(get_db)):
    """Mark entire invoice as paid."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    db.execute(text("""
        UPDATE billing_items
        SET status = 'paid', paid_date = :today
        WHERE invoice_number = :inv AND org_id = :org_id
    """), {"inv": invoice_number, "today": date.today(), "org_id": request.state.org_id})
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/invoices/{invoice_number}", status_code=302)


@router.post("/{invoice_number}/send")
async def send_invoice_email(request: Request, invoice_number: str, db: Session = Depends(get_db)):
    """Send invoice via email."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Get invoice details
    items = tenant_query(db, BillingItem, request.state.org_id).filter(
        BillingItem.invoice_number == invoice_number
    ).all()

    if not items:
        raise HTTPException(status_code=404, detail="Invoice not found")

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == items[0].case_id).first()
    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first() if case else None

    if not client or not client.email:
        raise HTTPException(status_code=400, detail="Client has no email address")

    # Send email using email service
    try:
        from services.email_service import email_service
        total = sum(float(item.amount) for item in items)

        # Get org currency - use org setting, fall back to product default
        org = getattr(getattr(request, "state", None), "org", None)
        product_defaults = getattr(getattr(request, "app", None), "state", None)
        default_currency = getattr(product_defaults, "product_defaults", {}).get("currency", "USD") if product_defaults else "USD"
        if isinstance(org, dict):
            org_currency = org.get("currency", default_currency) or default_currency
        else:
            org_currency = getattr(org, "currency", default_currency) or default_currency

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h1>Invoice {invoice_number}</h1>
            <p>Dear {client.first_name} {client.last_name},</p>
            <p>Please find your invoice details below:</p>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <tr style="background: #f8f9fa;">
                    <th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Description</th>
                    <th style="padding: 10px; text-align: right; border: 1px solid #ddd;">Amount</th>
                </tr>
                {''.join(f'<tr><td style="padding: 10px; border: 1px solid #ddd;">{item.description}</td><td style="padding: 10px; text-align: right; border: 1px solid #ddd;">{format_currency(item.amount, org_currency)}</td></tr>' for item in items)}
                <tr style="background: #f8f9fa; font-weight: bold;">
                    <td style="padding: 10px; border: 1px solid #ddd;">Total</td>
                    <td style="padding: 10px; text-align: right; border: 1px solid #ddd;">{format_currency(total, org_currency)}</td>
                </tr>
            </table>
            <p>Thank you for your business.</p>
            <hr>
            <p style="color: #666; font-size: 12px;">{settings.ORG_NAME} | {settings.ORG_DOMAIN or settings.BASE_URL}</p>
        </body>
        </html>
        """

        result = email_service.send_email(
            to_email=client.email,
            subject=f"Invoice {invoice_number} from {settings.ORG_NAME}",
            html_content=html
        )

        if result["success"]:
            return JSONResponse({"success": True, "message": f"Invoice sent to {client.email}"})
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to send email"))

    except ImportError:
        raise HTTPException(status_code=500, detail="Email service not available")


@router.get("/{invoice_number}/pdf")
async def download_invoice_pdf(request: Request, invoice_number: str, db: Session = Depends(get_db)):
    """Download invoice as PDF."""
    from services.pdf_service import pdf_service
    from fastapi.responses import Response

    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    items = tenant_query(db, BillingItem, request.state.org_id).filter(
        BillingItem.invoice_number == invoice_number
    ).all()

    if not items:
        raise HTTPException(status_code=404, detail="Invoice not found")

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == items[0].case_id).first()
    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first() if case else None

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    subtotal = sum(float(item.amount or 0) for item in items)
    invoice_data = {
        "invoice_number": invoice_number,
        "client_name": f"{client.first_name} {client.last_name}",
        "client_address": client.address if hasattr(client, 'address') else None,
        "client_email": client.email,
        "case_name": case.case_name if case else None,
        "items": [{"description": item.description, "amount": float(item.amount or 0)} for item in items],
        "subtotal": subtotal,
        "tax": 0,
        "total": subtotal,
        "due_date": items[0].due_date if items[0].due_date else None,
        "invoice_date": items[0].created_at if items else datetime.now(),
        "paid": items[0].status == 'paid' if items else False,
        "notes": None
    }

    pdf_bytes = pdf_service.generate_invoice_pdf(invoice_data)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=Invoice_{invoice_number}.pdf"
        }
    )
