"""
CaseHub - Enhanced Process Steps Routes
Workflow management for immigration cases with target dates, reminders, and visual progress
"""
from datetime import datetime, timedelta
from typing import Optional
import json

from core.form_utils import form_int, form_float
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX, inject_org_context
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, Case
from auth import get_current_user
from models.tenant import tenant_query
from i18n import get_translations

router = APIRouter(prefix="/processes", tags=["processes"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py
# PREFIX = "/casehub"  # Imported from template_config.py

def get_context(request: Request, db: Session, **kwargs):
    lang = request.cookies.get("lang", "pt-BR")
    t = get_translations(lang)
    user = get_current_user(request, db)
    product_state = getattr(getattr(request, "app", None), "state", None)
    product = getattr(product_state, "product", "lite") if product_state else "lite"
    return {
        "request": request,
        "PREFIX": PREFIX,
        "lang": lang,
        "t": t,
        "user": user,
        "product": product,
        **inject_org_context(request, user=user),
        **kwargs,
    }

# ==================== PROCESS TEMPLATES ====================

@router.get("", response_class=HTMLResponse)
async def list_processes(request: Request, db: Session = Depends(get_db)):
    """List all process templates"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    try:
        processes = db.execute(text("""
            SELECT p.*,
                   (SELECT COUNT(*) FROM process_steps WHERE process_id = p.id) as step_count,
                   (SELECT COUNT(*) FROM case_process_tracking WHERE process_id = p.id) as cases_using
            FROM case_processes p
            WHERE p.org_id = :org_id
            ORDER BY p.name
        """), {"org_id": request.state.org_id}).fetchall()
    except Exception:
        db.rollback()
        processes = []

    return templates.TemplateResponse("app/processes/list.html", get_context(request, db, processes=processes))

@router.get("/new", response_class=HTMLResponse)
async def new_process_form(request: Request, db: Session = Depends(get_db)):
    """Show form to create new process template"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    return templates.TemplateResponse("app/processes/form.html", get_context(request, db, process=None))

@router.post("/new")
async def create_process(
    request: Request,
    name: str = Form(...),
    description: str = Form(None),
    area_of_practice: str = Form(None),
    visa_types: str = Form(None),
    estimated_days: str = Form(None),
    db: Session = Depends(get_db)
):
    """Create a new process template"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Convert form strings to proper types
    estimated_days = form_int(estimated_days)

    visa_types_json = json.dumps(visa_types.split(",")) if visa_types else None

    db.execute(text("""
        INSERT INTO case_processes (name, description, area_of_practice, visa_types, estimated_days, org_id)
        VALUES (:name, :description, :area_of_practice, :visa_types, :estimated_days, :org_id)
    """), {
        "name": name,
        "description": description,
        "area_of_practice": area_of_practice,
        "visa_types": visa_types_json,
        "estimated_days": estimated_days,
        "org_id": request.state.org_id
    })
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/processes", status_code=302)

@router.get("/{process_id}", response_class=HTMLResponse)
async def view_process(process_id: int, request: Request, db: Session = Depends(get_db)):
    """View a process template and its steps"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    process = db.execute(text("""
        SELECT * FROM case_processes WHERE id = :id AND org_id = :org_id
    """), {"id": process_id, "org_id": request.state.org_id}).fetchone()

    if not process:
        raise HTTPException(status_code=404, detail="Process not found")

    steps = db.execute(text("""
        SELECT * FROM process_steps
        WHERE process_id = :process_id
        ORDER BY step_number
    """), {"process_id": process_id}).fetchall()

    return templates.TemplateResponse("app/processes/detail.html", get_context(request, db, process=process, steps=steps))

@router.get("/{process_id}/edit", response_class=HTMLResponse)
async def edit_process_form(process_id: int, request: Request, db: Session = Depends(get_db)):
    """Show form to edit process template"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    process = db.execute(text("""
        SELECT * FROM case_processes WHERE id = :id AND org_id = :org_id
    """), {"id": process_id, "org_id": request.state.org_id}).fetchone()

    if not process:
        raise HTTPException(status_code=404, detail="Process not found")

    return templates.TemplateResponse("app/processes/form.html", get_context(request, db, process=process))

@router.post("/{process_id}/edit")
async def update_process(
    process_id: int,
    request: Request,
    name: str = Form(...),
    description: str = Form(None),
    area_of_practice: str = Form(None),
    visa_types: str = Form(None),
    estimated_days: str = Form(None),
    enabled: bool = Form(True),
    db: Session = Depends(get_db)
):
    """Update a process template"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Convert form strings to proper types
    estimated_days = form_int(estimated_days)

    visa_types_json = json.dumps(visa_types.split(",")) if visa_types else None

    db.execute(text("""
        UPDATE case_processes
        SET name = :name, description = :description, area_of_practice = :area_of_practice,
            visa_types = :visa_types, estimated_days = :estimated_days, enabled = :enabled,
            updated_at = NOW()
        WHERE id = :id AND org_id = :org_id
    """), {
        "id": process_id,
        "org_id": request.state.org_id,
        "name": name,
        "description": description,
        "area_of_practice": area_of_practice,
        "visa_types": visa_types_json,
        "estimated_days": estimated_days,
        "enabled": enabled
    })
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/processes/{process_id}", status_code=302)

@router.post("/{process_id}/delete")
async def delete_process(process_id: int, request: Request, db: Session = Depends(get_db)):
    """Delete a process template"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    db.execute(text("DELETE FROM case_processes WHERE id = :id AND org_id = :org_id"), {"id": process_id, "org_id": request.state.org_id})
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/processes", status_code=302)

# ==================== PROCESS STEPS ====================

@router.post("/{process_id}/steps/add")
async def add_step(
    process_id: int,
    request: Request,
    name: str = Form(...),
    description: str = Form(None),
    estimated_days: str = Form(None),
    is_milestone: bool = Form(False),
    auto_start_next: bool = Form(True),
    email_on_complete: bool = Form(False),
    required_documents: str = Form(None),
    db: Session = Depends(get_db)
):
    """Add a step to a process"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Convert form strings to proper types
    estimated_days = form_int(estimated_days)

    # Get next step number
    result = db.execute(text("""
        SELECT COALESCE(MAX(step_number), 0) + 1 as next_num
        FROM process_steps WHERE process_id = :process_id
    """), {"process_id": process_id}).fetchone()
    next_num = result.next_num

    db.execute(text("""
        INSERT INTO process_steps (process_id, step_number, name, description, estimated_days, 
                                   is_milestone, auto_start_next, email_on_complete, required_documents)
        VALUES (:process_id, :step_number, :name, :description, :estimated_days, 
                :is_milestone, :auto_start_next, :email_on_complete, :required_documents)
    """), {
        "process_id": process_id,
        "step_number": next_num,
        "name": name,
        "description": description,
        "estimated_days": estimated_days,
        "is_milestone": is_milestone,
        "auto_start_next": auto_start_next,
        "email_on_complete": email_on_complete,
        "required_documents": required_documents
    })
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/processes/{process_id}", status_code=302)

@router.post("/{process_id}/steps/{step_id}/delete")
async def delete_step(process_id: int, step_id: int, request: Request, db: Session = Depends(get_db)):
    """Delete a step from a process"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    db.execute(text("DELETE FROM process_steps WHERE id = :id"), {"id": step_id})
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/processes/{process_id}", status_code=302)

@router.post("/{process_id}/steps/reorder")
async def reorder_steps(
    process_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Reorder steps via drag-and-drop (AJAX)"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    try:
        data = await request.json()
        step_order = data.get("step_order", [])
        
        for i, step_id in enumerate(step_order):
            db.execute(text("""
                UPDATE process_steps SET step_number = :num WHERE id = :id AND process_id = :process_id
            """), {"num": i + 1, "id": step_id, "process_id": process_id})
        
        db.commit()
        return JSONResponse({"success": True})
    except Exception as e:
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)

# ==================== CASE PROCESS TRACKING ====================

@router.post("/case/{case_id}/assign")
async def assign_process_to_case(
    case_id: int,
    request: Request,
    process_id: int = Form(...),
    start_date: str = Form(None),
    db: Session = Depends(get_db)
):
    """Assign a process template to a case with calculated target dates"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Parse start date or use today
    if start_date:
        base_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    else:
        base_date = datetime.now().date()

    # Get first step of process
    first_step = db.execute(text("""
        SELECT id FROM process_steps WHERE process_id = :process_id ORDER BY step_number LIMIT 1
    """), {"process_id": process_id}).fetchone()

    # Create tracking record
    db.execute(text("""
        INSERT INTO case_process_tracking (case_id, process_id, current_step_id)
        VALUES (:case_id, :process_id, :current_step_id)
        ON CONFLICT DO NOTHING
    """), {
        "case_id": case_id,
        "process_id": process_id,
        "current_step_id": first_step.id if first_step else None
    })

    # Create step progress records for all steps with calculated target dates
    steps = db.execute(text("""
        SELECT id, estimated_days FROM process_steps WHERE process_id = :process_id ORDER BY step_number
    """), {"process_id": process_id}).fetchall()

    cumulative_days = 0
    for i, step in enumerate(steps):
        status = "in_progress" if i == 0 else "pending"
        started_at = datetime.now() if i == 0 else None
        
        # Calculate target date based on cumulative estimated days
        step_days = step.estimated_days or 7  # Default 7 days if not specified
        cumulative_days += step_days
        target_date = base_date + timedelta(days=cumulative_days)
        
        db.execute(text("""
            INSERT INTO case_step_progress (case_id, step_id, status, started_at, target_date)
            VALUES (:case_id, :step_id, :status, :started_at, :target_date)
            ON CONFLICT DO NOTHING
        """), {
            "case_id": case_id,
            "step_id": step.id,
            "status": status,
            "started_at": started_at,
            "target_date": target_date
        })

    db.commit()

    return RedirectResponse(url=f"{PREFIX}/processes/case/{case_id}/progress", status_code=302)

@router.get("/case/{case_id}/progress", response_class=HTMLResponse)
async def view_case_progress(case_id: int, request: Request, db: Session = Depends(get_db)):
    """View enhanced process progress for a case with visual timeline"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Get process tracking
    tracking = db.execute(text("""
        SELECT cpt.*, cp.name as process_name, ps.name as current_step_name, ps.step_number as current_step_number
        FROM case_process_tracking cpt
        JOIN case_processes cp ON cp.id = cpt.process_id
        LEFT JOIN process_steps ps ON ps.id = cpt.current_step_id
        WHERE cpt.case_id = :case_id
    """), {"case_id": case_id}).fetchone()

    # Get all step progress with enhanced info
    step_progress = []
    total_steps = 0
    completed_steps = 0
    if tracking:
        step_progress = db.execute(text("""
            SELECT csp.*, ps.name as step_name, ps.step_number, ps.is_milestone,
                   ps.estimated_days, ps.required_documents, ps.auto_start_next,
                   u.name as completed_by_name, ua.name as assigned_to_name,
                   CASE 
                       WHEN csp.status = 'completed' THEN 'completed'
                       WHEN csp.target_date < CURRENT_DATE AND csp.status != 'completed' THEN 'overdue'
                       WHEN csp.target_date <= CURRENT_DATE + INTERVAL '3 days' AND csp.status != 'completed' THEN 'due_soon'
                       ELSE csp.status
                   END as display_status
            FROM case_step_progress csp
            JOIN process_steps ps ON ps.id = csp.step_id
            LEFT JOIN users u ON u.id = csp.completed_by
            LEFT JOIN users ua ON ua.id = csp.assigned_to
            WHERE csp.case_id = :case_id
            ORDER BY ps.step_number
        """), {"case_id": case_id}).fetchall()
        
        total_steps = len(step_progress)
        completed_steps = sum(1 for s in step_progress if s.status == 'completed')

    # Calculate progress percentage
    progress_percent = (completed_steps / total_steps * 100) if total_steps > 0 else 0

    # Get all available processes for assignment
    all_processes = db.execute(text("""
        SELECT * FROM case_processes WHERE enabled = true AND org_id = :org_id ORDER BY name
    """), {"org_id": request.state.org_id}).fetchall()

    # Get all users for assignment dropdown
    all_users = db.execute(text("""
        SELECT id, name FROM users WHERE enabled = true AND org_id = :org_id ORDER BY name
    """), {"org_id": request.state.org_id}).fetchall()

    return templates.TemplateResponse("app/processes/case_progress.html", get_context(
        request, db,
        case=case,
        tracking=tracking,
        step_progress=step_progress,
        all_processes=all_processes,
        all_users=all_users,
        progress_percent=progress_percent,
        total_steps=total_steps,
        completed_steps=completed_steps
    ))

@router.post("/case/{case_id}/step/{step_id}/complete")
async def complete_step(
    case_id: int,
    step_id: int,
    request: Request,
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Mark a step as completed and auto-start next step"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Update current step as completed
    db.execute(text("""
        UPDATE case_step_progress
        SET status = 'completed', completed_at = NOW(), completed_by = :user_id, notes = :notes
        WHERE case_id = :case_id AND step_id = :step_id
    """), {"case_id": case_id, "step_id": step_id, "user_id": user.id, "notes": notes})

    # Check if step has auto_start_next enabled
    current_step = db.execute(text("""
        SELECT ps.auto_start_next, ps.email_on_complete
        FROM process_steps ps WHERE ps.id = :step_id
    """), {"step_id": step_id}).fetchone()

    # Get next step
    next_step = db.execute(text("""
        SELECT ps2.id, ps2.estimated_days
        FROM process_steps ps1
        JOIN process_steps ps2 ON ps2.process_id = ps1.process_id AND ps2.step_number = ps1.step_number + 1
        WHERE ps1.id = :step_id
    """), {"step_id": step_id}).fetchone()

    if next_step and (current_step is None or current_step.auto_start_next):
        # Calculate new target date for next step
        next_target = datetime.now().date() + timedelta(days=next_step.estimated_days or 7)
        
        # Update next step as in_progress
        db.execute(text("""
            UPDATE case_step_progress
            SET status = 'in_progress', started_at = NOW(), target_date = :target_date
            WHERE case_id = :case_id AND step_id = :step_id
        """), {"case_id": case_id, "step_id": next_step.id, "target_date": next_target})

        # Update tracking
        db.execute(text("""
            UPDATE case_process_tracking
            SET current_step_id = :step_id
            WHERE case_id = :case_id
        """), {"case_id": case_id, "step_id": next_step.id})
    elif not next_step:
        # No more steps - mark process as completed
        db.execute(text("""
            UPDATE case_process_tracking
            SET completed_at = NOW()
            WHERE case_id = :case_id
        """), {"case_id": case_id})

    db.commit()

    return RedirectResponse(url=f"{PREFIX}/processes/case/{case_id}/progress", status_code=302)

@router.post("/case/{case_id}/step/{step_id}/skip")
async def skip_step(
    case_id: int,
    step_id: int,
    request: Request,
    notes: str = Form(None),
    db: Session = Depends(get_db)
):
    """Skip a step"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    db.execute(text("""
        UPDATE case_step_progress
        SET status = 'skipped', completed_at = NOW(), completed_by = :user_id, notes = :notes
        WHERE case_id = :case_id AND step_id = :step_id
    """), {"case_id": case_id, "step_id": step_id, "user_id": user.id, "notes": notes})
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/processes/case/{case_id}/progress", status_code=302)

# ==================== NEW: TARGET DATES & ASSIGNMENTS ====================

@router.post("/case/{case_id}/step/{step_id}/set-target")
async def set_step_target_date(
    case_id: int,
    step_id: int,
    request: Request,
    target_date: str = Form(...),
    db: Session = Depends(get_db)
):
    """Set or update target date for a step"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    db.execute(text("""
        UPDATE case_step_progress
        SET target_date = :target_date
        WHERE case_id = :case_id AND step_id = :step_id
    """), {"case_id": case_id, "step_id": step_id, "target_date": target_date})
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/processes/case/{case_id}/progress", status_code=302)

@router.post("/case/{case_id}/step/{step_id}/assign")
async def assign_step_to_user(
    case_id: int,
    step_id: int,
    request: Request,
    assigned_to: int = Form(...),
    db: Session = Depends(get_db)
):
    """Assign a step to a caseworker"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    db.execute(text("""
        UPDATE case_step_progress
        SET assigned_to = :assigned_to
        WHERE case_id = :case_id AND step_id = :step_id
    """), {"case_id": case_id, "step_id": step_id, "assigned_to": assigned_to})
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/processes/case/{case_id}/progress", status_code=302)

@router.post("/case/{case_id}/step/{step_id}/set-priority")
async def set_step_priority(
    case_id: int,
    step_id: int,
    request: Request,
    priority: str = Form(...),
    db: Session = Depends(get_db)
):
    """Set priority for a step"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    db.execute(text("""
        UPDATE case_step_progress
        SET priority = :priority
        WHERE case_id = :case_id AND step_id = :step_id
    """), {"case_id": case_id, "step_id": step_id, "priority": priority})
    db.commit()

    return RedirectResponse(url=f"{PREFIX}/processes/case/{case_id}/progress", status_code=302)

# ==================== API ENDPOINTS ====================

@router.get("/api/case/{case_id}/progress")
async def api_case_progress(case_id: int, request: Request, db: Session = Depends(get_db)):
    """API: Get case progress data for AJAX/charts"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    try:
        step_progress = db.execute(text("""
            SELECT csp.id, csp.status, csp.target_date, csp.started_at, csp.completed_at,
                   ps.name as step_name, ps.step_number, ps.is_milestone,
                   CASE 
                       WHEN csp.status = 'completed' THEN 100
                       WHEN csp.status = 'in_progress' THEN 50
                       ELSE 0
                   END as progress_value
            FROM case_step_progress csp
            JOIN process_steps ps ON ps.id = csp.step_id
            WHERE csp.case_id = :case_id
            ORDER BY ps.step_number
        """), {"case_id": case_id}).fetchall()

        steps = []
        for s in step_progress:
            steps.append({
                "id": s.id,
                "name": s.step_name,
                "number": s.step_number,
                "status": s.status,
                "is_milestone": s.is_milestone,
                "target_date": str(s.target_date) if s.target_date else None,
                "started_at": str(s.started_at) if s.started_at else None,
                "completed_at": str(s.completed_at) if s.completed_at else None,
                "progress": s.progress_value
            })

        total = len(steps)
        completed = sum(1 for s in steps if s["status"] == "completed")
        
        return JSONResponse({
            "steps": steps,
            "total_steps": total,
            "completed_steps": completed,
            "progress_percent": round(completed / total * 100, 1) if total > 0 else 0
        })
    except Exception as e:
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)

@router.get("/api/overdue-steps")
async def api_overdue_steps(request: Request, db: Session = Depends(get_db)):
    """API: Get all overdue steps across all cases"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    try:
        overdue = db.execute(text("""
            SELECT csp.id, csp.target_date, csp.case_id,
                   c.case_number, c.case_name,
                   ps.name as step_name, ps.step_number,
                   cl.first_name, cl.last_name,
                   u.name as assigned_to_name,
                   (CURRENT_DATE - csp.target_date) as days_overdue
            FROM case_step_progress csp
            JOIN process_steps ps ON ps.id = csp.step_id
            JOIN cases c ON c.id = csp.case_id
            JOIN clients cl ON cl.id = c.client_id
            LEFT JOIN users u ON u.id = csp.assigned_to
            WHERE csp.target_date < CURRENT_DATE
              AND csp.status NOT IN ('completed', 'skipped')
              AND c.org_id = :org_id
            ORDER BY csp.target_date ASC
        """), {"org_id": request.state.org_id}).fetchall()

        results = []
        for o in overdue:
            results.append({
                "step_id": o.id,
                "case_id": o.case_id,
                "case_number": o.case_number,
                "case_name": o.case_name,
                "client_name": f"{o.first_name} {o.last_name}",
                "step_name": o.step_name,
                "target_date": str(o.target_date),
                "days_overdue": o.days_overdue,
                "assigned_to": o.assigned_to_name
            })

        return JSONResponse({"overdue_steps": results, "count": len(results)})
    except Exception as e:
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)

@router.get("/api/upcoming-deadlines")
async def api_upcoming_deadlines(
    request: Request, 
    days: int = 7,
    db: Session = Depends(get_db)
):
    """API: Get steps with deadlines in the next N days"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    try:
        upcoming = db.execute(text("""
            SELECT csp.id, csp.target_date, csp.case_id, csp.status,
                   c.case_number, c.case_name,
                   ps.name as step_name, ps.step_number,
                   cl.first_name, cl.last_name,
                   u.name as assigned_to_name,
                   (csp.target_date - CURRENT_DATE) as days_until
            FROM case_step_progress csp
            JOIN process_steps ps ON ps.id = csp.step_id
            JOIN cases c ON c.id = csp.case_id
            JOIN clients cl ON cl.id = c.client_id
            LEFT JOIN users u ON u.id = csp.assigned_to
            WHERE csp.target_date BETWEEN CURRENT_DATE AND (CURRENT_DATE + :days * INTERVAL '1 day')
              AND csp.status NOT IN ('completed', 'skipped')
              AND c.org_id = :org_id
            ORDER BY csp.target_date ASC
        """), {"days": days, "org_id": request.state.org_id}).fetchall()

        results = []
        for u in upcoming:
            results.append({
                "step_id": u.id,
                "case_id": u.case_id,
                "case_number": u.case_number,
                "case_name": u.case_name,
                "client_name": f"{u.first_name} {u.last_name}",
                "step_name": u.step_name,
                "status": u.status,
                "target_date": str(u.target_date),
                "days_until": u.days_until,
                "assigned_to": u.assigned_to_name
            })

        return JSONResponse({"upcoming_deadlines": results, "count": len(results)})
    except Exception as e:
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=500)
