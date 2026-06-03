"""
CaseHub - Payment Routes
Handle Stripe payment processing.
"""
from datetime import date, datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, Request, Form, HTTPException, Header
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, Client, Case, BillingItem, User
from auth import get_current_user
from models.tenant import tenant_query
from services.stripe_service import stripe_service
from config import settings

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/payments", tags=["payments"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


@router.get("", response_class=HTMLResponse)
async def payment_overview(request: Request, db: Session = Depends(get_db)):
    """Payment overview page."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Get payment statistics
    try:
        result = db.execute(text("""
            SELECT
                SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END) as total_paid,
                SUM(CASE WHEN status != 'paid' THEN amount ELSE 0 END) as total_pending,
                COUNT(DISTINCT CASE WHEN status = 'paid' THEN invoice_number END) as paid_invoices,
                COUNT(DISTINCT CASE WHEN status != 'paid' THEN invoice_number END) as pending_invoices
            FROM billing_items
            WHERE invoice_number IS NOT NULL
        """))
        stats = result.fetchone()
    except Exception as e:
        logger.error("Failed to fetch payment stats: %s", e)
        stats = None

    return templates.TemplateResponse("app/payments/overview.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "stats": {
            "total_paid": float(stats.total_paid or 0) if stats else 0,
            "total_pending": float(stats.total_pending or 0) if stats else 0,
            "paid_invoices": stats.paid_invoices if stats else 0,
            "pending_invoices": stats.pending_invoices if stats else 0
        },
        "stripe_configured": stripe_service.is_configured()
    })


@router.get("/checkout/{invoice_number}", response_class=HTMLResponse)
async def payment_checkout(request: Request, invoice_number: str, db: Session = Depends(get_db)):
    """Checkout page for an invoice."""
    # Get invoice items
    items = tenant_query(db, BillingItem, request.state.org_id).filter(
        BillingItem.invoice_number == invoice_number,
        BillingItem.status != 'paid'
    ).all()

    if not items:
        return templates.TemplateResponse("app/payments/error.html", {
            "request": request,
            "PREFIX": PREFIX,
            "error": "Invoice not found or already paid"
        })

    # Get case and client info
    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == items[0].case_id).first()
    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first() if case else None

    total = sum(float(item.amount or 0) for item in items)

    return templates.TemplateResponse("app/payments/checkout.html", {
        "request": request,
        "PREFIX": PREFIX,
        "invoice_number": invoice_number,
        "items": items,
        "total": total,
        "client": client,
        "case": case,
        "stripe_configured": stripe_service.is_configured(),
        "publishable_key": stripe_service.publishable_key
    })


@router.post("/create-checkout-session")
async def create_checkout_session(
    request: Request,
    invoice_number: str = Form(...),
    db: Session = Depends(get_db)
):
    """Create a Stripe checkout session."""
    if not stripe_service.is_configured():
        raise HTTPException(status_code=400, detail="Payment system not configured")

    # Get invoice items
    items = tenant_query(db, BillingItem, request.state.org_id).filter(
        BillingItem.invoice_number == invoice_number,
        BillingItem.status != 'paid'
    ).all()

    if not items:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Get client info
    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == items[0].case_id).first()
    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first() if case else None

    total = sum(float(item.amount or 0) for item in items)

    # Create checkout session
    result = stripe_service.create_checkout_session(
        amount=total,
        invoice_number=invoice_number,
        client_email=client.email if client else None,
        description=f"Payment for {case.case_name}" if case else "Invoice Payment",
        metadata={
            "case_id": str(case.id) if case else "",
            "client_id": str(client.id) if client else ""
        }
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return JSONResponse(content=result)


@router.get("/success", response_class=HTMLResponse)
async def payment_success(
    request: Request,
    session_id: Optional[str] = None,
    invoice: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Payment success page."""
    payment_info = None

    if session_id and stripe_service.is_configured():
        # Retrieve session to verify payment
        session = stripe_service.retrieve_session(session_id)
        if "error" not in session and session.get("payment_status") == "paid":
            # Mark invoice as paid
            if invoice:
                try:
                    db.execute(text("""
                        UPDATE billing_items
                        SET status = 'paid', paid_date = :today
                        WHERE invoice_number = :inv
                    """), {"inv": invoice, "today": date.today()})
                    db.commit()
                except Exception as e:
                    db.rollback()

            payment_info = {
                "amount": session.get("amount_total", 0),
                "email": session.get("customer_email"),
                "invoice": invoice
            }

    return templates.TemplateResponse("app/payments/success.html", {
        "request": request,
        "PREFIX": PREFIX,
        "payment_info": payment_info,
        "invoice_number": invoice
    })


@router.get("/cancel", response_class=HTMLResponse)
async def payment_cancel(
    request: Request,
    invoice: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Payment cancelled page."""
    return templates.TemplateResponse("app/payments/cancel.html", {
        "request": request,
        "PREFIX": PREFIX,
        "invoice_number": invoice
    })


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
    db: Session = Depends(get_db)
):
    """Handle Stripe webhooks for payment confirmation."""
    if not stripe_service.is_configured():
        raise HTTPException(status_code=400, detail="Stripe not configured")

    payload = await request.body()
    event = stripe_service.verify_webhook(payload, stripe_signature)

    if "error" in event:
        raise HTTPException(status_code=400, detail=event["error"])

    # Handle the event
    event_type = event.get("type")
    data = event.get("data", {})

    if event_type == "checkout.session.completed":
        # Payment completed
        invoice_number = data.get("metadata", {}).get("invoice_number")
        if invoice_number:
            try:
                db.execute(text("""
                    UPDATE billing_items
                    SET status = 'paid', paid_date = :today
                    WHERE invoice_number = :inv
                """), {"inv": invoice_number, "today": date.today()})
                db.commit()
            except Exception as e:
                db.rollback()

    elif event_type == "payment_intent.succeeded":
        # Alternative payment confirmation
        invoice_number = data.get("metadata", {}).get("invoice_number")
        if invoice_number:
            try:
                db.execute(text("""
                    UPDATE billing_items
                    SET status = 'paid', paid_date = :today
                    WHERE invoice_number = :inv
                """), {"inv": invoice_number, "today": date.today()})
                db.commit()
            except Exception as e:
                db.rollback()

    return JSONResponse(content={"status": "received"})


@router.get("/link/{invoice_number}")
async def get_payment_link(
    request: Request,
    invoice_number: str,
    db: Session = Depends(get_db)
):
    """Generate a payment link for an invoice."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Get invoice items
    items = tenant_query(db, BillingItem, request.state.org_id).filter(
        BillingItem.invoice_number == invoice_number,
        BillingItem.status != 'paid'
    ).all()

    if not items:
        raise HTTPException(status_code=404, detail="Invoice not found or already paid")

    total = sum(float(item.amount or 0) for item in items)

    if not stripe_service.is_configured():
        # Return basic payment link if Stripe not configured
        return JSONResponse(content={
            "link": f"{settings.BASE_URL}/casehub/payments/checkout/{invoice_number}",
            "amount": total,
            "stripe_enabled": False
        })

    # Get client info
    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == items[0].case_id).first()
    client = tenant_query(db, Client, request.state.org_id).filter(Client.id == case.client_id).first() if case else None

    # Create checkout session
    result = stripe_service.create_checkout_session(
        amount=total,
        invoice_number=invoice_number,
        client_email=client.email if client else None,
        description=f"Payment for Invoice {invoice_number}"
    )

    if "error" in result:
        return JSONResponse(content={
            "link": f"{settings.BASE_URL}/casehub/payments/checkout/{invoice_number}",
            "amount": total,
            "stripe_enabled": False,
            "error": result["error"]
        })

    return JSONResponse(content={
        "link": result["checkout_url"],
        "amount": total,
        "stripe_enabled": True,
        "session_id": result["session_id"]
    })
