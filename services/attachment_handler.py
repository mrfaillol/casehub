#!/usr/bin/env python3
"""
Attachment Handler - CaseHub
Downloads email attachments, classifies them with LLM, and saves to organized storage.
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

# Document types for classification
DOCUMENT_TYPES = [
    "Passport",
    "I-94 Travel Record",
    "Visa",
    "EAD Card",
    "Green Card",
    "Birth Certificate",
    "Marriage Certificate",
    "Diploma",
    "Academic Transcript",
    "Employment Letter",
    "Tax Return",
    "Pay Stub",
    "Bank Statement",
    "Letter of Recommendation",
    "Supporting Evidence",
    "USCIS Form",
    "Receipt Notice",
    "Approval Notice",
    "Request for Evidence",
    "Expansion",
    "Testimonial",
    "Other Document"
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
        prompt = f"""Analyze the filename below and classify it into one of the categories listed.
Reply with ONLY the exact category name, no explanations.

Filename: {filename}

Available categories:
- Passport
- I-94 Travel Record
- Visa
- EAD Card
- Green Card
- Birth Certificate
- Marriage Certificate
- Diploma
- Academic Transcript
- Employment Letter
- Tax Return
- Pay Stub
- Bank Statement
- Letter of Recommendation
- Supporting Evidence
- USCIS Form
- Receipt Notice
- Approval Notice
- Request for Evidence
- Expansion (EB1A expansion letters, extraordinary ability)
- Testimonial (personal statement, prongs questionnaire)
- Other Document

Category:"""

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

        logger.warning(f"LLM returned unknown type '{response_text}', defaulting to Other Document")
        return "Other Document"

    except Exception as e:
        logger.error(f"LLM classification error: {e}")
        return classify_by_filename(filename)


def classify_by_filename(filename: str) -> str:
    """
    Fallback classification based on filename patterns.
    """
    filename_lower = filename.lower()

    # Pattern matching
    patterns = {
        "Passport": ["passport", "pasaporte", "passaporte"],
        "I-94 Travel Record": ["i-94", "i94", "arrival", "departure"],
        "Visa": ["visa", "visto"],
        "EAD Card": ["ead", "employment authorization", "work permit"],
        "Green Card": ["green card", "permanent resident", "i-551"],
        "Birth Certificate": ["birth", "nascimento", "certidao"],
        "Marriage Certificate": ["marriage", "casamento", "wedding"],
        "Diploma": ["diploma", "degree", "graduacao"],
        "Academic Transcript": ["transcript", "historico", "grades"],
        "Employment Letter": ["employment letter", "carta de emprego", "job letter", "offer letter"],
        "Tax Return": ["tax return", "1040", "w-2", "imposto"],
        "Pay Stub": ["pay stub", "paystub", "paycheck", "contracheque", "holerite"],
        "Bank Statement": ["bank statement", "extrato", "statement"],
        "Letter of Recommendation": ["recommendation", "recomendacao", "lor", "reference"],
        "Supporting Evidence": ["evidence", "exhibit", "prova"],
        "USCIS Form": ["i-140", "i-485", "i-765", "i-131", "i-130", "i-129", "g-28", "i-907"],
        "Receipt Notice": ["receipt", "recibo", "i-797c"],
        "Approval Notice": ["approval", "aprovacao", "approved", "i-797"],
        "Request for Evidence": ["rfe", "request for evidence", "solicitacao"],
        "Expansion": ["expansion", "carta", "carta de expansao", "eb1a expansion", "prong", "extraordinary ability", "habilidade extraordinaria"],
        "Testimonial": ["testimonial", "personal statement", "personal_statement", "declaracao pessoal", "questionnaire", "ps questionnaire", "prong 1", "prong 2", "prong 3"]
    }

    for doc_type, keywords in patterns.items():
        for keyword in keywords:
            if keyword in filename_lower:
                return doc_type

    return "Other Document"


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

            return {
                "success": True,
                "path": str(file_path),
                "name": filename,
                "safe_name": safe_filename,
                "type": doc_type,
                "size": len(content),
                "client": client_name,
                "date": email_date.isoformat()
            }

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

    logger.info("Testing Attachment Handler...")

    # Test classification
    test_files = [
        "passport_scan.pdf",
        "I-140_receipt.pdf",
        "employment_letter_company.docx",
        "bank_statement_jan_2026.pdf",
        "random_document.pdf"
    ]

    logger.info("Classification tests:")
    for filename in test_files:
        doc_type = classify_by_filename(filename)
        logger.info("  %s -> %s", filename, doc_type)

    # Test saving (dry run)
    logger.info("Storage path test:")
    path = get_storage_path()
    logger.info("  Today's storage path: %s", path)
