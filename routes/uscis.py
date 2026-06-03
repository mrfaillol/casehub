"""
USCIS Case Status Integration
Check and track case status from USCIS
"""
import httpx
import json
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, Case
from auth import get_current_user
from models.tenant import tenant_query

router = APIRouter(prefix="/uscis", tags=["uscis"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py
# templates.env.globals["PREFIX"] = "/casehub"  # Configured in template_config.py

# USCIS API endpoint for case status
USCIS_API_URL = "https://egov.uscis.gov/casestatus/mycasestatus.do"


async def check_uscis_status(receipt_number: str) -> dict:
    """
    Check case status from USCIS website.
    Returns dict with status_title, status_description, form_type
    """
    try:
        async with httpx.AsyncClient() as client:
            # USCIS uses a form POST to check status
            response = await client.post(
                USCIS_API_URL,
                data={
                    "appReceiptNum": receipt_number,
                    "caseStatusSearchBtn": "CHECK STATUS"
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                timeout=30.0,
                follow_redirects=True
            )
            
            if response.status_code != 200:
                return {"error": f"USCIS returned status {response.status_code}"}
            
            html = response.text
            
            # Parse the response HTML
            # Look for the status title
            title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            status_title = title_match.group(1).strip() if title_match else "Unknown"
            
            # Look for the status description
            desc_match = re.search(r'<div class="rows text-center">(.*?)</div>', html, re.DOTALL)
            if not desc_match:
                desc_match = re.search(r'<p class="(text-center|current-status-sec)"[^>]*>(.*?)</p>', html, re.DOTALL)
            
            status_description = ""
            if desc_match:
                # Clean up the HTML
                desc_html = desc_match.group(1) if len(desc_match.groups()) == 1 else desc_match.group(2)
                status_description = re.sub(r'<[^>]+>', '', desc_html).strip()
                status_description = re.sub(r'\s+', ' ', status_description)
            
            # Extract form type from the description or receipt number
            form_type = receipt_number[:3] if len(receipt_number) >= 3 else "Unknown"
            form_match = re.search(r'Form (I-\d+)', html)
            if form_match:
                form_type = form_match.group(1)
            
            return {
                "status_title": status_title,
                "status_description": status_description,
                "form_type": form_type,
                "receipt_number": receipt_number,
                "checked_at": datetime.now().isoformat()
            }
            
    except httpx.TimeoutException:
        return {"error": "USCIS request timed out"}
    except Exception as e:
        return {"error": str(e)}


@router.get("", response_class=HTMLResponse)
async def uscis_status_list(request: Request, db: Session = Depends(get_db)):
    """List all tracked USCIS cases"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(f"{PREFIX}/login", status_code=302)
    
    # Get all tracked cases
    tracked = db.execute(text("""
        SELECT us.*, c.case_name, c.visa_type
        FROM uscis_status_checks us
        LEFT JOIN cases c ON c.id = us.case_id
        ORDER BY us.last_checked DESC
    """)).fetchall()
    
    return templates.TemplateResponse("app/uscis/list.html", {
        "request": request,
        "user": user,
        "tracked_cases": tracked
    })


@router.get("/check/{case_id}", response_class=HTMLResponse)
async def uscis_check_case(
    request: Request,
    case_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Check USCIS status for a specific case"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(f"{PREFIX}/login", status_code=302)
    
    case = tenant_query(db, Case, request.state.org_id).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    if not case.receipt_number:
        return RedirectResponse(f"{PREFIX}/cases/{case_id}?error=no_receipt", status_code=302)
    
    # Check status
    result = await check_uscis_status(case.receipt_number)
    
    if "error" in result:
        return RedirectResponse(f"{PREFIX}/cases/{case_id}?error=uscis_error&msg={result['error']}", status_code=302)
    
    # Check if we have an existing record
    existing = db.execute(text("""
        SELECT id, status_title FROM uscis_status_checks 
        WHERE case_id = :case_id
    """), {"case_id": case_id}).fetchone()
    
    if existing:
        # Update existing record
        old_status = existing.status_title
        
        db.execute(text("""
            UPDATE uscis_status_checks
            SET status_title = :title,
                status_description = :desc,
                form_type = :form,
                last_checked = NOW(),
                check_count = check_count + 1,
                raw_response = :raw
            WHERE id = :id
        """), {
            "title": result["status_title"],
            "desc": result["status_description"],
            "form": result["form_type"],
            "raw": json.dumps(result),
            "id": existing.id
        })
        
        # If status changed, log to history
        if old_status != result["status_title"]:
            db.execute(text("""
                INSERT INTO uscis_check_history (status_check_id, status_title, status_description)
                VALUES (:id, :title, :desc)
            """), {
                "id": existing.id,
                "title": result["status_title"],
                "desc": result["status_description"]
            })
    else:
        # Create new record
        db.execute(text("""
            INSERT INTO uscis_status_checks (case_id, receipt_number, status_title, status_description, form_type, raw_response)
            VALUES (:case_id, :receipt, :title, :desc, :form, :raw)
        """), {
            "case_id": case_id,
            "receipt": case.receipt_number,
            "title": result["status_title"],
            "desc": result["status_description"],
            "form": result["form_type"],
            "raw": json.dumps(result)
        })
    
    db.commit()
    
    return RedirectResponse(f"{PREFIX}/cases/{case_id}?success=uscis_checked", status_code=302)


@router.post("/check-receipt")
async def check_receipt_directly(
    request: Request,
    receipt_number: str = Form(...),
    db: Session = Depends(get_db)
):
    """Check USCIS status by receipt number directly"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(f"{PREFIX}/login", status_code=302)
    
    # Clean up receipt number
    receipt_number = receipt_number.strip().upper()
    
    # Validate format (3 letters + 10 digits)
    if not re.match(r'^[A-Z]{3}\d{10}$', receipt_number):
        return RedirectResponse(f"{PREFIX}/uscis?error=invalid_receipt", status_code=302)
    
    result = await check_uscis_status(receipt_number)
    
    if "error" in result:
        return RedirectResponse(f"{PREFIX}/uscis?error=uscis_error&msg={result['error']}", status_code=302)
    
    # Store result (without case linkage)
    db.execute(text("""
        INSERT INTO uscis_status_checks (receipt_number, status_title, status_description, form_type, raw_response)
        VALUES (:receipt, :title, :desc, :form, :raw)
        ON CONFLICT DO NOTHING
    """), {
        "receipt": receipt_number,
        "title": result["status_title"],
        "desc": result["status_description"],
        "form": result["form_type"],
        "raw": json.dumps(result)
    })
    db.commit()
    
    return RedirectResponse(f"{PREFIX}/uscis?success=checked&receipt={receipt_number}", status_code=302)


@router.get("/history/{check_id}")
async def uscis_check_history(
    request: Request,
    check_id: int,
    db: Session = Depends(get_db)
):
    """Get status history for a tracked case"""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    history = db.execute(text("""
        SELECT * FROM uscis_check_history
        WHERE status_check_id = :id
        ORDER BY checked_at DESC
    """), {"id": check_id}).fetchall()
    
    return JSONResponse({
        "history": [{
            "status_title": h.status_title,
            "status_description": h.status_description,
            "checked_at": h.checked_at.isoformat() if h.checked_at else None
        } for h in history]
    })


@router.get("/api/status/{receipt_number}")
async def api_check_status(receipt_number: str, db: Session = Depends(get_db)):
    """API endpoint to check USCIS status"""
    # Clean up receipt number
    receipt_number = receipt_number.strip().upper()
    
    # Validate format
    if not re.match(r'^[A-Z]{3}\d{10}$', receipt_number):
        return JSONResponse({"error": "Invalid receipt number format"}, status_code=400)
    
    result = await check_uscis_status(receipt_number)
    return JSONResponse(result)
