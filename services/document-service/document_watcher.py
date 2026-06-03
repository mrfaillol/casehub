#!/usr/bin/env python3
"""
Document Watcher - Monitors directories for new uploads and classifies them.
Runs as a PM2 service on VPS.
"""

import os
import sys
import time
import json
import shutil
import logging
import psycopg2
from pathlib import Path
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from document_classifier import classify_document, ClassificationResult, EmailContext

# Configuration
WATCH_DIRS = [
    os.getenv("APP_BASE_PATH", "/opt/casehub") + "/casehub/uploads/email_attachments",
    os.getenv("APP_BASE_PATH", "/opt/casehub") + "/documents/clients/_incoming",
    os.getenv("APP_BASE_PATH", "/opt/casehub") + "/client-intake/uploads",
]
DOCUMENTS_BASE = Path(os.getenv("APP_BASE_PATH", "/opt/casehub") + "/documents/clients")
LOG_FILE = "/var/log/document-service/watcher.log"
CLASSIFICATION_LOG = "/var/log/document-service/classification.log"

# Database
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "casehub"),
    "user": os.getenv("DB_USER", "casehub"),
    "password": os.getenv("DB_PASSWORD", ""),
}

# Ensure log directory exists
Path("/var/log/document-service").mkdir(parents=True, exist_ok=True)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Classification logger (separate file for auditing)
class_logger = logging.getLogger('classification')
class_logger.addHandler(logging.FileHandler(CLASSIFICATION_LOG))
class_logger.setLevel(logging.INFO)


def get_db_connection():
    """Get database connection."""
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return None


def get_client_info(file_path: str) -> dict:
    """Extract client info from file path or metadata."""
    path = Path(file_path)

    # Try to find client folder in path
    for parent in path.parents:
        if parent.parent == DOCUMENTS_BASE:
            # Folder format: "LASTNAME, Firstname - VISA"
            folder_name = parent.name
            parts = folder_name.split(' - ')
            if len(parts) >= 2:
                return {
                    "name": parts[0],
                    "visa_category": parts[1] if len(parts) > 1 else "Unknown",
                    "folder": folder_name
                }

    # Try to get from email_attachments metadata
    meta_file = path.parent / f".{path.name}.meta.json"
    if meta_file.exists():
        try:
            with open(meta_file) as f:
                meta = json.load(f)
                return {
                    "name": meta.get("client_name", "Unknown"),
                    "visa_category": meta.get("visa_category", "Unknown"),
                    "folder": meta.get("client_folder", ""),
                    "email_context": meta.get("email_context")
                }
        except Exception:
            pass

    return {"name": "Unknown", "visa_category": "Unknown", "folder": ""}


def get_email_context_from_meta(file_path: str) -> EmailContext:
    """Get email context from metadata file if available."""
    path = Path(file_path)
    meta_file = path.parent / f".{path.name}.meta.json"

    if meta_file.exists():
        try:
            with open(meta_file) as f:
                meta = json.load(f)
                ec = meta.get("email_context", {})
                if ec:
                    return EmailContext(
                        message_id=ec.get("message_id", ""),
                        subject=ec.get("subject", ""),
                        body_preview=ec.get("body_preview", ""),
                        sender=ec.get("sender", "")
                    )
        except Exception:
            pass
    return None


def get_target_folder(client_info: dict, doc_type: str) -> Path:
    """Determine target folder for document."""
    client_folder = client_info.get("folder", "")

    if not client_folder:
        # Put in _unknown for manual review
        return DOCUMENTS_BASE / "_unknown" / doc_type

    base_folder = DOCUMENTS_BASE / client_folder

    # Subfolder mapping
    subfolder_map = {
        "Passaporte": "Personal Documents",
        "I-94": "Personal Documents",
        "Visa": "Personal Documents",
        "EAD Card": "Personal Documents",
        "Green Card": "Personal Documents",
        "Birth Certificate": "Personal Documents",
        "Marriage Certificate": "Personal Documents",
        "Photo": "Personal Documents",
        "Diploma": "Education",
        "Transcript": "Education",
        "Credential Evaluation": "Education",
        "Resume": "Resume",
        "Employment Letter": "Employment",
        "Pay Stub": "Employment",
        "Tax": "Tax",
        "LOR": "LOR",
        "Publication": "Publications",
        "Citation": "Publications",
        "Award": "Awards",
        "Media Coverage": "Media",
        "Membership": "Memberships",
        "USCIS Form": "USCIS Forms",
        "Receipt Notice": "USCIS Forms",
        "RFE": "USCIS Forms",
        "Approval Notice": "USCIS Forms",
        "Brief": "Brief",
        "Exhibit": "Exhibits",
        "Case Admin": "Case Admin",
        "Questionnaire": "Questionnaire",
        "Retainer": "Retainer",
        "Outro": "Outros",
    }

    subfolder = subfolder_map.get(doc_type, "Outros")
    return base_folder / subfolder


def move_document(src_path: Path, dst_folder: Path, new_name: str) -> Path:
    """Move document to target folder with new name."""
    dst_folder.mkdir(parents=True, exist_ok=True)
    dst_path = dst_folder / new_name

    # Handle duplicates
    if dst_path.exists():
        stem = dst_path.stem
        suffix = dst_path.suffix
        counter = 1
        while dst_path.exists():
            dst_path = dst_folder / f"{stem}_{counter}{suffix}"
            counter += 1

    shutil.move(str(src_path), str(dst_path))
    return dst_path


def update_database(client_info: dict, classification: ClassificationResult,
                    original_path: str, new_path: str):
    """Update database with document record."""
    conn = get_db_connection()
    if not conn:
        return

    try:
        cur = conn.cursor()

        # Check if documents table exists and has right columns
        # First find client/case IDs
        cur.execute("""
            SELECT c.id as client_id, cs.id as case_id
            FROM clients c
            LEFT JOIN cases cs ON cs.client_id = c.id
            WHERE c.first_name || ' ' || c.last_name ILIKE %s
               OR c.last_name || ', ' || c.first_name ILIKE %s
            LIMIT 1
        """, (
            f"%{client_info.get('name', '')}%",
            f"%{client_info.get('name', '')}%"
        ))
        row = cur.fetchone()
        client_id = row[0] if row else None
        case_id = row[1] if row else None
        
        # Insert document with correct column names
        cur.execute("""
            INSERT INTO documents (
                name, doc_type, file_path, original_filename,
                llm_classified, classification_confidence,
                client_id, case_id, status, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'received', NOW())
        """, (
            Path(new_path).name,
            classification.document_type,
            str(new_path),
            Path(original_path).name,
            classification.method == 'llm',
            classification.confidence,
            client_id,
            case_id
        ))

        conn.commit()
        logger.info(f"Database updated for: {Path(original_path).name}")
    except Exception as e:
        logger.error(f"Database update failed: {e}")
        conn.rollback()
    finally:
        conn.close()


def log_classification(original_path: str, new_path: str,
                       classification: ClassificationResult,
                       client_info: dict):
    """Log classification for auditing."""
    record = {
        "timestamp": datetime.now().isoformat(),
        "original_path": original_path,
        "new_path": str(new_path),
        "document_type": classification.document_type,
        "confidence": classification.confidence,
        "method": classification.method,
        "client": client_info.get("name", "Unknown")
    }
    class_logger.info(json.dumps(record))


class DocumentHandler(FileSystemEventHandler):
    """Handle new file events."""

    def __init__(self):
        self.processing = set()

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = event.src_path

        # Skip metadata files and temp files
        if Path(file_path).name.startswith('.') or file_path.endswith('.tmp'):
            return

        # Skip if already processing
        if file_path in self.processing:
            return

        self.processing.add(file_path)

        try:
            # Wait for file to be fully written
            time.sleep(2)

            if not Path(file_path).exists():
                return

            self.process_document(file_path)
        finally:
            self.processing.discard(file_path)

    def process_document(self, file_path: str):
        """Process a new document."""
        logger.info(f"Processing: {file_path}")

        try:
            path = Path(file_path)
            filename = path.name

            # Get client info
            client_info = get_client_info(file_path)
            logger.info(f"Client info: {client_info}")

            # Get email context if available
            email_ctx = get_email_context_from_meta(file_path)

            # Classify document
            classification = classify_document(
                filename=filename,
                client_name=client_info.get("name", ""),
                visa_category=client_info.get("visa_category", ""),
                email_ctx=email_ctx
            )

            logger.info(f"Classification: {classification.document_type} "
                       f"(confidence={classification.confidence}, method={classification.method})")

            # Determine target folder
            target_folder = get_target_folder(client_info, classification.document_type)

            # Generate new name
            new_name = f"{classification.document_type} - {client_info.get('name', 'Unknown')}{path.suffix}"

            # Move document
            new_path = move_document(path, target_folder, new_name)
            logger.info(f"Moved to: {new_path}")

            # Update database
            update_database(client_info, classification, file_path, new_path)

            # Log classification
            log_classification(file_path, new_path, classification, client_info)

        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")


def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("Document Watcher Service Starting")
    logger.info("=" * 60)

    # Ensure watch directories exist
    for watch_dir in WATCH_DIRS:
        Path(watch_dir).mkdir(parents=True, exist_ok=True)
        logger.info(f"Watching: {watch_dir}")

    # Set up observer
    event_handler = DocumentHandler()
    observer = Observer()

    for watch_dir in WATCH_DIRS:
        observer.schedule(event_handler, watch_dir, recursive=True)

    observer.start()
    logger.info("Observer started. Waiting for new documents...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logger.info("Shutting down...")

    observer.join()


if __name__ == "__main__":
    main()
