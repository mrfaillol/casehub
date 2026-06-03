"""
CaseHub - Deadline Calculator Routes
Calculate and display case deadlines
"""
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date
import logging

logger = logging.getLogger(__name__)

from models import get_db, Case
from auth import get_current_user
from models.tenant import tenant_query
from i18n import get_translations
from services.deadline import DeadlineCalculator, PROCESSING_TIMES
from config import settings

PREFIX = settings.PREFIX

router = APIRouter(prefix="/deadlines", tags=["deadlines"])
templates = Jinja2Templates(directory="templates")


def get_context(request: Request, db: Session, **kwargs):
    """Build template context."""
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
async def deadlines_overview(request: Request, days: int = 30, db: Session = Depends(get_db)):
    """View all upcoming deadlines."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    try:
        calculator = DeadlineCalculator(db)
        upcoming = calculator.get_upcoming_deadlines(days)
    except Exception as e:
        db.rollback()
        upcoming = []
    
    # Group by urgency
    critical = [d for d in upcoming if d.get("critical")]
    urgent = [d for d in upcoming if d.get("urgent") and not d.get("critical")]
    normal = [d for d in upcoming if not d.get("urgent")]

    return templates.TemplateResponse("app/deadlines/overview.html", {
        **get_context(request, db),
        "critical": critical,
        "urgent": urgent,
        "normal": normal,
        "days": days,
        "total": len(upcoming)
    })


@router.get("/case/{case_id}", response_class=HTMLResponse)
async def case_deadlines(request: Request, case_id: int, db: Session = Depends(get_db)):
    """View deadlines for a specific case."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    try:
        case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error")

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    try:
        calculator = DeadlineCalculator(db)
        deadlines = calculator.calculate_deadlines(case_id)
        stages = calculator.get_stage_estimates(case.visa_type, case.status)
    except Exception as e:
        db.rollback()
        deadlines = []
        stages = []

    return templates.TemplateResponse("deadlines/case.html", {
        **get_context(request, db),
        "case": case,
        "deadlines": deadlines,
        "stages": stages
    })


@router.get("/calculator", response_class=HTMLResponse)
async def deadline_calculator(request: Request, db: Session = Depends(get_db)):
    """Interactive deadline calculator."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    visa_types = []
    for code, config in PROCESSING_TIMES.items():
        visa_types.append({
            "code": code,
            "name": config["name"],
            "premium": config.get("premium_available", False),
        })

    return templates.TemplateResponse("app/deadlines/calculator.html", {
        **get_context(request, db),
        "visa_types": visa_types,
        "processing_times": PROCESSING_TIMES
    })


@router.post("/calculate")
async def calculate_deadline(
    request: Request,
    db: Session = Depends(get_db)
):
    """Calculate deadline based on visa type and dates."""
    data = await request.json()
    visa_type = data.get("visa_type")
    filing_date = data.get("filing_date")
    premium = data.get("premium", False)

    if visa_type not in PROCESSING_TIMES:
        return JSONResponse({"error": "Invalid visa type"}, status_code=400)

    times = PROCESSING_TIMES[visa_type]
    if premium and times.get("premium"):
        days_min = times["premium"]
        days_max = times["premium"]
    else:
        days_min = times["regular_min"]
        days_max = times["regular_max"]

    from datetime import datetime, timedelta
    try:
        start = datetime.strptime(filing_date, "%Y-%m-%d")
    except Exception as e:
        logger.error("Failed to parse filing_date '%s': %s", filing_date, e)
        start = datetime.now()

    return JSONResponse({
        "visa_type": visa_type,
        "filing_date": filing_date,
        "premium": premium,
        "estimated_min": (start + timedelta(days=days_min)).strftime("%Y-%m-%d"),
        "estimated_max": (start + timedelta(days=days_max)).strftime("%Y-%m-%d"),
        "days_min": days_min,
        "days_max": days_max
    })


@router.get("/api/stages/{visa_type}")
async def get_stages_api(request: Request, visa_type: str, db: Session = Depends(get_db)):
    """Return processing stages for a visa type."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    if visa_type not in PROCESSING_TIMES:
        return JSONResponse({"error": "Invalid visa type"}, status_code=400)

    calculator = DeadlineCalculator(db)
    stages = calculator.get_stage_estimates(visa_type)
    return JSONResponse(stages)


@router.get("/api/estimate")
async def estimate_api(
    request: Request,
    visa_type: str = "",
    premium: str = "false",
    db: Session = Depends(get_db)
):
    """Estimate case completion timeline."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    if visa_type not in PROCESSING_TIMES:
        return JSONResponse({"error": "Invalid visa type"}, status_code=400)

    calculator = DeadlineCalculator(db)
    is_premium = premium.lower() == "true"
    result = calculator.estimate_completion(visa_type, premium=is_premium)
    return JSONResponse(result)
