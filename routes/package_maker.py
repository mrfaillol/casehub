"""
CaseHub - Package Maker Routes
Native package builder for USCIS immigration cases (Musheng Paradigm, Exhibits A-M).
Full feature parity: validation, cover page, page numbers, watermark, separators.
"""
from fastapi import APIRouter, Depends, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
import os
import json
import tempfile
import shutil
import logging

from models import get_db, Client, Case, Document, QuestionnaireResponse, QuestionnaireTemplate
from models.tenant import tenant_query
from auth import get_current_user
from core.request_utils import get_request_org_id
from middleware.features import require_feature
from config import settings

logger = logging.getLogger(__name__)

PREFIX = settings.PREFIX
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "output")

router = APIRouter(tags=["package-maker"])
templates = Jinja2Templates(directory="templates")


# Required exhibits for validation
REQUIRED_EXHIBITS = {"A", "B", "C", "D"}


class ValidateRequest(BaseModel):
    structure: list


@router.get("/package-maker", response_class=HTMLResponse)
async def package_maker_page(
    request: Request,
    case_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _feature=Depends(require_feature("package_builder")),
):
    """Render the Package Maker form page."""
    from fastapi.responses import RedirectResponse
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    from services.package_builder import EXHIBITS

    org_id = get_request_org_id(request)
    case = None
    client = None
    case_documents = []

    if case_id and org_id is not None:
        case = tenant_query(db, Case, org_id).filter(Case.id == case_id).first()
        if case:
            client = tenant_query(db, Client, org_id).filter(Client.id == case.client_id).first()
            case_documents = tenant_query(db, Document, org_id).filter(
                Document.case_id == case_id,
                Document.status != 'file_missing'
            ).order_by(Document.doc_type.asc()).all()

    exhibits = []
    for letter, info in EXHIBITS.items():
        exhibits.append({
            "letter": letter,
            "name": info["name"],
            "description": info["description"],
            "required": info["required"],
        })

    response = templates.TemplateResponse("app/package_maker/form.html", {
        "request": request, "user": user, "PREFIX": PREFIX,
        "case": case,
        "client": client,
        "exhibits": exhibits,
        "case_documents": case_documents,
    })
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


@router.get("/api/package/case-documents/{case_id}")
async def get_case_documents(
    request: Request,
    case_id: int,
    db: Session = Depends(get_db)
):
    """Get all documents for a case, grouped by exhibit for Package Maker.
    Uses read-only query, short-lived session (PostgreSQL lock safety).
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    from services.document_classifier import EXHIBIT_MAP

    org_id = get_request_org_id(request)
    if org_id is None:
        return JSONResponse({"error": "Case not found"}, status_code=404)

    case = tenant_query(db, Case, org_id).filter(Case.id == case_id).first()
    if not case:
        return JSONResponse({"error": "Case not found"}, status_code=404)

    client = tenant_query(db, Client, org_id).filter(Client.id == case.client_id).first()

    # Query documents — filter out file_missing status, read-only
    docs = tenant_query(db, Document, org_id).filter(
        Document.case_id == case_id,
        Document.status != 'file_missing'
    ).order_by(Document.doc_type.asc(), Document.name.asc()).all()

    documents = []
    by_exhibit = {}
    unassigned = []
    stats = {"total": 0, "with_exhibit": 0, "unassigned": 0}

    for doc in docs:
        # Resolve file path: storage_path -> local_path -> file_path
        resolved_path = None
        drive_only = False
        for path_attr in [doc.storage_path, doc.local_path, doc.file_path]:
            if path_attr and os.path.exists(path_attr):
                resolved_path = path_attr
                break

        if not resolved_path:
            if doc.drive_file_id or doc.drive_link:
                drive_only = True
            else:
                continue  # No file anywhere — skip entirely

        # Determine exhibit: use suggested_exhibit, fallback to EXHIBIT_MAP
        exhibit = doc.suggested_exhibit
        if not exhibit and doc.doc_type:
            exhibit = EXHIBIT_MAP.get(doc.doc_type)

        doc_data = {
            "id": doc.id,
            "name": doc.name,
            "doc_type": doc.doc_type,
            "suggested_exhibit": exhibit,
            "file_size": doc.file_size,
            "status": doc.status,
            "classification_confidence": doc.classification_confidence,
            "drive_only": drive_only,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "mime_type": doc.mime_type,
        }

        documents.append(doc_data)
        stats["total"] += 1

        if exhibit:
            stats["with_exhibit"] += 1
            by_exhibit.setdefault(exhibit, []).append(doc_data)
        else:
            stats["unassigned"] += 1
            unassigned.append(doc_data)

    return JSONResponse({
        "documents": documents,
        "by_exhibit": by_exhibit,
        "unassigned": unassigned,
        "stats": stats,
        "case_info": {
            "case_id": case.id,
            "case_type": case.visa_type,
            "client_name": f"{client.first_name} {client.last_name}" if client else None,
        }
    })


@router.patch("/api/package/classify-doc/{doc_id}")
async def classify_doc_manual(
    request: Request,
    doc_id: int,
    db: Session = Depends(get_db)
):
    """Manually classify a document's type and update exhibit assignment."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    from services.document_classifier import EXHIBIT_MAP, DOCUMENT_TYPES

    try:
        body = await request.json()
        new_doc_type = body.get("doc_type")
        if not new_doc_type or new_doc_type not in DOCUMENT_TYPES:
            return JSONResponse({"error": f"Invalid doc_type. Must be one of: {DOCUMENT_TYPES}"}, status_code=400)

        org_id = get_request_org_id(request)
        if org_id is None:
            return JSONResponse({"error": "Document not found"}, status_code=404)

        doc = tenant_query(db, Document, org_id).filter(Document.id == doc_id).first()
        if not doc:
            return JSONResponse({"error": "Document not found"}, status_code=404)

        doc.doc_type = new_doc_type
        doc.suggested_exhibit = EXHIBIT_MAP.get(new_doc_type)
        doc.classification_confidence = 1.0  # Manual = 100% confidence
        doc.llm_classified = False  # Mark as manually classified
        db.commit()

        return JSONResponse({
            "success": True,
            "doc_id": doc_id,
            "doc_type": new_doc_type,
            "suggested_exhibit": doc.suggested_exhibit,
        })
    except Exception as e:
        db.rollback()
        logger.error(f"Manual classify error: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/package/batch-classify/{case_id}")
async def batch_classify(
    request: Request,
    case_id: int,
    db: Session = Depends(get_db)
):
    """Run LLM classification on unclassified documents for a case."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    from services.document_classifier import EXHIBIT_MAP, classify_document

    org_id = get_request_org_id(request)
    if org_id is None:
        return JSONResponse({"error": "Case not found"}, status_code=404)

    # Confirm the case belongs to this tenant before touching its documents.
    case = tenant_query(db, Case, org_id).filter(Case.id == case_id).first()
    if not case:
        return JSONResponse({"error": "Case not found"}, status_code=404)

    docs = tenant_query(db, Document, org_id).filter(
        Document.case_id == case_id,
        Document.status != 'file_missing',
    ).filter(
        (Document.doc_type == None) | (Document.doc_type == "Other Document")  # noqa: E711
    ).all()

    classified = 0
    failed = 0
    results = []

    for doc in docs:
        try:
            result = await classify_document(doc.name, doc.ocr_text[:500] if doc.ocr_text else "")
            doc.doc_type = result["doc_type"]
            doc.suggested_exhibit = result.get("suggested_exhibit") or EXHIBIT_MAP.get(result["doc_type"])
            doc.classification_confidence = result["confidence"]
            doc.llm_classified = True
            classified += 1
            results.append({
                "doc_id": doc.id,
                "name": doc.name,
                "doc_type": result["doc_type"],
                "confidence": result["confidence"],
                "method": result["method"],
                "suggested_exhibit": doc.suggested_exhibit,
            })
        except Exception as e:
            failed += 1
            logger.error(f"Batch classify error for doc {doc.id}: {e}")
            results.append({"doc_id": doc.id, "name": doc.name, "error": str(e)})

    db.commit()

    return JSONResponse({
        "classified": classified,
        "failed": failed,
        "total": len(docs),
        "results": results,
    })


@router.get("/api/package/intake-data/{case_id}")
async def get_intake_data(
    request: Request,
    case_id: int,
    db: Session = Depends(get_db)
):
    """Get intake questionnaire responses for a case, for form auto-population."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    org_id = get_request_org_id(request)
    if org_id is None:
        return JSONResponse({"error": "Case not found"}, status_code=404)

    case = tenant_query(db, Case, org_id).filter(Case.id == case_id).first()
    if not case:
        return JSONResponse({"error": "Case not found"}, status_code=404)

    client = tenant_query(db, Client, org_id).filter(Client.id == case.client_id).first()

    from sqlalchemy import text as sql_text

    forms_data = []
    total_fields = 0
    filled_fields = 0

    # PRIMARY SOURCE: intake_responses table (Client Portal submissions).
    # Scoped by tenant: intake_packages has no org_id, so we JOIN clients and
    # filter clients.org_id. Prevents cross-tenant client_id collisions from
    # leaking another org's intake answers.
    intake_query = sql_text("""
        SELECT ii.questionnaire_id, ii.name, ir.response_data, ir.submitted_at, ir.id
        FROM intake_responses ir
        JOIN intake_items ii ON ii.id = ir.item_id
        JOIN intake_packages ip ON ip.id = ii.package_id
        JOIN clients c ON c.id = ip.client_id
        WHERE ip.client_id = :client_id AND c.org_id = :org_id
        ORDER BY ir.submitted_at DESC
    """)
    intake_rows = db.execute(intake_query, {"client_id": case.client_id, "org_id": org_id}).fetchall()

    seen_templates = set()
    for row in intake_rows:
        template_id = row[0]
        item_name = row[1]
        data = row[2] or {}
        submitted_at = row[3]
        response_id = row[4]

        if not data or not template_id:
            continue
        # Only keep most recent per template
        if template_id in seen_templates:
            continue
        seen_templates.add(template_id)

        # Try to get template name from DB
        template = db.query(QuestionnaireTemplate).filter(
            QuestionnaireTemplate.id == template_id
        ).first()

        field_count = len(data)
        non_empty = sum(1 for v in data.values() if v and str(v).strip())

        total_fields += field_count
        filled_fields += non_empty

        forms_data.append({
            "response_id": response_id,
            "template_id": template_id,
            "template_name": template.name if template else item_name or f"Template {template_id}",
            "status": "submitted",
            "submitted_at": submitted_at.isoformat() if submitted_at else None,
            "total_fields": field_count,
            "filled_fields": non_empty,
            "completion_pct": round(non_empty / field_count * 100) if field_count > 0 else 0,
            "data": data,
            "source": "intake_portal",
        })

    # FALLBACK: also check questionnaire_responses table
    qr_responses = db.query(QuestionnaireResponse).filter(
        QuestionnaireResponse.client_id == case.client_id
    ).order_by(QuestionnaireResponse.submitted_at.desc()).all()

    for resp in qr_responses:
        if resp.template_id in seen_templates:
            continue
        seen_templates.add(resp.template_id)

        template = db.query(QuestionnaireTemplate).filter(
            QuestionnaireTemplate.id == resp.template_id
        ).first()

        data = resp.responses_data or {}
        field_count = len(data)
        non_empty = sum(1 for v in data.values() if v and str(v).strip())

        total_fields += field_count
        filled_fields += non_empty

        forms_data.append({
            "response_id": resp.id,
            "template_id": resp.template_id,
            "template_name": template.name if template else f"Template {resp.template_id}",
            "status": resp.status,
            "submitted_at": resp.submitted_at.isoformat() if resp.submitted_at else None,
            "total_fields": field_count,
            "filled_fields": non_empty,
            "completion_pct": round(non_empty / field_count * 100) if field_count > 0 else 0,
            "data": data,
            "source": "casehub",
        })

    return JSONResponse({
        "case_id": case_id,
        "client_name": f"{client.first_name} {client.last_name}" if client else None,
        "forms": forms_data,
        "summary": {
            "total_forms": len(forms_data),
            "total_fields": total_fields,
            "filled_fields": filled_fields,
            "completion_pct": round(filled_fields / total_fields * 100) if total_fields > 0 else 0,
        }
    })


## ======== PHASE 3: FORM AUTO-FILL (GAME CHANGER) ========

@router.get("/api/package/available-forms")
async def list_available_forms(request: Request, db: Session = Depends(get_db)):
    """List forms that can be auto-filled with intake data."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    from services.form_filler import form_filler
    available = form_filler.get_available_forms()
    return JSONResponse({"forms": available})


@router.post("/api/package/generate-forms/{case_id}")
async def generate_filled_forms(
    request: Request,
    case_id: int,
    db: Session = Depends(get_db)
):
    """Generate auto-filled USCIS forms from intake questionnaire data.
    This is the core feature: client fills questionnaire once, forms auto-populate.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    org_id = get_request_org_id(request)
    if org_id is None:
        return JSONResponse({"error": "Case not found"}, status_code=404)

    case = tenant_query(db, Case, org_id).filter(Case.id == case_id).first()
    if not case:
        return JSONResponse({"error": "Case not found"}, status_code=404)

    client = tenant_query(db, Client, org_id).filter(Client.id == case.client_id).first()
    beneficiary_name = f"{client.first_name} {client.last_name}" if client else "Unknown"

    # Parse optional body for form selection
    try:
        body = await request.json()
    except Exception:
        body = {}

    requested_forms = body.get("forms")  # None = all forms for visa type
    visa_type = body.get("visa_type") or case.visa_type or "EB-2 NIW"

    from services.form_filler import form_filler, TEMPLATE_IDS
    from sqlalchemy import text as sql_text

    responses_by_template = {}
    common_info = {}

    # PRIMARY SOURCE: intake_responses table (where Client Portal data lives)
    # This is where clients actually submit their questionnaire answers.
    # Scoped by tenant via clients.org_id (intake_packages has no org_id).
    intake_query = sql_text("""
        SELECT ii.questionnaire_id, ir.response_data, ir.submitted_at
        FROM intake_responses ir
        JOIN intake_items ii ON ii.id = ir.item_id
        JOIN intake_packages ip ON ip.id = ii.package_id
        JOIN clients c ON c.id = ip.client_id
        WHERE ip.client_id = :client_id AND c.org_id = :org_id
        ORDER BY ir.submitted_at DESC
    """)
    intake_rows = db.execute(intake_query, {"client_id": case.client_id, "org_id": org_id}).fetchall()

    for row in intake_rows:
        template_id = row[0]  # questionnaire_id
        data = row[1] or {}   # response_data (JSONB)
        if not data or not template_id:
            continue
        # Only keep the most recent response per template
        if template_id not in responses_by_template:
            responses_by_template[template_id] = data
        # Extract COMMON-INFO
        if template_id == TEMPLATE_IDS.get("COMMON-INFO"):
            common_info = data

    # FALLBACK: also check questionnaire_responses table (CaseHub admin submissions)
    qr_responses = db.query(QuestionnaireResponse).filter(
        QuestionnaireResponse.client_id == case.client_id
    ).order_by(QuestionnaireResponse.submitted_at.desc()).all()

    for resp in qr_responses:
        data = resp.responses_data or {}
        if not data:
            continue
        tid = resp.template_id
        if tid not in responses_by_template:
            responses_by_template[tid] = data
        if tid == TEMPLATE_IDS.get("COMMON-INFO") and not common_info:
            common_info = data

    logger.info(f"Found intake data for client {case.client_id}: {len(responses_by_template)} templates with data")
    # Generate filled forms
    if requested_forms:
        # Fill specific requested forms
        results = []
        for form_name in requested_forms:
            template_id = TEMPLATE_IDS.get(form_name)
            form_data = responses_by_template.get(template_id, {}) if template_id else {}
            output_path, stats = form_filler.fill_form(
                form_name=form_name,
                response_data=form_data,
                common_info=common_info,
                beneficiary_name=beneficiary_name,
            )
            results.append({
                "form_name": form_name,
                "output_path": output_path,
                "filename": os.path.basename(output_path) if output_path else None,
                "download_url": f"{PREFIX}/api/package/download/{os.path.basename(output_path)}" if output_path else None,
                **stats,
            })
    else:
        # Fill all forms for the visa type
        raw_results = form_filler.fill_all_forms(
            visa_type=visa_type,
            responses_by_template=responses_by_template,
            common_info=common_info,
            beneficiary_name=beneficiary_name,
        )
        results = []
        for r in raw_results:
            r["download_url"] = f"{PREFIX}/api/package/download/{r['filename']}" if r.get("filename") else None
            results.append(r)

    successful = sum(1 for r in results if r.get("success"))

    return JSONResponse({
        "case_id": case_id,
        "visa_type": visa_type,
        "beneficiary": beneficiary_name,
        "forms_generated": successful,
        "forms_total": len(results),
        "results": results,
    })


## ======== PHASE 4: VISA-TYPE PRESETS & TEMPLATES ========

VISA_PRESETS = {
    "EB-2 NIW": {
        "name": "EB-2 NIW (National Interest Waiver)",
        "exhibits": {
            "A": {"enabled": True, "required": True, "doc_types": ["USCIS Form", "Receipt Notice", "Approval Notice"]},
            "B": {"enabled": True, "required": True, "doc_types": []},
            "C": {"enabled": True, "required": True, "doc_types": ["Passport", "Visa", "I-94 Travel Record", "Resume/CV", "Diploma", "Academic Transcript", "Credential Evaluation", "Employment Letter", "Employment Contract"]},
            "D": {"enabled": True, "required": True, "doc_types": ["Letter of Recommendation", "Personal Statement"], "min_docs": 3, "note": "3-6 strong LORs recommended"},
            "E": {"enabled": True, "required": False, "doc_types": ["Tax Return", "Pay Stub", "Financial Statement"]},
            "F": {"enabled": False, "required": False, "doc_types": ["Professional Membership"]},
            "G": {"enabled": False, "required": False, "doc_types": []},
            "H": {"enabled": False, "required": False, "doc_types": ["Award/Recognition"]},
            "I": {"enabled": False, "required": False, "doc_types": []},
            "J": {"enabled": False, "required": False, "doc_types": []},
            "K": {"enabled": False, "required": False, "doc_types": []},
            "L": {"enabled": True, "required": False, "doc_types": ["Publication", "Portfolio/Work Samples"]},
            "M": {"enabled": True, "required": False, "doc_types": ["Supporting Evidence"]},
        },
        "forms": ["G-28", "I-140", "I-907"],
    },
    "EB-1A": {
        "name": "EB-1A (Extraordinary Ability)",
        "exhibits": {
            "A": {"enabled": True, "required": True, "doc_types": ["USCIS Form", "Receipt Notice", "Approval Notice"]},
            "B": {"enabled": True, "required": True, "doc_types": []},
            "C": {"enabled": True, "required": True, "doc_types": ["Passport", "Visa", "I-94 Travel Record", "Resume/CV", "Diploma", "Academic Transcript", "Employment Letter"]},
            "D": {"enabled": True, "required": True, "doc_types": ["Letter of Recommendation"], "min_docs": 3, "note": "3-6 strong LORs"},
            "E": {"enabled": True, "required": True, "doc_types": ["Tax Return", "Pay Stub", "Financial Statement"]},
            "F": {"enabled": True, "required": False, "doc_types": ["Professional Membership"]},
            "G": {"enabled": True, "required": False, "doc_types": []},
            "H": {"enabled": True, "required": False, "doc_types": ["Award/Recognition"]},
            "I": {"enabled": True, "required": False, "doc_types": []},
            "J": {"enabled": True, "required": False, "doc_types": ["Employment Contract"]},
            "K": {"enabled": True, "required": False, "doc_types": []},
            "L": {"enabled": True, "required": False, "doc_types": ["Publication", "Portfolio/Work Samples"]},
            "M": {"enabled": True, "required": False, "doc_types": ["Supporting Evidence"]},
        },
        "forms": ["G-28", "I-140", "I-907"],
    },
    "EB-1B": {
        "name": "EB-1B (Outstanding Researcher)",
        "exhibits": {
            "A": {"enabled": True, "required": True, "doc_types": ["USCIS Form", "Receipt Notice"]},
            "B": {"enabled": True, "required": True, "doc_types": []},
            "C": {"enabled": True, "required": True, "doc_types": ["Passport", "Visa", "Resume/CV", "Diploma", "Academic Transcript", "Employment Letter"]},
            "D": {"enabled": True, "required": True, "doc_types": ["Letter of Recommendation"], "min_docs": 3},
            "E": {"enabled": True, "required": False, "doc_types": ["Tax Return", "Pay Stub"]},
            "F": {"enabled": True, "required": False, "doc_types": ["Professional Membership"]},
            "G": {"enabled": True, "required": False, "doc_types": []},
            "H": {"enabled": True, "required": False, "doc_types": ["Award/Recognition"]},
            "I": {"enabled": False, "required": False, "doc_types": []},
            "J": {"enabled": True, "required": True, "doc_types": ["Employment Contract"]},
            "K": {"enabled": False, "required": False, "doc_types": []},
            "L": {"enabled": True, "required": False, "doc_types": ["Publication"]},
            "M": {"enabled": True, "required": False, "doc_types": ["Supporting Evidence"]},
        },
        "forms": ["G-28", "I-140"],
    },
    "O-1A": {
        "name": "O-1A (Extraordinary Ability Nonimmigrant)",
        "exhibits": {
            "A": {"enabled": True, "required": True, "doc_types": ["USCIS Form", "Receipt Notice"]},
            "B": {"enabled": True, "required": True, "doc_types": []},
            "C": {"enabled": True, "required": True, "doc_types": ["Passport", "Visa", "Resume/CV", "Diploma", "Employment Letter"]},
            "D": {"enabled": True, "required": True, "doc_types": ["Letter of Recommendation"], "min_docs": 3},
            "E": {"enabled": True, "required": True, "doc_types": ["Tax Return", "Pay Stub"]},
            "F": {"enabled": True, "required": False, "doc_types": ["Professional Membership"]},
            "G": {"enabled": True, "required": False, "doc_types": []},
            "H": {"enabled": True, "required": False, "doc_types": ["Award/Recognition"]},
            "I": {"enabled": True, "required": False, "doc_types": []},
            "J": {"enabled": True, "required": True, "doc_types": ["Employment Contract"]},
            "K": {"enabled": True, "required": False, "doc_types": []},
            "L": {"enabled": True, "required": False, "doc_types": ["Publication", "Portfolio/Work Samples"]},
            "M": {"enabled": True, "required": False, "doc_types": ["Supporting Evidence"]},
        },
        "forms": ["G-28", "I-129", "I-907"],
    },
    "Family-Based": {
        "name": "Family-Based (I-130 + I-485)",
        "exhibits": {
            "A": {"enabled": True, "required": True, "doc_types": ["USCIS Form", "Receipt Notice", "Approval Notice"]},
            "B": {"enabled": True, "required": True, "doc_types": []},
            "C": {"enabled": True, "required": True, "doc_types": ["Passport", "Visa", "I-94 Travel Record", "Birth Certificate", "Marriage Certificate", "Diploma"]},
            "D": {"enabled": False, "required": False, "doc_types": []},
            "E": {"enabled": True, "required": True, "doc_types": ["Tax Return", "Pay Stub", "Financial Statement"]},
            "F": {"enabled": False, "required": False, "doc_types": []},
            "G": {"enabled": False, "required": False, "doc_types": []},
            "H": {"enabled": False, "required": False, "doc_types": []},
            "I": {"enabled": False, "required": False, "doc_types": []},
            "J": {"enabled": True, "required": False, "doc_types": ["Employment Letter"]},
            "K": {"enabled": False, "required": False, "doc_types": []},
            "L": {"enabled": False, "required": False, "doc_types": []},
            "M": {"enabled": True, "required": False, "doc_types": ["Supporting Evidence", "Medical Records", "Police Certificate"]},
        },
        "forms": ["G-28", "I-130", "I-485", "I-864", "I-765", "I-131"],
    },
}


@router.get("/api/package/presets")
async def list_presets(request: Request, db: Session = Depends(get_db)):
    """List all available visa-type package presets."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    presets = []
    for visa_type, config in VISA_PRESETS.items():
        enabled_exhibits = [k for k, v in config["exhibits"].items() if v.get("enabled")]
        required_exhibits = [k for k, v in config["exhibits"].items() if v.get("required")]
        presets.append({
            "visa_type": visa_type,
            "name": config["name"],
            "enabled_exhibits": enabled_exhibits,
            "required_exhibits": required_exhibits,
            "forms": config.get("forms", []),
        })

    return JSONResponse({"presets": presets})


@router.get("/api/package/presets/{visa_type}")
async def get_preset(request: Request, visa_type: str, db: Session = Depends(get_db)):
    """Get a specific visa-type package preset with full exhibit config."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    config = VISA_PRESETS.get(visa_type)
    if not config:
        return JSONResponse({"error": f"Unknown visa type: {visa_type}"}, status_code=404)

    return JSONResponse({
        "visa_type": visa_type,
        "name": config["name"],
        "exhibits": config["exhibits"],
        "forms": config.get("forms", []),
    })


@router.post("/api/package/validate")
async def validate_package_api(
    request: Request,
    db: Session = Depends(get_db)
):
    """Validate a package structure before building."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    try:
        body = await request.json()
        structure = body.get("structure", [])

        issues = []
        warnings = []
        info = []

        # Which exhibits have content
        present_exhibits = set()
        exhibit_file_counts = {}
        total_files = 0

        for item in structure:
            letter = item.get("letter", "")
            files = item.get("files", [])
            if files:
                present_exhibits.add(letter)
                exhibit_file_counts[letter] = len(files)
                total_files += len(files)

        # Check required exhibits
        for req in REQUIRED_EXHIBITS:
            if req not in present_exhibits:
                from services.package_builder import EXHIBITS
                name = EXHIBITS.get(req, {}).get("name", req)
                issues.append({
                    "type": "missing_required",
                    "exhibit": req,
                    "message": f"Missing required Exhibit {req}: {name}"
                })

        # Check LOR count
        lor_count = exhibit_file_counts.get("D", 0)
        if "D" in present_exhibits and lor_count < 3:
            warnings.append({
                "type": "insufficient_lors",
                "exhibit": "D",
                "count": lor_count,
                "message": f"Exhibit D has only {lor_count} LORs. Recommend 3-6 strong letters."
            })
        elif "D" in present_exhibits and lor_count > 8:
            info.append({
                "type": "many_lors",
                "exhibit": "D",
                "message": f"Exhibit D has {lor_count} LORs. Consider quality over quantity."
            })

        # Check evidence count
        evidence_exhibits = present_exhibits - {"A", "B", "C", "D"}
        if len(evidence_exhibits) < 2:
            warnings.append({
                "type": "limited_evidence",
                "exhibit": None,
                "message": "Only " + str(len(evidence_exhibits)) + " evidence exhibits. Consider adding more supporting evidence."
            })

        valid = len(issues) == 0

        return JSONResponse({
            "valid": valid,
            "issues": issues,
            "warnings": warnings,
            "info": info,
            "summary": {
                "exhibits_present": sorted(list(present_exhibits)),
                "exhibits_with_content": len(present_exhibits),
                "total_files": total_files,
                "required_present": sorted(list(present_exhibits & REQUIRED_EXHIBITS)),
                "required_missing": sorted(list(REQUIRED_EXHIBITS - present_exhibits)),
            }
        })

    except Exception as e:
        logger.error(f"Package validation error: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/package/build")
async def build_package_api(
    request: Request,
    db: Session = Depends(get_db),
    _feature=Depends(require_feature("package_builder")),
):
    """Build a USCIS package from uploaded files organized into exhibits."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    org_id = get_request_org_id(request)
    if org_id is None:
        return JSONResponse({"error": "Organization not found"}, status_code=404)

    try:
        from services.package_builder import PackageBuilder

        form = await request.form()

        beneficiary_name = form.get("beneficiary_name", "Petitioner")
        case_type = form.get("case_type", "EB-2 NIW")
        include_toc = form.get("include_toc", "true") == "true"
        include_separators = form.get("include_separators", "true") == "true"

        # Parse exhibit structure from form
        structure_json = form.get("structure", "[]")
        try:
            structure = json.loads(structure_json)
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid exhibit structure"}, status_code=400)

        # Parse server files (documents from DB, no re-upload needed)
        server_files_json = form.get("server_files", "[]")
        try:
            server_files = json.loads(server_files_json)
        except json.JSONDecodeError:
            server_files = []

        os.makedirs(OUTPUT_DIR, exist_ok=True)

        # Create temp directory for uploaded files
        temp_dir = tempfile.mkdtemp()

        try:
            builder = PackageBuilder(
                beneficiary_name=beneficiary_name,
                case_type=case_type,
                output_dir=OUTPUT_DIR,
                include_separators=include_separators,
                include_toc=include_toc,
            )

            failed_files = []
            added_files = 0

            # Process server files FIRST (documents already in DB)
            for sf in server_files:
                doc_id = sf.get("doc_id")
                exhibit = sf.get("exhibit")
                description = sf.get("description", "")

                if not doc_id or not exhibit:
                    continue

                # IDOR C3: re-validate the document belongs to this tenant
                # BEFORE resolving its path and reading bytes off disk.
                doc = tenant_query(db, Document, org_id).filter(Document.id == doc_id).first()
                if not doc:
                    failed_files.append(f"Document {doc_id}: not found in database")
                    continue

                # Resolve file path: storage_path -> local_path -> file_path
                resolved_path = None
                for path_attr in [doc.storage_path, doc.local_path, doc.file_path]:
                    if path_attr and os.path.exists(path_attr):
                        resolved_path = path_attr
                        break

                if not resolved_path:
                    failed_files.append(f"{doc.name} (Exhibit {exhibit}): file not found on disk")
                    continue

                try:
                    success = builder.add_document(
                        exhibit=exhibit,
                        filepath=resolved_path,
                        description=description or doc.name,
                    )
                    if success:
                        added_files += 1
                    else:
                        failed_files.append(f"{doc.name} (Exhibit {exhibit}): unsupported format")
                except Exception as e:
                    failed_files.append(f"{doc.name} (Exhibit {exhibit}): {str(e)}")
                    logger.error(f"Error adding server file {doc.name}: {e}")

            # Process generated USCIS forms (already exist in OUTPUT_DIR)
            generated_forms_json = form.get("generated_forms", "[]")
            try:
                generated_forms = json.loads(generated_forms_json)
            except json.JSONDecodeError:
                generated_forms = []

            for gf in generated_forms:
                filename = gf.get("filename", "")
                exhibit = gf.get("exhibit", "A")
                description = gf.get("description", "")

                if not filename or '..' in filename or '/' in filename:
                    failed_files.append(f"{filename}: invalid filename")
                    continue

                form_path = os.path.realpath(os.path.join(OUTPUT_DIR, filename))
                if not form_path.startswith(os.path.realpath(OUTPUT_DIR)):
                    failed_files.append(f"{filename}: path traversal blocked")
                    continue

                if not os.path.exists(form_path):
                    failed_files.append(f"{filename}: not found in output directory")
                    continue

                try:
                    success = builder.add_document(
                        exhibit=exhibit,
                        filepath=form_path,
                        description=description or filename,
                    )
                    if success:
                        added_files += 1
                    else:
                        failed_files.append(f"{filename}: unsupported format")
                except Exception as e:
                    failed_files.append(f"{filename}: {str(e)}")
                    logger.error(f"Error adding generated form {filename}: {e}")

            # Process uploaded files (backward compatible)
            file_index = 0

            # Sort file keys numerically (file_0, file_1, ..., file_10, file_11)
            file_keys = [k for k in form.keys() if k.startswith("file_")]
            file_keys.sort(key=lambda k: int(k.split("_", 1)[1]))

            for key in file_keys:
                upload = form[key]
                if hasattr(upload, 'filename') and upload.filename:
                    temp_path = os.path.join(temp_dir, f"{file_index}_{upload.filename}")
                    content = await upload.read()
                    with open(temp_path, "wb") as f:
                        f.write(content)

                    matched = False
                    for item in structure:
                        for file_ref in item.get("files", []):
                            if file_ref.get("index") == file_index:
                                matched = True
                                try:
                                    success = builder.add_document(
                                        exhibit=item["letter"],
                                        filepath=temp_path,
                                        description=file_ref.get("description", upload.filename),
                                    )
                                    if success:
                                        added_files += 1
                                    else:
                                        failed_files.append(f"{upload.filename} (Exhibit {item['letter']}): unsupported format")
                                except Exception as e:
                                    failed_files.append(f"{upload.filename} (Exhibit {item['letter']}): {str(e)}")
                                    logger.error(f"Error adding {upload.filename}: {e}")

                    if not matched:
                        logger.warning(f"File {upload.filename} (index {file_index}) not matched in structure")

                    file_index += 1

            if added_files == 0:
                error_detail = "No files were successfully added to the package."
                if failed_files:
                    error_detail += " Errors: " + "; ".join(failed_files)
                return JSONResponse({"error": error_detail}, status_code=400)

            filepath = builder.build()
            filename = os.path.basename(filepath)

            total_docs = sum(len(d) for d in builder.documents.values())
            total_exhibits = sum(1 for d in builder.documents.values() if d)

            result = {
                "success": True,
                "filename": filename,
                "download_url": f"{PREFIX}/api/package/download/{filename}",
                "total_documents": total_docs,
                "total_exhibits": total_exhibits,
            }
            if failed_files:
                result["warnings"] = failed_files
            return JSONResponse(result)

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        logger.error(f"Package build error: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/package/download/{filename}")
async def download_package(request: Request, filename: str, db: Session = Depends(get_db)):
    """Download a built package."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-. ")
    if not all(c in safe_chars for c in filename) or '..' in filename:
        return JSONResponse({"error": "Invalid filename"}, status_code=400)

    filepath = os.path.realpath(os.path.join(OUTPUT_DIR, filename))
    if not filepath.startswith(os.path.realpath(OUTPUT_DIR)):
        return JSONResponse({"error": "Invalid filename"}, status_code=400)
    if not os.path.exists(filepath):
        return JSONResponse({"error": "File not found"}, status_code=404)

    response = FileResponse(filepath, filename=filename, media_type="application/pdf")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
