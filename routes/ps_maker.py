"""
CaseHub - PS Maker Routes
Native Personal Statement generator for EB-2 NIW petitions.
Full feature parity: Content Extractor with AI, custom section titles,
processing options (grammar, completion, language enhancement).
"""
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
import os
import re
import json
import shutil
import tempfile
import logging
import httpx

from models import get_db, Client, Case
from models.tenant import tenant_query
from auth import get_current_user
from core.request_utils import get_request_org_id
from middleware.features import require_feature
from config import settings

logger = logging.getLogger(__name__)

PREFIX = settings.PREFIX
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "output")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

router = APIRouter(tags=["ps-maker"])
templates = Jinja2Templates(directory="templates")


def extract_text_from_file(filepath: str) -> str:
    """Extract text from PDF, DOCX, or TXT file."""
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == '.txt':
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        elif ext == '.docx':
            from docx import Document as DocxDocument
            doc = DocxDocument(filepath)
            return '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])
        elif ext == '.pdf':
            from PyPDF2 import PdfReader
            reader = PdfReader(filepath)
            return '\n'.join([page.extract_text() or '' for page in reader.pages])
    except Exception as e:
        logger.error(f"Text extraction failed: {e}")
    return ""


@router.get("/ps-maker", response_class=HTMLResponse)
async def ps_maker_page(
    request: Request,
    case_id: Optional[int] = None,
    client_name: Optional[str] = None,
    visa_type: Optional[str] = None,
    db: Session = Depends(get_db),
    _feature=Depends(require_feature("ai_ps")),
):
    """Render the PS Maker form page."""
    from fastapi.responses import RedirectResponse
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"{PREFIX}/login", status_code=302)

    org_id = get_request_org_id(request)
    prefill = {"beneficiary_name": "", "field": ""}
    case = None

    if case_id and org_id is not None:
        case = tenant_query(db, Case, org_id).filter(Case.id == case_id).first()
        if case:
            client = tenant_query(db, Client, org_id).filter(Client.id == case.client_id).first()
            if client:
                prefill["beneficiary_name"] = f"{client.first_name} {client.last_name}"

    if client_name and not prefill["beneficiary_name"]:
        prefill["beneficiary_name"] = client_name.replace("+", " ")

    from services.ps_generator import GOVERNMENT_DOCS
    field_list = list(GOVERNMENT_DOCS.keys())

    return templates.TemplateResponse("app/ps_maker/form.html", {
        "request": request, "user": user, "PREFIX": PREFIX,
        "prefill": prefill,
        "case": case,
        "fields": field_list,
    })


@router.post("/api/ps/generate")
async def generate_ps_api(
    request: Request,
    beneficiary_name: str = Form(...),
    field: str = Form(...),
    overview: str = Form(""),
    national_importance: str = Form(""),
    practical_impact: str = Form(""),
    well_positioned: str = Form(""),
    conclusion: str = Form(""),
    salutation: str = Form(""),
    closing: str = Form(""),
    section1_title: str = Form("I. Overview of the Proposed Endeavor"),
    section2_title: str = Form("II. National Importance of the Endeavor"),
    section3_title: str = Form("III. Practical Impact and Innovation"),
    section4_title: str = Form("IV. Why I Am Well-Positioned"),
    section5_title: str = Form("V. Conclusion"),
    case_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    _feature=Depends(require_feature("ai_ps")),
):
    """Generate a Personal Statement with custom section titles."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    try:
        from services.ps_generator import PSGenerator

        os.makedirs(OUTPUT_DIR, exist_ok=True)

        generator = PSGenerator(
            beneficiary_name=beneficiary_name,
            field=field,
            output_dir=OUTPUT_DIR,
        )

        sections = {}
        section_keys = ["overview", "national_importance", "practical_impact", "well_positioned", "conclusion"]
        section_values = [overview, national_importance, practical_impact, well_positioned, conclusion]

        for key, value in zip(section_keys, section_values):
            if value.strip():
                sections[key] = value.strip()
            else:
                sections[key] = generator.get_section_template(key)

        filepath = generator.create_document(
            sections=sections,
            salutation=salutation if salutation else None,
            closing=closing if closing else None,
        )

        filename = os.path.basename(filepath)

        return JSONResponse({
            "success": True,
            "filename": filename,
            "download_url": f"{PREFIX}/api/ps/download/{filename}",
            "beneficiary": beneficiary_name,
            "field": field,
        })

    except Exception as e:
        logger.error(f"PS generation error: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/ps/extract")
async def extract_ps_data(
    request: Request,
    file: UploadFile = File(...),
    context: str = Form(""),
    fix_errors: str = Form("false"),
    complete_sections: str = Form("false"),
    enhance_language: str = Form("false"),
    db: Session = Depends(get_db)
):
    """Extract and organize PS content from an uploaded document using AI."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    logger.info(f"Extracting PS data from {file.filename}")

    do_fix = fix_errors.lower() == 'true'
    do_complete = complete_sections.lower() == 'true'
    do_enhance = enhance_language.lower() == 'true'

    temp_dir = tempfile.mkdtemp()
    temp_path = None

    try:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ['.docx', '.pdf', '.txt', '.doc']:
            return JSONResponse({"success": False, "error": "Unsupported file format. Use PDF, DOCX, or TXT."}, status_code=400)

        temp_path = os.path.join(temp_dir, f"ps_extract{ext}")
        content_bytes = await file.read()
        with open(temp_path, "wb") as f:
            f.write(content_bytes)

        content = extract_text_from_file(temp_path)
        if not content.strip():
            return JSONResponse({"success": False, "error": "Could not extract text from file"}, status_code=400)

        # Truncate for API limits
        content = content[:25000]

        # Build prompt
        instructions = []
        instructions.append("1. Extract the beneficiary name and field of endeavor.")
        instructions.append("2. Draft or refine the following sections: Overview, National Importance, Practical Impact, Well Positioned, Conclusion.")
        if do_fix:
            instructions.append("3. Fix grammar and spelling errors.")
        if do_complete:
            instructions.append(f"{'4' if do_fix else '3'}. Complete any missing logic or sparse sections using reasonable professional inferences.")
        if do_enhance:
            instructions.append(f"{'5' if do_fix and do_complete else '4' if do_fix or do_complete else '3'}. Enhance the language to be more persuasive and professional.")

        prompt = f"""You are an expert immigration attorney assistant. Analyze the provided document text and extract information to draft or improve a Personal Statement for an EB-2 National Interest Waiver (NIW) or EB-1A petition.

CONTEXT provided by user: "{context}"
DOCUMENT TEXT:
{content}

INSTRUCTIONS:
{chr(10).join(instructions)}

Output strictly valid JSON with no markdown formatting:
{{
    "beneficiary_name": "Name found",
    "field": "Field found",
    "overview": "text content...",
    "national_importance": "text content...",
    "practical_impact": "text content...",
    "well_positioned": "text content...",
    "conclusion": "text content...",
    "suggestions": ["suggestion 1", "suggestion 2", "suggestion 3"]
}}"""

        # Try Gemini first, then Perplexity
        extracted_data = None

        if GEMINI_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
                        params={"key": GEMINI_API_KEY},
                        json={
                            "contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {"temperature": 0.3}
                        }
                    )
                    if response.status_code == 200:
                        data = response.json()
                        text = data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                        match = re.search(r'\{[\s\S]*\}', text)
                        if match:
                            extracted_data = json.loads(match.group(0))
            except Exception as e:
                logger.warning(f"Gemini extraction failed, trying Perplexity: {e}")

        if extracted_data is None and PERPLEXITY_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        "https://api.perplexity.ai/chat/completions",
                        headers={
                            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": "sonar",
                            "messages": [
                                {"role": "system", "content": "You are an expert legal assistant. Return only valid JSON."},
                                {"role": "user", "content": prompt}
                            ]
                        }
                    )
                    if response.status_code == 200:
                        data = response.json()
                        completion = data['choices'][0]['message']['content']
                        match = re.search(r'\{[\s\S]*\}', completion)
                        if match:
                            extracted_data = json.loads(match.group(0))
            except Exception as e:
                logger.error(f"Perplexity extraction also failed: {e}")

        if extracted_data is None:
            return JSONResponse({"success": False, "error": "AI extraction failed. No API keys configured or services unavailable."}, status_code=500)

        return JSONResponse({"success": True, "extracted": extracted_data})

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error from AI: {e}")
        return JSONResponse({"success": False, "error": "AI response was not valid JSON"}, status_code=500)
    except Exception as e:
        logger.error(f"Extract failed: {e}", exc_info=True)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.get("/api/ps/download/{filename}")
async def download_ps(request: Request, filename: str, db: Session = Depends(get_db)):
    """Download a generated PS file."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-. ")
    if not all(c in safe_chars for c in filename):
        return JSONResponse({"error": "Invalid filename"}, status_code=400)

    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        return JSONResponse({"error": "File not found"}, status_code=404)

    return FileResponse(filepath, filename=filename)
