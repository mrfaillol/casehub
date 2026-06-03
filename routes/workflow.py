"""
CaseHub - Workflow Routes
Manage case workflows and status transitions
"""
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session

from models import get_db, Case
from auth import get_current_user
from models.tenant import tenant_query
from i18n import get_translations
from services.workflow import WorkflowService, get_all_visa_types, WORKFLOW_CONFIGS

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/workflow", tags=["workflow"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


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
async def workflow_overview(request: Request, db: Session = Depends(get_db)):
    """Workflow overview page showing all visa types and their workflows."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    visa_types = get_all_visa_types()
    
    return templates.TemplateResponse("app/workflow/overview.html", {
        **get_context(request, db),
        "visa_types": visa_types,
        "workflow_configs": WORKFLOW_CONFIGS
    })


@router.get("/case/{case_id}", response_class=HTMLResponse)
async def case_workflow(request: Request, case_id: int, db: Session = Depends(get_db)):
    """View workflow status for a specific case."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    service = WorkflowService(db)
    progress = service.get_workflow_progress(case_id)
    history = service.get_status_history(case_id)
    config = service.get_workflow_config(case.visa_type or "default")

    return templates.TemplateResponse("app/workflow/case.html", {
        **get_context(request, db),
        "case": case,
        "progress": progress,
        "history": history,
        "workflow_config": config
    })


@router.post("/case/{case_id}/transition")
async def transition_case(
    request: Request,
    case_id: int,
    new_status: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Transition a case to a new status."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = WorkflowService(db)
    result = service.transition_case(case_id, new_status, user.id, notes)
    
    if not result.get("success"):
        return JSONResponse(result, status_code=400)
    
    return JSONResponse(result)


@router.get("/api/case/{case_id}/allowed-transitions")
async def get_allowed_transitions(request: Request, case_id: int, db: Session = Depends(get_db)):
    """API: Get allowed status transitions for a case."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        return JSONResponse({"error": "Case not found"}, status_code=404)

    service = WorkflowService(db)
    allowed = service.get_allowed_transitions(case.visa_type, case.status)
    
    return JSONResponse({
        "case_id": case_id,
        "current_status": case.status,
        "visa_type": case.visa_type,
        "allowed_transitions": allowed
    })


@router.get("/api/case/{case_id}/progress")
async def get_case_progress(request: Request, case_id: int, db: Session = Depends(get_db)):
    """API: Get workflow progress for a case."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service = WorkflowService(db)
    progress = service.get_workflow_progress(case_id)
    
    return JSONResponse(progress)


@router.get("/api/visa-types")
async def get_visa_types(request: Request, db: Session = Depends(get_db)):
    """API: Get all visa types with their workflow configurations."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    return JSONResponse(get_all_visa_types())
