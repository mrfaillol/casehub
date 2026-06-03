"""
CaseHub - Data Import Routes
Import data from external sources like Cerenade
"""
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
# from fastapi.templating import Jinja2Templates  # Not needed - using template_config.py
from core.template_config import templates, PREFIX
from sqlalchemy.orm import Session
from typing import Optional
import json
import logging
import os

logger = logging.getLogger(__name__)

from models import get_db, Client, Case, Document
from auth import get_current_user
from models.tenant import tenant_query
from services.cerenade_import import CerenadeImportService

# PREFIX = "/casehub"  # Imported from template_config.py

router = APIRouter(prefix="/import", tags=["import"])
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


@router.get("", response_class=HTMLResponse)
async def import_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # For Lite product, redirect to the generic CSV/Excel import wizard
    product = getattr(getattr(request, "app", None), "state", None)
    if product and getattr(product, "product", None) == "lite":
        return RedirectResponse(url=f"{PREFIX}/import-br", status_code=302)

    # Get current stats
    client_count = tenant_query(db, Client, request.state.org_id).count()
    case_count = tenant_query(db, Case, request.state.org_id).count()
    doc_count = tenant_query(db, Document, request.state.org_id).count()

    return templates.TemplateResponse("app/import/index.html", get_context(
        request, db,
        client_count=client_count,
        case_count=case_count,
        doc_count=doc_count
    ))


@router.post("/cerenade")
async def import_from_cerenade(
    request: Request,
    import_type: str = Form("all"),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    service = CerenadeImportService()

    if import_type == "all":
        results = service.import_all_from_files(db)
    elif import_type == "clients":
        clients_data = service.load_json_file("clients.json")
        results = {"clients": service.import_clients_from_json(db, clients_data)}
    elif import_type == "cases":
        cases_data = service.load_json_file("cases.json")
        results = {"cases": service.import_cases_from_json(db, cases_data)}
    elif import_type == "documents":
        docs_data = service.load_json_file("documents.json")
        results = {"documents": service.import_documents_from_json(db, docs_data)}
    else:
        results = {"error": f"Unknown import type: {import_type}"}

    return templates.TemplateResponse("app/import/results.html", get_context(
        request, db,
        results=results,
        source="Cerenade Files"
    ))


@router.post("/json")
async def import_from_json(
    request: Request,
    data_type: str = Form(...),
    json_file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    # Read uploaded file
    content = await json_file.read()
    try:
        json_content = content.decode('utf-8')
    except Exception as e:
        logger.error("Failed to decode uploaded JSON file: %s", e)
        return templates.TemplateResponse("app/import/index.html", get_context(
            request, db,
            error="Could not read file. Please ensure it's a valid UTF-8 encoded JSON file."
        ))

    service = CerenadeImportService()
    result = service.import_from_uploaded_json(db, json_content, data_type)

    if "error" in result:
        return templates.TemplateResponse("app/import/index.html", get_context(
            request, db,
            error=result["error"]
        ))

    results = {data_type: result}

    return templates.TemplateResponse("app/import/results.html", get_context(
        request, db,
        results=results,
        source=f"JSON Upload ({json_file.filename})"
    ))


@router.post("/csv")
async def import_from_csv(
    request: Request,
    data_type: str = Form(...),
    csv_file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Import data from CSV file"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    import csv
    from io import StringIO

    # Read uploaded file
    content = await csv_file.read()
    try:
        csv_content = content.decode('utf-8')
    except Exception as e:
        logger.error("Failed to decode uploaded CSV file: %s", e)
        return templates.TemplateResponse("app/import/index.html", get_context(
            request, db,
            error="Could not read file. Please ensure it's a valid UTF-8 encoded CSV file."
        ))

    # Parse CSV to list of dicts
    reader = csv.DictReader(StringIO(csv_content))
    data = list(reader)

    if not data:
        return templates.TemplateResponse("app/import/index.html", get_context(
            request, db,
            error="CSV file is empty or has no data rows."
        ))

    service = CerenadeImportService()
    result = service.import_from_uploaded_json(db, json.dumps(data), data_type)

    if "error" in result:
        return templates.TemplateResponse("app/import/index.html", get_context(
            request, db,
            error=result["error"]
        ))

    results = {data_type: result}

    return templates.TemplateResponse("app/import/results.html", get_context(
        request, db,
        results=results,
        source=f"CSV Upload ({csv_file.filename})"
    ))


@router.get("/template/{data_type}")
async def download_template(data_type: str):
    """Download CSV template for import"""
    from fastapi.responses import StreamingResponse
    import io

    templates_data = {
        "clients": [
            "name,email,phone,dob,country,address,status,notes",
            "John Doe,john@example.com,+1234567890,01/15/1990,Brazil,123 Main St,Active,Example notes"
        ],
        "cases": [
            "client_name,case_number,receipt_number,visa_type,status,filed_date,case_value,notes",
            "John Doe,CASE-001,WAC2390123456,H-1B,Filed,01/15/2024,5000,Example case"
        ],
        "documents": [
            "client_name,case_number,name,type,status,expiration_date,notes",
            "John Doe,CASE-001,Passport,passport,received,12/31/2030,Valid passport"
        ]
    }

    if data_type not in templates_data:
        raise HTTPException(status_code=404, detail="Template not found")

    content = "\n".join(templates_data[data_type])
    output = io.StringIO(content)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={data_type}_template.csv"}
    )
