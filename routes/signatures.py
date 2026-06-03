"""
CaseHub - Electronic Signature Routes
Manage signature capture, storage, and application.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request, Form, HTTPException, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from sqlalchemy import text

from models import get_db, User
from auth import get_current_user
from services.signature_service import signature_service, CREATE_SIGNATURES_TABLE

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/signatures", tags=["signatures"])
# templates = Jinja2Templates(directory="templates")  # Using shared instance from template_config.py


def ensure_tables(db: Session):
    """Ensure signature tables exist."""
    try:
        db.execute(text(CREATE_SIGNATURES_TABLE))
        db.commit()
    except Exception as e:
        db.rollback()


@router.get("", response_class=HTMLResponse)
async def signatures_page(request: Request, db: Session = Depends(get_db)):
    """Signature management page."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    ensure_tables(db)

    # Get user's signatures
    try:
        result = db.execute(text("""
            SELECT id, name, type, filepath, is_default, created_at
            FROM signatures
            WHERE user_id = :user_id
            ORDER BY is_default DESC, created_at DESC
        """), {"user_id": user.id})
        signatures = result.fetchall()
    except Exception:
        signatures = []

    return templates.TemplateResponse("app/signatures/manage.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX,
        "signatures": signatures
    })


@router.get("/capture", response_class=HTMLResponse)
async def capture_signature(request: Request, db: Session = Depends(get_db)):
    """Signature capture page (canvas)."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    return templates.TemplateResponse("app/signatures/capture.html", {
        "request": request,
        "user": user,
        "PREFIX": PREFIX
    })


@router.post("/save-drawn")
async def save_drawn_signature(
    request: Request,
    signature_data: str = Form(...),
    name: str = Form(None),
    set_default: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Save a drawn signature."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ensure_tables(db)

    # Get client info for audit
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    # Save the signature
    result = signature_service.save_drawn_signature(user.id, signature_data, name)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to save signature"))

    # If setting as default, unset others first
    if set_default:
        try:
            db.execute(text("UPDATE signatures SET is_default = false WHERE user_id = :uid"), {"uid": user.id})
        except Exception:
            pass

    # Store in database
    try:
        db.execute(text("""
            INSERT INTO signatures (user_id, name, type, filepath, checksum, is_default, ip_address, user_agent)
            VALUES (:uid, :name, 'drawn', :filepath, :checksum, :is_default, :ip, :ua)
        """), {
            "uid": user.id,
            "name": name or "My Signature",
            "filepath": result["filepath"],
            "checksum": result["checksum"],
            "is_default": set_default,
            "ip": ip_address,
            "ua": user_agent
        })
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    return RedirectResponse(url=f"{PREFIX}/signatures?saved=drawn", status_code=302)


@router.post("/save-upload")
async def save_uploaded_signature(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(None),
    set_default: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Save an uploaded signature image."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ensure_tables(db)

    # Read file
    file_data = await file.read()

    # Get client info for audit
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    # Save the signature
    result = signature_service.save_uploaded_signature(user.id, file_data, file.filename, name)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to save signature"))

    # If setting as default, unset others first
    if set_default:
        try:
            db.execute(text("UPDATE signatures SET is_default = false WHERE user_id = :uid"), {"uid": user.id})
        except Exception:
            pass

    # Store in database
    try:
        db.execute(text("""
            INSERT INTO signatures (user_id, name, type, filepath, checksum, is_default, ip_address, user_agent)
            VALUES (:uid, :name, 'uploaded', :filepath, :checksum, :is_default, :ip, :ua)
        """), {
            "uid": user.id,
            "name": name or "Uploaded Signature",
            "filepath": result["filepath"],
            "checksum": result["checksum"],
            "is_default": set_default,
            "ip": ip_address,
            "ua": user_agent
        })
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    return RedirectResponse(url=f"{PREFIX}/signatures?saved=upload", status_code=302)


@router.post("/save-typed")
async def save_typed_signature(
    request: Request,
    text: str = Form(...),
    font_style: str = Form("cursive"),
    name: str = Form(None),
    set_default: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Save a typed signature."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    ensure_tables(db)

    # Get client info for audit
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    # Generate the signature
    result = signature_service.generate_typed_signature(user.id, text, font_style, name)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to generate signature"))

    # If setting as default, unset others first
    if set_default:
        try:
            db.execute(text("UPDATE signatures SET is_default = false WHERE user_id = :uid"), {"uid": user.id})
        except Exception:
            pass

    # Store in database
    try:
        db.execute(text("""
            INSERT INTO signatures (user_id, name, type, filepath, checksum, is_default, typed_text, font_style, ip_address, user_agent)
            VALUES (:uid, :name, 'typed', :filepath, :checksum, :is_default, :typed, :font, :ip, :ua)
        """), {
            "uid": user.id,
            "name": name or "Typed Signature",
            "filepath": result["filepath"],
            "checksum": result["checksum"],
            "is_default": set_default,
            "typed": text,
            "font": font_style,
            "ip": ip_address,
            "ua": user_agent
        })
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    return RedirectResponse(url=f"{PREFIX}/signatures?saved=typed", status_code=302)


@router.get("/view/{signature_id}")
async def view_signature(request: Request, signature_id: int, db: Session = Depends(get_db)):
    """View a signature image."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        result = db.execute(text("""
            SELECT filepath FROM signatures WHERE id = :id AND user_id = :uid
        """), {"id": signature_id, "uid": user.id})
        row = result.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Signature not found")

        return FileResponse(row.filepath)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/delete/{signature_id}")
async def delete_signature(request: Request, signature_id: int, db: Session = Depends(get_db)):
    """Delete a signature."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        # Get filepath before deleting
        result = db.execute(text("""
            SELECT filepath FROM signatures WHERE id = :id AND user_id = :uid
        """), {"id": signature_id, "uid": user.id})
        row = result.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Signature not found")

        # Delete file
        signature_service.delete_signature(row.filepath)

        # Delete from database
        db.execute(text("DELETE FROM signatures WHERE id = :id"), {"id": signature_id})
        db.commit()

        return RedirectResponse(url=f"{PREFIX}/signatures?deleted=true", status_code=302)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/set-default/{signature_id}")
async def set_default_signature(request: Request, signature_id: int, db: Session = Depends(get_db)):
    """Set a signature as default."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        # Unset all defaults for this user
        db.execute(text("UPDATE signatures SET is_default = false WHERE user_id = :uid"), {"uid": user.id})

        # Set this one as default
        db.execute(text("UPDATE signatures SET is_default = true WHERE id = :id AND user_id = :uid"),
                   {"id": signature_id, "uid": user.id})
        db.commit()

        return RedirectResponse(url=f"{PREFIX}/signatures", status_code=302)

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/default")
async def get_default_signature(request: Request, db: Session = Depends(get_db)):
    """API: Get user's default signature as base64."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})

    try:
        result = db.execute(text("""
            SELECT id, filepath FROM signatures
            WHERE user_id = :uid AND is_default = true
            LIMIT 1
        """), {"uid": user.id})
        row = result.fetchone()

        if not row:
            return JSONResponse(content={"has_signature": False})

        base64_data = signature_service.get_signature_as_base64(row.filepath)

        return JSONResponse(content={
            "has_signature": True,
            "signature_id": row.id,
            "image_data": base64_data
        })

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
