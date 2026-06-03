"""
CaseHub - OCR Service
PDF text extraction for accurate document classification.

Created: 2026-02-27
Purpose: Extract text from PDFs to improve classification accuracy
"""

import logging
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

try:
    import pytesseract
    from pdf2image import convert_from_path
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logging.warning("Tesseract OCR not available - install pytesseract and pdf2image")

try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    logging.warning("PyPDF2 not available - install PyPDF2")

logger = logging.getLogger(__name__)


class OCRService:
    """
    OCR service for extracting text from documents.

    Priority:
    1. PyPDF2 text extraction (fast, for digital PDFs)
    2. Tesseract OCR (slow, for scanned PDFs)
    """

    def extract_text_from_pdf(self, file_path: Path) -> Dict[str, Any]:
        """
        Extract text from PDF using multiple methods.

        Args:
            file_path: Path to PDF file

        Returns:
            Dictionary with:
                - text: Extracted text content
                - method: Extraction method used (pypdf2, tesseract, failed)
                - confidence: Confidence score (0.0-1.0)
                - processing_time: Time taken in seconds
                - error: Error message if failed

        Example:
            >>> service = OCRService()
            >>> result = service.extract_text_from_pdf(Path("/tmp/document.pdf"))
            >>> if result['method'] != 'failed':
            ...     print(f"Extracted {len(result['text'])} characters")
        """
        start_time = datetime.now()
        result = {
            "text": "",
            "method": "failed",
            "confidence": 0.0,
            "processing_time": 0.0,
            "error": None
        }

        try:
            # Method 1: PyPDF2 (fast, for digital PDFs)
            if PYPDF2_AVAILABLE:
                text, num_pages = self._extract_with_pypdf2(file_path, return_page_count=True)
                result["page_count"] = num_pages

                if text and len(text.strip()) > 100:  # At least 100 chars
                    result["text"] = text
                    result["method"] = "pypdf2"
                    result["confidence"] = 0.95  # High confidence for digital text
                    result["processing_time"] = (datetime.now() - start_time).total_seconds()
                    logger.info(
                        f"PyPDF2 extracted {len(text)} chars from {file_path.name} "
                        f"({num_pages} pages) in {result['processing_time']:.2f}s"
                    )
                    return result

            # Method 2: Tesseract OCR (slow, for scanned PDFs)
            # CRITICAL: Skip very large PDFs to prevent timeouts/hangs (Bug fix for 96-page PDF hang)
            if TESSERACT_AVAILABLE:
                page_count = result.get("page_count", 0)
                max_pages_for_ocr = 50  # Configurable limit

                if page_count > max_pages_for_ocr:
                    logger.warning(
                        f"⚠️ Skipping Tesseract OCR for {file_path.name}: "
                        f"{page_count} pages exceeds limit of {max_pages_for_ocr} pages"
                    )
                    result["method"] = "skipped_too_large"
                    result["text"] = ""
                    result["confidence"] = 0.0
                    result["error"] = f"PDF too large ({page_count} pages > {max_pages_for_ocr} limit)"
                    result["processing_time"] = (datetime.now() - start_time).total_seconds()
                    return result

                ocr_result = self._extract_with_tesseract(file_path)
                result.update(ocr_result)
                result["processing_time"] = (datetime.now() - start_time).total_seconds()
                logger.info(
                    f"Tesseract OCR extracted {len(result['text'])} chars from {file_path.name} "
                    f"in {result['processing_time']:.2f}s (confidence: {result['confidence']:.2f})"
                )
                return result

            # No OCR available
            result["error"] = "No OCR libraries available (need PyPDF2 or Tesseract)"
            logger.error(result["error"])

        except Exception as e:
            logger.exception(f"OCR failed for {file_path}")
            result["error"] = str(e)

        result["processing_time"] = (datetime.now() - start_time).total_seconds()
        return result

    def _extract_with_pypdf2(self, file_path: Path, return_page_count: bool = False):
        """
        Extract text using PyPDF2 (fast method for digital PDFs).

        Args:
            file_path: Path to PDF file
            return_page_count: If True, return tuple of (text, page_count)

        Returns:
            Extracted text (may be empty if PDF is scanned image)
            OR tuple of (text, page_count) if return_page_count=True
        """
        text = []
        num_pages = 0

        try:
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                num_pages = len(reader.pages)

                # Limit to first 50 pages to avoid OOM on huge PDFs
                max_pages = min(num_pages, 50)

                for i in range(max_pages):
                    try:
                        page = reader.pages[i]
                        page_text = page.extract_text()
                        if page_text:
                            text.append(page_text)
                    except Exception as e:
                        logger.warning(f"Failed to extract page {i} from {file_path.name}: {e}")
                        continue

            extracted_text = "\n".join(text)
            if return_page_count:
                return extracted_text, num_pages
            return extracted_text

        except Exception as e:
            logger.error(f"PyPDF2 extraction failed for {file_path.name}: {e}")
            if return_page_count:
                return "", 0
            return ""

    def _extract_with_tesseract(self, file_path: Path) -> Dict[str, Any]:
        """
        Extract text using Tesseract OCR (slow method for scanned PDFs).

        Args:
            file_path: Path to PDF file

        Returns:
            Dictionary with:
                - text: Extracted text
                - method: "tesseract"
                - confidence: Average confidence score
        """
        try:
            # Convert PDF to images (limit to first 10 pages for performance)
            images = convert_from_path(
                str(file_path),
                dpi=300,  # High DPI for better OCR accuracy
                first_page=1,
                last_page=10  # Limit pages to avoid OOM
            )

            text_parts = []
            confidences = []

            for img in images:
                # Extract text with confidence data
                data = pytesseract.image_to_data(
                    img,
                    output_type=pytesseract.Output.DICT,
                    lang='eng'  # English only for now
                )

                # Get text
                page_text = " ".join(data['text'])
                text_parts.append(page_text)

                # Calculate average confidence (filter out -1 values)
                conf_values = [int(c) for c in data['conf'] if c != '-1']
                if conf_values:
                    confidences.append(sum(conf_values) / len(conf_values))

            avg_confidence = sum(confidences) / len(confidences) / 100 if confidences else 0.0

            return {
                "text": "\n".join(text_parts),
                "method": "tesseract",
                "confidence": avg_confidence
            }

        except Exception as e:
            logger.error(f"Tesseract OCR failed for {file_path.name}: {e}")
            return {
                "text": "",
                "method": "failed",
                "confidence": 0.0,
                "error": str(e)
            }

    async def process_document_async(self, document_id: int, db_session):
        """
        Process document OCR in background (async task).

        Use with FastAPI BackgroundTasks or Celery.

        Args:
            document_id: Document ID to process
            db_session: SQLAlchemy database session

        Example:
            >>> from fastapi import BackgroundTasks
            >>> background_tasks.add_task(ocr_service.process_document_async, doc.id, db)
        """
        from models.document import Document

        doc = db_session.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.error(f"Document {document_id} not found")
            return

        # Update status to processing
        doc.ocr_status = "processing"
        db_session.commit()

        try:
            # Get file path
            file_path = Path(doc.storage_path or doc.file_path)

            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            # Only process PDFs for now
            if doc.mime_type != "application/pdf":
                logger.info(f"Document {document_id} is not a PDF (mime: {doc.mime_type}), skipping OCR")
                doc.ocr_status = "completed"
                doc.ocr_text = ""  # Non-PDF, no OCR needed
                db_session.commit()
                return

            # Extract text
            result = self.extract_text_from_pdf(file_path)

            # Sanitize text: remove NUL characters that PostgreSQL rejects
            sanitized_text = result["text"].replace('\x00', '') if result["text"] else ""

            # Update document
            doc.ocr_text = sanitized_text[:50000]  # Limit to 50k chars to avoid DB bloat
            doc.ocr_confidence = result["confidence"]
            doc.ocr_language = "en"  # English for now
            doc.ocr_processed_at = datetime.now()

            if result["method"] == "failed":
                doc.ocr_status = "failed"
                logger.error(
                    f"OCR failed for document {document_id} ({doc.name}): {result.get('error')}"
                )
            else:
                doc.ocr_status = "completed"
                logger.info(
                    f"OCR completed for document {document_id} ({doc.name}): "
                    f"{len(result['text'])} chars, method={result['method']}, "
                    f"confidence={result['confidence']:.2f}"
                )

            db_session.commit()

        except Exception as e:
            logger.exception(f"OCR processing failed for document {document_id}")
            doc.ocr_status = "failed"
            db_session.commit()

    def get_pending_count(self, db_session) -> int:
        """
        Get count of documents pending OCR processing.

        Args:
            db_session: SQLAlchemy database session

        Returns:
            Number of documents with ocr_status='pending'
        """
        from models.document import Document
        from sqlalchemy import func

        count = db_session.query(func.count(Document.id)).filter(
            Document.ocr_status == "pending",
            Document.mime_type == "application/pdf"
        ).scalar()

        return count or 0

    def get_failed_count(self, db_session) -> int:
        """
        Get count of documents that failed OCR processing.

        Args:
            db_session: SQLAlchemy database session

        Returns:
            Number of documents with ocr_status='failed'
        """
        from models.document import Document
        from sqlalchemy import func

        count = db_session.query(func.count(Document.id)).filter(
            Document.ocr_status == "failed"
        ).scalar()

        return count or 0
