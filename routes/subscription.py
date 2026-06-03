"""
CaseHub - Subscription Management Routes
Plan management, Stripe billing, usage tracking.
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text, func as sql_func

from models import get_db, User, Client, Case, Document
from auth import get_current_user
from models.tenant import tenant_query, tenant_count
from config import settings

logger = logging.getLogger(__name__)

try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False

router = APIRouter(prefix="/subscription", tags=["subscription"])

# ---------------------------------------------------------------------------
# Plan definitions (mirrors DB plans table)
#
# Spec (Victor, 28/05/2026): exactly two plans.
#   - office     R$ 129/mês — Pequenos escritórios e Sociedade Unipessoal de Advocacia
#   - enterprise Sob consulta — grandes escritórios (sem preço fixo, CTA de contato)
# Usuários ILIMITADOS por enquanto em ambos: max_users = -1 (convenção
# unlimited, ver middleware/plan_enforcement.py: -1 ou None => sem limite).
#
# Conventions:
#   price_monthly: int em centavos, ou None quando o preço é "sob consulta".
#   price_label:   string opcional a exibir quando não há preço fixo.
#   contact_only:  True => sem checkout Stripe, CTA de contato comercial.
# ---------------------------------------------------------------------------
DEFAULT_PLAN = "office"

PLAN_FEATURES = {
    "office": {
        "display_name": "Pequenos escritórios e Sociedade Unipessoal de Advocacia",
        "price_monthly": 129_00,
        "price_label": None,
        "contact_only": False,
        "max_users": -1,   # unlimited (por enquanto)
        "max_cases": -1,   # unlimited (por enquanto)
        "features": [
            "cases", "clients", "documents", "drive_sync", "email", "tasks",
            "ai_lor", "ai_ps", "package_builder", "crm", "whatsapp", "reports",
        ],
    },
    "enterprise": {
        "display_name": "Enterprise",
        "price_monthly": None,        # sob consulta — sem preço fixo
        "price_label": "Sob consulta",
        "contact_only": True,
        "max_users": -1,   # unlimited (por enquanto)
        "max_cases": -1,   # unlimited (por enquanto)
        "features": [
            "cases", "clients", "documents", "drive_sync", "email", "tasks",
            "ai_lor", "ai_ps", "package_builder", "crm", "whatsapp", "reports",
            "sso", "custom_domain", "api_access", "audit", "priority_support",
        ],
    },
}


def _get_org(request: Request) -> dict:
    """Get org dict from request state or raise."""
    org = getattr(getattr(request, "state", None), "org", None)
    if not org:
        raise HTTPException(status_code=403, detail="No organization context.")
    return org


def _stripe_configured() -> bool:
    return STRIPE_AVAILABLE and bool(settings.STRIPE_SECRET_KEY)


def _init_stripe():
    if _stripe_configured():
        stripe.api_key = settings.STRIPE_SECRET_KEY


# ---------------------------------------------------------------------------
# GET /subscription — Current plan, usage, next billing date
# ---------------------------------------------------------------------------
@router.get("", response_class=HTMLResponse)
async def subscription_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(f"{PREFIX}/login", status_code=302)

    org = _get_org(request)
    plan_name = org.get("plan") or DEFAULT_PLAN
    if plan_name not in PLAN_FEATURES:
        # Legacy plan value (e.g. starter/professional) → default plan.
        plan_name = DEFAULT_PLAN
    plan_info = PLAN_FEATURES[plan_name]

    # Usage counts
    org_id = org["id"]
    user_count = db.execute(
        text("SELECT COUNT(*) FROM users WHERE org_id = :oid AND enabled = TRUE"),
        {"oid": org_id},
    ).scalar() or 0

    case_count = db.execute(
        text("SELECT COUNT(*) FROM cases WHERE org_id = :oid"),
        {"oid": org_id},
    ).scalar() or 0

    doc_count = db.execute(
        text("SELECT COUNT(*) FROM documents WHERE org_id = :oid"),
        {"oid": org_id},
    ).scalar() or 0

    # Stripe subscription info
    next_billing = None
    subscription_status = org.get("subscription_status", "active")
    stripe_sub = None
    if _stripe_configured() and org.get("stripe_subscription_id"):
        _init_stripe()
        try:
            stripe_sub = stripe.Subscription.retrieve(org["stripe_subscription_id"])
            if stripe_sub.current_period_end:
                next_billing = datetime.fromtimestamp(stripe_sub.current_period_end)
            subscription_status = stripe_sub.status
        except Exception as e:
            logger.warning(f"Failed to retrieve Stripe subscription: {e}")

    context = {
        "request": request,
        "user": user,
        "org": org,
        "plan_name": plan_name,
        "plan_info": plan_info,
        "all_plans": PLAN_FEATURES,
        "user_count": user_count,
        "case_count": case_count,
        "doc_count": doc_count,
        "max_users": plan_info["max_users"],
        "max_cases": plan_info["max_cases"],
        "next_billing": next_billing,
        "subscription_status": subscription_status,
        "stripe_configured": _stripe_configured(),
        "PREFIX": PREFIX,
    }

    return templates.TemplateResponse("app/subscription/dashboard.html", context)


# ---------------------------------------------------------------------------
# GET /subscription/usage — JSON usage stats
# ---------------------------------------------------------------------------
@router.get("/usage", response_class=JSONResponse)
async def subscription_usage(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    org = _get_org(request)
    org_id = org["id"]
    plan_name = org.get("plan") or DEFAULT_PLAN
    if plan_name not in PLAN_FEATURES:
        plan_name = DEFAULT_PLAN
    plan_info = PLAN_FEATURES[plan_name]

    user_count = db.execute(
        text("SELECT COUNT(*) FROM users WHERE org_id = :oid AND enabled = TRUE"),
        {"oid": org_id},
    ).scalar() or 0

    case_count = db.execute(
        text("SELECT COUNT(*) FROM cases WHERE org_id = :oid"),
        {"oid": org_id},
    ).scalar() or 0

    doc_count = db.execute(
        text("SELECT COUNT(*) FROM documents WHERE org_id = :oid"),
        {"oid": org_id},
    ).scalar() or 0

    return {
        "plan": plan_name,
        "users": {"current": user_count, "limit": plan_info["max_users"]},
        "cases": {"current": case_count, "limit": plan_info["max_cases"]},
        "documents": {"current": doc_count, "limit": -1},
        "features": plan_info["features"],
    }


# ---------------------------------------------------------------------------
# POST /subscription/checkout — Create Stripe Checkout for plan upgrade
# ---------------------------------------------------------------------------
@router.post("/checkout", response_class=JSONResponse)
async def subscription_checkout(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not _stripe_configured():
        raise HTTPException(status_code=503, detail="Stripe is not configured")

    _init_stripe()
    org = _get_org(request)

    body = await request.json()
    target_plan = body.get("plan", DEFAULT_PLAN)

    if target_plan not in PLAN_FEATURES:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {target_plan}")

    # Contact-only plans (e.g. Enterprise "Sob consulta") have no fixed price
    # and therefore no self-service Stripe checkout — route to commercial contact.
    if PLAN_FEATURES[target_plan].get("contact_only"):
        raise HTTPException(
            status_code=400,
            detail="Este plano é sob consulta. Fale com o time comercial para contratar.",
        )

    # Look up or create the Stripe price_id from plans table
    row = db.execute(
        text("SELECT stripe_price_id FROM plans WHERE name = :name AND is_active = TRUE"),
        {"name": target_plan},
    ).first()

    if not row or not row[0]:
        raise HTTPException(
            status_code=400,
            detail=f"No Stripe price configured for plan '{target_plan}'. Contact support.",
        )

    stripe_price_id = row[0]

    # Ensure Stripe customer exists
    customer_id = org.get("stripe_customer_id")
    if not customer_id:
        customer = stripe.Customer.create(
            email=org.get("email") or user.email,
            name=org.get("name", ""),
            metadata={"org_id": str(org["id"]), "org_slug": org.get("slug", "")},
        )
        customer_id = customer.id
        db.execute(
            text("UPDATE organizations SET stripe_customer_id = :cid WHERE id = :oid"),
            {"cid": customer_id, "oid": org["id"]},
        )
        db.commit()

    # Create Checkout Session for subscription
    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": stripe_price_id, "quantity": 1}],
        mode="subscription",
        success_url=f"{settings.BASE_URL}{PREFIX}/subscription?checkout=success",
        cancel_url=f"{settings.BASE_URL}{PREFIX}/subscription?checkout=cancel",
        metadata={
            "org_id": str(org["id"]),
            "plan": target_plan,
        },
    )

    return {"checkout_url": session.url, "session_id": session.id}


# ---------------------------------------------------------------------------
# POST /subscription/cancel — Cancel subscription with grace period
# ---------------------------------------------------------------------------
@router.post("/cancel", response_class=JSONResponse)
async def subscription_cancel(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not _stripe_configured():
        raise HTTPException(status_code=503, detail="Stripe is not configured")

    _init_stripe()
    org = _get_org(request)

    sub_id = org.get("stripe_subscription_id")
    if not sub_id:
        raise HTTPException(status_code=400, detail="No active subscription to cancel")

    try:
        # Cancel at period end (grace period until billing cycle ends)
        subscription = stripe.Subscription.modify(
            sub_id,
            cancel_at_period_end=True,
        )
        db.execute(
            text("UPDATE organizations SET subscription_status = 'canceling' WHERE id = :oid"),
            {"oid": org["id"]},
        )
        db.commit()

        cancel_at = None
        if subscription.current_period_end:
            cancel_at = datetime.fromtimestamp(subscription.current_period_end).isoformat()

        return {
            "status": "canceling",
            "message": "Subscription will be canceled at end of current billing period.",
            "cancel_at": cancel_at,
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# POST /subscription/webhook — Stripe webhook handler
# ---------------------------------------------------------------------------
@router.post("/webhook")
async def subscription_webhook(request: Request, db: Session = Depends(get_db)):
    if not _stripe_configured():
        raise HTTPException(status_code=503, detail="Stripe not configured")

    _init_stripe()

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    event_type = event["type"]
    data_object = event["data"]["object"]

    logger.info(f"Stripe webhook: {event_type}")

    if event_type == "invoice.paid":
        _handle_invoice_paid(db, data_object)
    elif event_type == "customer.subscription.updated":
        _handle_subscription_updated(db, data_object)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(db, data_object)
    elif event_type == "checkout.session.completed":
        _handle_checkout_completed(db, data_object)

    return {"status": "ok"}


def _handle_invoice_paid(db: Session, invoice: dict):
    """Handle successful invoice payment — keep subscription active."""
    customer_id = invoice.get("customer")
    if not customer_id:
        return
    db.execute(
        text(
            "UPDATE organizations SET subscription_status = 'active' "
            "WHERE stripe_customer_id = :cid"
        ),
        {"cid": customer_id},
    )
    db.commit()
    logger.info(f"Invoice paid for customer {customer_id}")


def _handle_subscription_updated(db: Session, subscription: dict):
    """Handle subscription status changes (e.g., past_due, active)."""
    customer_id = subscription.get("customer")
    sub_status = subscription.get("status", "active")
    sub_id = subscription.get("id")

    if not customer_id:
        return

    # Update plan from Stripe product metadata if available
    plan_name = None
    items = subscription.get("items", {}).get("data", [])
    if items:
        metadata = items[0].get("price", {}).get("metadata", {})
        plan_name = metadata.get("plan")

    if plan_name and plan_name in PLAN_FEATURES:
        plan_info = PLAN_FEATURES[plan_name]
        db.execute(
            text(
                "UPDATE organizations SET "
                "stripe_subscription_id = :sid, subscription_status = :ss, "
                "plan = :plan, max_users = :mu, max_clients = :mc "
                "WHERE stripe_customer_id = :cid"
            ),
            {
                "sid": sub_id,
                "ss": sub_status,
                "plan": plan_name,
                "mu": plan_info["max_users"],
                "mc": plan_info["max_cases"],
                "cid": customer_id,
            },
        )
    else:
        db.execute(
            text(
                "UPDATE organizations SET "
                "stripe_subscription_id = :sid, subscription_status = :ss "
                "WHERE stripe_customer_id = :cid"
            ),
            {"sid": sub_id, "ss": sub_status, "cid": customer_id},
        )
    db.commit()
    logger.info(f"Subscription updated: {sub_id} -> {sub_status}")


def _handle_subscription_deleted(db: Session, subscription: dict):
    """Handle subscription cancellation — downgrade to the default plan.

    With unlimited users on every plan, a downgrade no longer reduces seats;
    it just clears the Stripe link and marks the subscription canceled.
    """
    customer_id = subscription.get("customer")
    if not customer_id:
        return

    default_plan = PLAN_FEATURES[DEFAULT_PLAN]
    db.execute(
        text(
            "UPDATE organizations SET "
            "subscription_status = 'canceled', plan = :plan, "
            "max_users = :mu, max_clients = :mc, stripe_subscription_id = NULL "
            "WHERE stripe_customer_id = :cid"
        ),
        {
            "plan": DEFAULT_PLAN,
            "mu": default_plan["max_users"],
            "mc": default_plan["max_cases"],
            "cid": customer_id,
        },
    )
    db.commit()
    logger.info(
        f"Subscription deleted for customer {customer_id} — downgraded to {DEFAULT_PLAN}"
    )


def _handle_checkout_completed(db: Session, session: dict):
    """Handle checkout.session.completed — link subscription to org."""
    org_id = session.get("metadata", {}).get("org_id")
    plan_name = session.get("metadata", {}).get("plan")
    subscription_id = session.get("subscription")
    customer_id = session.get("customer")

    if not org_id or not subscription_id:
        return

    if plan_name not in PLAN_FEATURES:
        plan_name = DEFAULT_PLAN
    plan_info = PLAN_FEATURES[plan_name]

    db.execute(
        text(
            "UPDATE organizations SET "
            "stripe_customer_id = :cid, stripe_subscription_id = :sid, "
            "subscription_status = 'active', plan = :plan, "
            "max_users = :mu, max_clients = :mc "
            "WHERE id = :oid"
        ),
        {
            "cid": customer_id,
            "sid": subscription_id,
            "plan": plan_name,
            "mu": plan_info["max_users"],
            "mc": plan_info["max_cases"],
            "oid": int(org_id),
        },
    )
    db.commit()
    logger.info(f"Checkout completed: org {org_id} -> plan {plan_name}")


# ---------------------------------------------------------------------------
# GET /subscription/portal — Redirect to Stripe Customer Portal
# ---------------------------------------------------------------------------
@router.get("/portal")
async def subscription_portal(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(f"{PREFIX}/login", status_code=302)

    if not _stripe_configured():
        raise HTTPException(status_code=503, detail="Stripe is not configured")

    _init_stripe()
    org = _get_org(request)

    customer_id = org.get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer linked to this organization")

    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{settings.BASE_URL}{PREFIX}/subscription",
        )
        return RedirectResponse(portal_session.url, status_code=303)
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
