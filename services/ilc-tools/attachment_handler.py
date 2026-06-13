#!/usr/bin/env python3
"""
Attachment Handler - CaseHub
Downloads email attachments, classifies them with LLM, and saves to organized storage.

Enhanced Pipeline (2026):
1. Save attachment locally
2. Extract text (OCR/PDF)
3. Analyze with local LLM (LM Studio)
4. Classify document type and visa category
5. Generate descriptive title
6. Upload to Google Drive (organized by client/visa/type)
7. Save metadata with Drive link
"""

import os
import re
import logging
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Configuration
ATTACHMENTS_BASE_PATH = os.getenv("ATTACHMENTS_BASE_PATH", "/data/attachments")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Feature flags
ENABLE_LOCAL_LLM = os.getenv("ENABLE_LOCAL_LLM", "true").lower() == "true"
ENABLE_GDRIVE_UPLOAD = os.getenv("ENABLE_GDRIVE_UPLOAD", "true").lower() == "true"
ENABLE_OCR = os.getenv("ENABLE_OCR", "true").lower() == "true"

# Document types for classification
DOCUMENT_TYPES = [
    "Passaporte",
    "I-94",
    "Visa",
    "EAD Card",
    "Green Card",
    "Birth Certificate",
    "Marriage Certificate",
    "Diploma",
    "Transcript",
    "Employment Letter",
    "Tax Return",
    "Pay Stub",
    "Bank Statement",
    "Recommendation Letter",
    "Evidence",
    "USCIS Form",
    "Receipt Notice",
    "Approval Notice",
    "RFE",
    "Outro"
]

# File extensions to process
ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".gif",
    ".tiff", ".tif", ".bmp", ".xls", ".xlsx", ".txt", ".rtf"
}


def slugify(text: str) -> str:
    """Convert text to a safe filename slug."""
    if not text:
        return "unknown"
    # Remove accents and special characters
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '_', text)
    return text[:50]  # Limit length


def get_storage_path(date: datetime = None) -> Path:
    """Get the storage path for a given date."""
    if date is None:
        date = datetime.now()
    date_str = date.strftime("%Y-%m-%d")
    path = Path(ATTACHMENTS_BASE_PATH) / date_str
    path.mkdir(parents=True, exist_ok=True)
    return path


def classify_document_with_llm(filename: str, content_preview: bytes = None) -> str:
    """
    Use Anthropic Claude to classify document type based on filename and content.

    Args:
        filename: Original filename of the attachment
        content_preview: First few KB of file content (for text files)

    Returns:
        Document type from DOCUMENT_TYPES list
    """
    if not ANTHROPIC_API_KEY:
        logger.warning("No Anthropic API key configured, using filename-based classification")
        return classify_by_filename(filename)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # Build prompt
        prompt = f"""Analise o nome deste arquivo e classifique em uma das categorias abaixo.
Responda APENAS com o nome exato da categoria, sem explicacoes.

Nome do arquivo: {filename}

Categorias disponiveis:
- Passaporte
- I-94
- Visa
- EAD Card
- Green Card
- Birth Certificate
- Marriage Certificate
- Diploma
- Transcript
- Employment Letter
- Tax Return
- Pay Stub
- Bank Statement
- Recommendation Letter
- Evidence
- USCIS Form
- Receipt Notice
- Approval Notice
- RFE
- Outro

Categoria:"""

        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text.strip()

        # Validate response
        for doc_type in DOCUMENT_TYPES:
            if doc_type.lower() in response_text.lower():
                return doc_type

        logger.warning(f"LLM returned unknown type '{response_text}', defaulting to Outro")
        return "Outro"

    except Exception as e:
        logger.error(f"LLM classification error: {e}")
        return classify_by_filename(filename)


def process_document_with_pipeline(
    file_path: str,
    filename: str,
    client_name: str
) -> Dict[str, Any]:
    """
    Process document through the enhanced pipeline:
    1. Extract text
    2. Analyze with local LLM
    3. Classify visa category
    4. Generate title
    5. Upload to Google Drive

    Args:
        file_path: Path to the saved file
        filename: Original filename
        client_name: Client name

    Returns:
        Dict with processing results
    """
    result = {
        "text_extracted": False,
        "llm_analyzed": False,
        "drive_uploaded": False,
        "document_type": "Outro",
        "visa_category": "General",
        "suggested_title": None,
        "drive_link": None,
        "drive_file_id": None,
        "extraction_method": None,
        "confidence": "low"
    }

    extracted_text = ""

    # Step 1: Extract text from document
    if ENABLE_OCR:
        try:
            from document_extractor import extract_text_auto

            extraction = extract_text_auto(file_path)
            if extraction["success"]:
                extracted_text = extraction["text"]
                result["text_extracted"] = True
                result["extraction_method"] = extraction["method"]
                logger.info(f"Extracted {len(extracted_text)} chars via {extraction['method']}")
        except ImportError:
            logger.warning("document_extractor not available, skipping text extraction")
        except Exception as e:
            logger.error(f"Text extraction failed: {e}")

    # Step 2: Analyze with local LLM
    if ENABLE_LOCAL_LLM and extracted_text:
        try:
            from document_analyzer import analyze_document_content

            analysis = analyze_document_content(extracted_text, filename)

            if analysis["method"] == "llm":
                result["llm_analyzed"] = True
                result["document_type"] = analysis["document_type"]
                result["suggested_title"] = analysis["suggested_title"]
                result["confidence"] = analysis["confidence"]

                # Use LLM's visa category if confident
                if analysis["visa_category"] != "Unknown":
                    result["visa_category"] = analysis["visa_category"]

                logger.info(f"LLM analysis: type={analysis['document_type']}, category={analysis['visa_category']}")

        except ImportError:
            logger.warning("document_analyzer not available, skipping LLM analysis")
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")

    # Step 3: Classify visa category (if LLM didn't provide one)
    if result["visa_category"] == "General" and extracted_text:
        try:
            from visa_category_classifier import classify_document

            category, subfolder, confidence = classify_document(
                extracted_text,
                result["document_type"],
                filename
            )
            result["visa_category"] = category
            logger.info(f"Visa classification: {category} (confidence: {confidence:.1%})")

        except ImportError:
            logger.warning("visa_category_classifier not available")
        except Exception as e:
            logger.error(f"Visa classification failed: {e}")

    # Step 4: Upload to Google Drive
    if ENABLE_GDRIVE_UPLOAD:
        try:
            from google_drive_handler import GoogleDriveHandler

            drive_handler = GoogleDriveHandler()
            if drive_handler.is_connected():
                # Use suggested title or original filename
                doc_title = result["suggested_title"] or Path(filename).stem

                upload_result = drive_handler.upload_document(
                    file_path=file_path,
                    client_name=client_name,
                    document_title=doc_title,
                    visa_category=result["visa_category"],
                    document_type=result["document_type"]
                )

                if upload_result["success"]:
                    result["drive_uploaded"] = True
                    result["drive_link"] = upload_result["web_link"]
                    result["drive_file_id"] = upload_result["file_id"]
                    logger.info(f"Uploaded to Drive: {upload_result['web_link']}")
                else:
                    logger.warning(f"Drive upload failed: {upload_result.get('error')}")
            else:
                logger.info("Google Drive not connected, skipping upload")

        except ImportError:
            logger.warning("google_drive_handler not available, skipping Drive upload")
        except Exception as e:
            logger.error(f"Drive upload failed: {e}")

    return result


def classify_by_filename(filename: str) -> str:
    """
    Fallback classification based on filename patterns.
    """
    filename_lower = filename.lower()

    # Pattern matching
    patterns = {
        "Passaporte": ["passport", "pasaporte", "passaporte"],
        "I-94": ["i-94", "i94", "arrival", "departure"],
        "Visa": ["visa", "visto"],
        "EAD Card": ["ead", "employment authorization", "work permit"],
        "Green Card": ["green card", "permanent resident", "i-551"],
        "Birth Certificate": ["birth", "nascimento", "certidao"],
        "Marriage Certificate": ["marriage", "casamento", "wedding"],
        "Diploma": ["diploma", "degree", "graduacao"],
        "Transcript": ["transcript", "historico", "grades"],
        "Employment Letter": ["employment letter", "carta de emprego", "job letter", "offer letter"],
        "Tax Return": ["tax return", "1040", "w-2", "imposto"],
        "Pay Stub": ["pay stub", "paystub", "paycheck", "contracheque", "holerite"],
        "Bank Statement": ["bank statement", "extrato", "statement"],
        "Recommendation Letter": ["recommendation", "recomendacao", "lor", "reference"],
        "Evidence": ["evidence", "exhibit", "prova"],
        "USCIS Form": ["i-140", "i-485", "i-765", "i-131", "i-130", "i-129", "g-28", "i-907"],
        "Receipt Notice": ["receipt", "recibo", "i-797c"],
        "Approval Notice": ["approval", "aprovacao", "approved", "i-797"],
        "RFE": ["rfe", "request for evidence", "solicitacao"]
    }

    for doc_type, keywords in patterns.items():
        for keyword in keywords:
            if keyword in filename_lower:
                return doc_type

    return "Outro"


class AttachmentHandler:
    """Handles downloading, classifying, and saving email attachments."""

    def __init__(self, base_path: str = None):
        self.base_path = Path(base_path or ATTACHMENTS_BASE_PATH)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save_attachment(
        self,
        content: bytes,
        filename: str,
        client_name: str,
        email_date: datetime = None
    ) -> Dict[str, Any]:
        """
        Save an attachment to disk with proper organization.

        Args:
            content: File content as bytes
            filename: Original filename
            client_name: Client name for file naming
            email_date: Date of email for folder organization

        Returns:
            Dict with path, type, name, size, etc.
        """
        if email_date is None:
            email_date = datetime.now()

        # Validate extension
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            logger.warning(f"Skipping file with unsupported extension: {filename}")
            return {"success": False, "error": f"Unsupported extension: {ext}"}

        # Classify document
        doc_type = classify_document_with_llm(filename, content[:4096] if len(content) > 4096 else content)

        # Build safe filename
        client_slug = slugify(client_name)
        type_slug = slugify(doc_type)
        original_name = slugify(Path(filename).stem)
        safe_filename = f"{client_slug}_{type_slug}_{original_name}{ext}"

        # Get storage path
        storage_path = get_storage_path(email_date)
        file_path = storage_path / safe_filename

        # Handle duplicates
        counter = 1
        while file_path.exists():
            safe_filename = f"{client_slug}_{type_slug}_{original_name}_{counter}{ext}"
            file_path = storage_path / safe_filename
            counter += 1

        # Save file
        try:
            with open(file_path, "wb") as f:
                f.write(content)

            logger.info(f"Saved attachment: {file_path}")

            # Initialize result with basic info
            result = {
                "success": True,
                "path": str(file_path),
                "name": filename,
                "safe_name": safe_filename,
                "type": doc_type,
                "size": len(content),
                "client": client_name,
                "date": email_date.isoformat(),
                # New fields from enhanced pipeline
                "visa_category": "General",
                "drive_link": None,
                "drive_file_id": None,
                "suggested_title": None,
                "text_extracted": False,
                "llm_analyzed": False,
                "drive_uploaded": False
            }

            # Run enhanced pipeline (extract, analyze, upload to Drive)
            try:
                pipeline_result = process_document_with_pipeline(
                    file_path=str(file_path),
                    filename=filename,
                    client_name=client_name
                )

                # Update result with pipeline outputs
                if pipeline_result.get("document_type") and pipeline_result["document_type"] != "Outro":
                    result["type"] = pipeline_result["document_type"]

                result["visa_category"] = pipeline_result.get("visa_category", "General")
                result["drive_link"] = pipeline_result.get("drive_link")
                result["drive_file_id"] = pipeline_result.get("drive_file_id")
                result["suggested_title"] = pipeline_result.get("suggested_title")
                result["text_extracted"] = pipeline_result.get("text_extracted", False)
                result["llm_analyzed"] = pipeline_result.get("llm_analyzed", False)
                result["drive_uploaded"] = pipeline_result.get("drive_uploaded", False)

                # If we got a better title from LLM and file was renamed
                if pipeline_result.get("suggested_title"):
                    result["suggested_title"] = pipeline_result["suggested_title"]

            except Exception as e:
                logger.warning(f"Enhanced pipeline failed, continuing with basic save: {e}")

            return result

        except Exception as e:
            logger.error(f"Error saving attachment: {e}")
            return {"success": False, "error": str(e)}

    def process_email_attachments(
        self,
        attachments: List[Tuple[str, bytes]],
        client_name: str,
        email_date: datetime = None
    ) -> List[Dict[str, Any]]:
        """
        Process multiple attachments from an email.

        Args:
            attachments: List of (filename, content) tuples
            client_name: Client name
            email_date: Date of email

        Returns:
            List of save results
        """
        results = []

        for filename, content in attachments:
            result = self.save_attachment(
                content=content,
                filename=filename,
                client_name=client_name,
                email_date=email_date
            )
            results.append(result)

        success_count = sum(1 for r in results if r.get("success"))
        logger.info(f"Processed {success_count}/{len(attachments)} attachments for {client_name}")

        return results

    def get_attachment_stats(self) -> Dict[str, Any]:
        """Get statistics about stored attachments."""
        stats = {
            "total_files": 0,
            "total_size": 0,
            "by_date": {},
            "by_type": {}
        }

        for date_folder in self.base_path.iterdir():
            if date_folder.is_dir():
                date_str = date_folder.name
                stats["by_date"][date_str] = {"files": 0, "size": 0}

                for file_path in date_folder.iterdir():
                    if file_path.is_file():
                        size = file_path.stat().st_size
                        stats["total_files"] += 1
                        stats["total_size"] += size
                        stats["by_date"][date_str]["files"] += 1
                        stats["by_date"][date_str]["size"] += size

                        # Try to extract type from filename
                        parts = file_path.stem.split("_")
                        if len(parts) >= 2:
                            doc_type = parts[1].replace("_", " ").title()
                            if doc_type not in stats["by_type"]:
                                stats["by_type"][doc_type] = 0
                            stats["by_type"][doc_type] += 1

        return stats


# Convenience functions
def save_attachment(
    content: bytes,
    filename: str,
    client_name: str,
    email_date: datetime = None
) -> Dict[str, Any]:
    """Convenience function to save an attachment."""
    handler = AttachmentHandler()
    return handler.save_attachment(content, filename, client_name, email_date)


def classify_document(filename: str) -> str:
    """Convenience function to classify a document."""
    return classify_document_with_llm(filename)


if __name__ == "__main__":
    # Test the handler
    logging.basicConfig(level=logging.INFO)

    print("Testing Attachment Handler...")

    # Test classification
    test_files = [
        "passport_scan.pdf",
        "I-140_receipt.pdf",
        "employment_letter_company.docx",
        "bank_statement_jan_2026.pdf",
        "random_document.pdf"
    ]

    print("\nClassification tests:")
    for filename in test_files:
        doc_type = classify_by_filename(filename)
        print(f"  {filename} -> {doc_type}")

    # Test saving (dry run)
    print("\nStorage path test:")
    path = get_storage_path()
    print(f"  Today's storage path: {path}")
