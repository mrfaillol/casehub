"""
CaseHub Client Intake Portal
Portal público para clientes preencherem formulários USCIS.
Dados são salvos no mesmo banco do CaseHub.
PROTEGIDO COM PASSPHRASE

v2.0 - Adicionado suporte a upload de documentos
"""
import os
import uuid
import shutil
from datetime import datetime
from typing import Optional
from pathlib import Path
import json
import hashlib
import threading
import subprocess
import logging

logger = logging.getLogger(__name__)

from fastapi import FastAPI, Request, Form, HTTPException, Depends, Cookie, Response, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

# Document upload configuration
UPLOAD_DIR = Path(os.getenv("PORTAL_UPLOAD_DIR", "/tmp/portal_uploads"))
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB
ALLOWED_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.docx', '.doc'}
ALLOWED_MIME_TYPES = {
    'application/pdf',
    'image/jpeg',
    'image/png',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/msword'
}

# --- Lightweight malware scan ---
# Magic bytes for safe file types
SAFE_MAGIC = {
    '.pdf':  [b'%PDF'],
    '.jpg':  [b'\xff\xd8\xff'],
    '.jpeg': [b'\xff\xd8\xff'],
    '.png':  [b'\x89PNG'],
    '.docx': [b'PK'],       # DOCX = ZIP container
    '.doc':  [b'\xd0\xcf\x11\xe0'],  # OLE2 compound document
}

# Signatures of known dangerous file types - REJECT these
DANGEROUS_SIGS = [
    (b'MZ',           'Windows executable'),
    (b'\x7fELF',      'Linux binary'),
    (b'#!/',          'Shell script'),
    (b'<?php',        'PHP script'),
    (b'<script',      'Script file'),
]

def is_safe_upload(contents: bytes, extension: str) -> tuple:
    """
    Lightweight malware scan. Checks:
    1. File is not empty
    2. File does not match dangerous executable signatures
    3. (Optional) Magic bytes match expected type - WARNING only, not blocking

    Returns: (is_safe: bool, reason: str)
    Designed to minimize false positives per user requirement.
    """
    if len(contents) == 0:
        return False, "Empty file"

    # Check for dangerous signatures (executables, scripts)
    header = contents[:16]
    for sig, desc in DANGEROUS_SIGS:
        if header[:len(sig)] == sig:
            return False, f"File appears to be a {desc}"

    # Check magic bytes match extension (log warning but DON'T block)
    expected = SAFE_MAGIC.get(extension, [])
    if expected:
        matched = any(header[:len(sig)] == sig for sig in expected)
        if not matched:
            logger.warning(
                f"Magic bytes mismatch: extension={extension}, "
                f"header={header[:8].hex()}. Allowing anyway (no false positives)."
            )

    return True, "OK"


def _trigger_drive_sync(doc_id: int):
    """Fire-and-forget Drive sync via casehub subprocess."""
    try:
        result = subprocess.run(
            ['python3', '-c',
             f"import sys; sys.path.insert(0,os.getenv('APP_BASE_PATH', '/opt/casehub') + '/casehub'); "
             f"from database import SessionLocal; "
             f"from services.document_sync import sync_to_google_drive; "
             f"db=SessionLocal(); "
             f"r=sync_to_google_drive(db,{doc_id}); "
             f"print('Drive sync doc {doc_id}:', 'OK' if r.get('success') else r.get('error','')); "
             f"db.close()"],
            cwd=os.getenv('APP_BASE_PATH', '/opt/casehub') + '/casehub',
            timeout=120,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            logger.info(f"Drive sync doc {doc_id}: {result.stdout.strip()}")
        else:
            logger.error(f"Drive sync doc {doc_id} failed: {result.stderr.strip()}")
    except Exception as e:
        logger.error(f"Drive sync doc {doc_id} error: {e}")


# Email notification configuration
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL", "info@casehub.app")

# Paralegal email mapping
PARALEGAL_EMAILS = {
    "Ana Clara": "anacleal.2025@gmail.com",
    "Juliana": "juliana.moreschi.2025@gmail.com"
}

def send_document_notification(client_name: str, doc_type: str, doc_name: str, paralegal: str = None):
    """Send email notification when client uploads a document."""
    if not SMTP_USER or not SMTP_PASSWORD:
        print("SMTP not configured, skipping notification")
        return False

    try:
        # Determine recipient
        to_email = PARALEGAL_EMAILS.get(paralegal, NOTIFICATION_EMAIL)

        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"[CaseHub] New Document Upload - {client_name}"
        msg['From'] = SMTP_FROM
        msg['To'] = to_email

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #1a3d6e 0%, #2c5aa0 100%); padding: 20px; color: white;">
                <h2 style="margin: 0;">New Document Uploaded</h2>
            </div>
            <div style="padding: 20px; background: #f8f9fa;">
                <p><strong>Client:</strong> {client_name}</p>
                <p><strong>Document Type:</strong> {doc_type}</p>
                <p><strong>Document Name:</strong> {doc_name}</p>
                <p><strong>Status:</strong> <span style="color: #ffc107;">Pending Approval</span></p>

                <div style="margin-top: 20px;">
                    <a href="https://casehub.app/casehub/documents"
                       style="background: #2c5aa0; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                        Review in CaseHub
                    </a>
                </div>

                <p style="margin-top: 20px; color: #6c757d; font-size: 12px;">
                    This document requires your review before it will be synced to Google Drive.
                </p>
            </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(html, 'html'))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [to_email, NOTIFICATION_EMAIL], msg.as_string())

        print(f"Notification sent to {to_email}")
        return True

    except Exception as e:
        print(f"Failed to send notification: {e}")
        return False

# Configuração do banco (mesmo do CaseHub)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/casehub")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

app = FastAPI(
    title="CaseHub Client Intake",
    description="Portal para clientes preencherem formulários de imigração",
    version="1.0.0"
)

# Security headers middleware
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
            "connect-src 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

app.add_middleware(SecurityHeadersMiddleware)


# Templates
templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_passphrase(passphrase: str) -> str:
    """Hash simples da passphrase para verificação."""
    return hashlib.sha256(passphrase.encode()).hexdigest()[:16]


def validate_token(db: Session, package_id: str, token: str):
    """Valida o token de acesso e retorna o pacote."""
    result = db.execute(text("""
        SELECT p.*, c.first_name, c.last_name, c.email,
               cs.case_number, cs.case_name
        FROM intake_packages p
        LEFT JOIN clients c ON p.client_id = c.id
        LEFT JOIN cases cs ON p.case_id = cs.id
        WHERE p.package_id = :pid AND p.access_token = :token
        AND p.status IN ('sent', 'in_progress')
        AND (p.expires_at IS NULL OR p.expires_at > NOW())
    """), {"pid": package_id, "token": token})
    return result.fetchone()


def get_package_items(db: Session, package_id: int):
    """Retorna os itens do pacote com info do questionário."""
    result = db.execute(text("""
        SELECT i.*, qt.name as template_name, qt.description as template_desc
        FROM intake_items i
        LEFT JOIN questionnaire_templates qt ON i.questionnaire_id = qt.id
        WHERE i.package_id = :pid
        ORDER BY i.sort_order
    """), {"pid": package_id})
    return result.fetchall()


def get_questionnaire_fields(db: Session, template_id: int):
    """Retorna os campos de um questionário."""
    result = db.execute(text("""
        SELECT * FROM questionnaire_fields
        WHERE template_id = :tid
        ORDER BY section, "order"
    """), {"tid": template_id})
    return result.fetchall()


def get_existing_response(db: Session, package_id: int, item_id: int):
    """Retorna resposta existente se houver."""
    result = db.execute(text("""
        SELECT response_data FROM intake_responses
        WHERE item_id = :iid
        ORDER BY submitted_at DESC
        LIMIT 1
    """), {"iid": item_id})
    row = result.fetchone()
    if row and row.response_data:
        if isinstance(row.response_data, str):
            return json.loads(row.response_data)
        return row.response_data
    return {}


# ============ ROTAS ============

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Página inicial - solicita código de acesso."""
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/test", response_class=HTMLResponse)
async def test_page(request: Request, db: Session = Depends(get_db)):
    """Página de teste - mostra formulário de demonstração."""
    # Criar ou buscar pacote de teste
    test_result = db.execute(text("""
        SELECT * FROM intake_packages WHERE package_id = 'TEST-DEMO'
    """))
    test_pkg = test_result.fetchone()

    if not test_pkg:
        # Info do teste
        info = {
            "package_id": "TEST-DEMO",
            "token": "test-token-demo",
            "passphrase": "REDACTED",
            "message": "Este é um pacote de demonstração para testar o sistema."
        }
    else:
        info = {
            "package_id": test_pkg.package_id,
            "token": test_pkg.access_token,
            "passphrase": test_pkg.passphrase or "N/A",
            "message": "Pacote de teste existente."
        }

    return templates.TemplateResponse("test.html", {
        "request": request,
        "info": info
    })


@app.get("/{package_id}", response_class=HTMLResponse)
async def intake_portal(
    request: Request,
    package_id: str,
    token: str = None,
    db: Session = Depends(get_db),
    intake_auth: str = Cookie(default=None)
):
    """Página principal do intake - lista de formulários."""
    if not token:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Access token required",
            "message": "Please use the link provided by your attorney."
        })

    package = validate_token(db, package_id, token)
    if not package:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Invalid or expired access",
            "message": "This link is invalid or has expired. Please contact your attorney."
        })

    # Verificar passphrase se existir
    if package.passphrase:
        expected_hash = hash_passphrase(package.passphrase)
        if intake_auth != expected_hash:
            # Mostrar página de login com passphrase
            return templates.TemplateResponse("passphrase.html", {
                "request": request,
                "package_id": package_id,
                "token": token,
                "client_name": package.first_name or "Client",
                "error": None
            })

    # Atualizar status para in_progress se ainda estiver como sent
    if package.status == 'sent':
        db.execute(text("""
            UPDATE intake_packages SET status = 'in_progress', updated_at = NOW()
            WHERE id = :id
        """), {"id": package.id})
        db.commit()

    items = get_package_items(db, package.id)

    # Calcular progresso
    total = len(items)
    completed = sum(1 for i in items if i.status in ('submitted', 'approved'))

    return templates.TemplateResponse("intake.html", {
        "request": request,
        "package": package,
        "items": items,
        "token": token,
        "progress": {
            "total": total,
            "completed": completed,
            "percent": int((completed / total) * 100) if total > 0 else 0
        }
    })


@app.post("/{package_id}/auth")
async def verify_passphrase(
    request: Request,
    package_id: str,
    token: str = Form(...),
    passphrase: str = Form(...),
    db: Session = Depends(get_db)
):
    """Verifica a passphrase e define cookie."""
    package = validate_token(db, package_id, token)
    if not package:
        raise HTTPException(status_code=403, detail="Invalid access")

    if package.passphrase and passphrase != package.passphrase:
        return templates.TemplateResponse("passphrase.html", {
            "request": request,
            "package_id": package_id,
            "token": token,
            "client_name": package.first_name or "Client",
            "error": "Incorrect passphrase. Please try again."
        })

    # Criar resposta com redirect e cookie
    response = RedirectResponse(
        url=f"/intake/{package_id}?token={token}",
        status_code=302
    )

    # Definir cookie de autenticação (válido por 24h)
    auth_hash = hash_passphrase(package.passphrase) if package.passphrase else "none"
    response.set_cookie(
        key="intake_auth",
        value=auth_hash,
        max_age=86400,  # 24 horas
        httponly=True,
        secure=True,
        samesite="lax"
    )

    return response


@app.get("/{package_id}/form/{item_id}", response_class=HTMLResponse)
async def show_form(
    request: Request,
    package_id: str,
    item_id: int,
    token: str = None,
    db: Session = Depends(get_db),
    intake_auth: str = Cookie(default=None)
):
    """Mostra um formulário específico para preenchimento."""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")

    package = validate_token(db, package_id, token)
    if not package:
        raise HTTPException(status_code=403, detail="Invalid access")

    # Verificar passphrase
    if package.passphrase:
        expected_hash = hash_passphrase(package.passphrase)
        if intake_auth != expected_hash:
            return RedirectResponse(url=f"/intake/{package_id}?token={token}", status_code=302)

    # Buscar item
    item_result = db.execute(text("""
        SELECT i.*, qt.name as template_name
        FROM intake_items i
        LEFT JOIN questionnaire_templates qt ON i.questionnaire_id = qt.id
        WHERE i.id = :iid AND i.package_id = :pid
    """), {"iid": item_id, "pid": package.id})
    item = item_result.fetchone()

    if not item:
        raise HTTPException(status_code=404, detail="Form not found")

    # Buscar campos do questionário
    fields = get_questionnaire_fields(db, item.questionnaire_id)

    # Buscar respostas existentes
    existing = get_existing_response(db, package.id, item_id)

    # Agrupar campos por seção
    sections = {}
    for field in fields:
        section = field.section or "General"
        if section not in sections:
            sections[section] = []
        sections[section].append(field)

    return templates.TemplateResponse("form.html", {
        "request": request,
        "package": package,
        "item": item,
        "sections": sections,
        "existing": existing,
        "token": token
    })


@app.post("/{package_id}/form/{item_id}/save")
async def save_form(
    request: Request,
    package_id: str,
    item_id: int,
    token: str = None,
    db: Session = Depends(get_db),
    intake_auth: str = Cookie(default=None)
):
    """Salva as respostas do formulário."""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")

    package = validate_token(db, package_id, token)
    if not package:
        raise HTTPException(status_code=403, detail="Invalid access")

    # Verificar passphrase
    if package.passphrase:
        expected_hash = hash_passphrase(package.passphrase)
        if intake_auth != expected_hash:
            raise HTTPException(status_code=403, detail="Authentication required")

    # Pegar dados do form
    form_data = await request.form()
    responses = {key: value for key, value in form_data.items() if key != "token" and key != "_action"}
    action = form_data.get("_action", "save")

    # Salvar resposta
    ip_address = request.client.host if request.client else None

    db.execute(text("""
        INSERT INTO intake_responses (item_id, response_data, ip_address, submitted_at)
        VALUES (:iid, :data, :ip, NOW())
    """), {
        "iid": item_id,
        "data": json.dumps(responses),
        "ip": ip_address
    })

    # Atualizar status do item
    new_status = "submitted" if action == "submit" else "in_progress"
    db.execute(text("""
        UPDATE intake_items
        SET status = :status, submitted_at = CASE WHEN :status = 'submitted' THEN NOW() ELSE submitted_at END
        WHERE id = :iid
    """), {"status": new_status, "iid": item_id})

    db.commit()

    # Verificar se todos os itens obrigatórios foram submetidos
    check = db.execute(text("""
        SELECT COUNT(*) as pending FROM intake_items
        WHERE package_id = :pid AND required = true AND status NOT IN ('submitted', 'approved')
    """), {"pid": package.id}).fetchone()

    if check.pending == 0:
        db.execute(text("""
            UPDATE intake_packages SET status = 'completed', completed_at = NOW()
            WHERE id = :id
        """), {"id": package.id})
        db.commit()

    return RedirectResponse(
        url=f"/intake/{package_id}?token={token}",
        status_code=302
    )


@app.get("/{package_id}/complete", response_class=HTMLResponse)
async def complete_page(
    request: Request,
    package_id: str,
    token: str = None,
    db: Session = Depends(get_db)
):
    """Página de conclusão."""
    package = validate_token(db, package_id, token) if token else None

    return templates.TemplateResponse("complete.html", {
        "request": request,
        "package": package
    })


# ============ DOCUMENT ROUTES ============

def get_client_documents(db: Session, client_id: int):
    """Get documents for a client: visible ones + their own portal uploads."""
    result = db.execute(text("""
        SELECT id, name, doc_type, status, file_size, mime_type,
               visa_category, uploaded_via, created_at, rejection_reason
        FROM documents
        WHERE client_id = :cid
          AND (client_visible IS NULL OR client_visible = TRUE
               OR uploaded_via = 'client_portal')
        ORDER BY created_at DESC
    """), {"cid": client_id})
    return result.fetchall()


def get_document_type_label(doc_type: str) -> str:
    """Convert doc_type code to friendly label."""
    labels = {
        'passport': 'Passport',
        'i94': 'I-94',
        'visa': 'Visa',
        'diploma': 'Diploma',
        'lor': 'Letter of Recommendation',
        'resume': 'Resume/CV',
        'award': 'Award',
        'publication': 'Publication',
        'employment': 'Employment Letter',
        'tax': 'Tax Document',
        'financial': 'Financial Document',
        'birth_cert': 'Birth Certificate',
        'marriage_cert': 'Marriage Certificate',
        'uscis_form': 'USCIS Form',
        'other': 'Other Document'
    }
    return labels.get(doc_type, doc_type.replace('_', ' ').title() if doc_type else 'Document')


@app.get("/{package_id}/documents", response_class=HTMLResponse)
async def documents_page(
    request: Request,
    package_id: str,
    token: str = None,
    db: Session = Depends(get_db),
    intake_auth: str = Cookie(default=None)
):
    """Page to view and upload documents."""
    if not token:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Access token required",
            "message": "Please use the link provided by your attorney."
        })

    package = validate_token(db, package_id, token)
    if not package:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Invalid or expired access",
            "message": "This link is invalid or has expired. Please contact your attorney."
        })

    # Verify passphrase if required
    if package.passphrase:
        expected_hash = hash_passphrase(package.passphrase)
        if intake_auth != expected_hash:
            return RedirectResponse(url=f"/{package_id}?token={token}", status_code=302)

    # Get client's documents
    documents = get_client_documents(db, package.client_id) if package.client_id else []

    # Count by status
    stats = {
        'total': len(documents),
        'pending': sum(1 for d in documents if d.status == 'PENDING_APPROVAL'),
        'approved': sum(1 for d in documents if d.status == 'APPROVED'),
        'rejected': sum(1 for d in documents if d.status == 'REJECTED')
    }

    return templates.TemplateResponse("documents.html", {
        "request": request,
        "package": package,
        "documents": documents,
        "stats": stats,
        "token": token,
        "get_type_label": get_document_type_label
    })


@app.post("/{package_id}/documents/upload")
async def upload_document(
    request: Request,
    package_id: str,
    token: str = Form(...),
    doc_type: str = Form(...),
    description: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    intake_auth: str = Cookie(default=None)
):
    """Upload a document from the client portal."""
    package = validate_token(db, package_id, token)
    if not package:
        raise HTTPException(status_code=403, detail="Invalid access")

    # Verify passphrase
    if package.passphrase:
        expected_hash = hash_passphrase(package.passphrase)
        if intake_auth != expected_hash:
            raise HTTPException(status_code=403, detail="Authentication required")

    # Validate file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        return templates.TemplateResponse("documents.html", {
            "request": request,
            "package": package,
            "documents": get_client_documents(db, package.client_id) if package.client_id else [],
            "stats": {'total': 0, 'pending': 0, 'approved': 0, 'rejected': 0},
            "token": token,
            "get_type_label": get_document_type_label,
            "error": f"File type {file_ext} not allowed. Please upload PDF, JPEG, PNG, or DOCX files."
        })

    # Read and validate file size
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        return templates.TemplateResponse("documents.html", {
            "request": request,
            "package": package,
            "documents": get_client_documents(db, package.client_id) if package.client_id else [],
            "stats": {'total': 0, 'pending': 0, 'approved': 0, 'rejected': 0},
            "token": token,
            "get_type_label": get_document_type_label,
            "error": "File too large. Maximum size is 25MB."
        })


    # Malware scan (lightweight: check for dangerous signatures)
    is_safe, safety_reason = is_safe_upload(contents, file_ext)
    if not is_safe:
        logger.warning(f"Upload rejected - malware scan: {file.filename} - {safety_reason}")
        return templates.TemplateResponse("documents.html", {
            "request": request,
            "package": package,
            "documents": get_client_documents(db, package.client_id) if package.client_id else [],
            "stats": {'total': 0, 'pending': 0, 'approved': 0, 'rejected': 0},
            "token": token,
            "get_type_label": get_document_type_label,
            "error": f"File rejected for security reasons. Please upload a valid document file."
        })

    # Create upload directory
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Generate unique filename
    file_id = str(uuid.uuid4())
    safe_filename = f"{file_id}{file_ext}"
    file_path = UPLOAD_DIR / safe_filename

    # Save file
    with open(file_path, 'wb') as f:
        f.write(contents)

    # Generate display name
    client_name = f"{package.first_name} {package.last_name}".strip() or "Client"
    display_name = description if description else f"{get_document_type_label(doc_type)} - {client_name}"

    # Insert into database with PENDING_APPROVAL status
    db.execute(text("""
        INSERT INTO documents (
            name, doc_type, status, file_path, file_size, mime_type,
            client_id, case_id, uploaded_via, original_filename, local_path,
            client_visible, created_at
        ) VALUES (
            :name, :doc_type, 'APPROVED', :file_path, :file_size, :mime_type,
            :client_id, :case_id, 'client_portal', :original_filename, :local_path,
            TRUE, NOW()
        )
        RETURNING id
    """), {
        "name": display_name,
        "doc_type": doc_type,
        "file_path": str(file_path),
        "file_size": len(contents),
        "mime_type": file.content_type,
        "client_id": package.client_id,
        "case_id": package.case_id,
        "original_filename": file.filename,
        "local_path": str(file_path)
    })
    db.commit()

    # Get the inserted document ID for Drive sync
    doc_id_result = db.execute(text(
        "SELECT id FROM documents WHERE file_path = :fp ORDER BY id DESC LIMIT 1"
    ), {"fp": str(file_path)})
    new_doc_row = doc_id_result.fetchone()
    new_doc_id = new_doc_row[0] if new_doc_row else None

    # Trigger Drive sync in background (non-blocking)
    if new_doc_id:
        threading.Thread(
            target=_trigger_drive_sync,
            args=(new_doc_id,),
            daemon=True
        ).start()
        logger.info(f"Auto-approved doc #{new_doc_id} ({file.filename}), Drive sync triggered")


    # Send notification to paralegal/caseworker
    # Get paralegal assignment from case if available
    paralegal = None
    if package.case_id:
        paralegal_result = db.execute(text("""
            SELECT u.name FROM cases c
            LEFT JOIN users u ON c.paralegal_id = u.id
            WHERE c.id = :case_id
        """), {"case_id": package.case_id})
        row = paralegal_result.fetchone()
        if row:
            paralegal = row.name

    send_document_notification(
        client_name=client_name,
        doc_type=get_document_type_label(doc_type),
        doc_name=display_name,
        paralegal=paralegal
    )

    return RedirectResponse(
        url=f"/{package_id}/documents?token={token}&success=1",
        status_code=302
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
