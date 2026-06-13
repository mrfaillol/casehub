#!/usr/bin/env python3
"""
CaseHub - Batch Document Reprocessing Script

Reprocesses existing documents to populate new V2 schema fields:
- content_hash: SHA256 hash for deduplication
- ocr_text: Extracted text from PDFs
- duplicate_of: Links to original document if duplicate

Usage:
    python batch_reprocess_documents.py --mode hash --limit 100
    python batch_reprocess_documents.py --mode ocr --client-id 42
    python batch_reprocess_documents.py --mode dedupe

Created: 2026-02-27
Estimated runtime: 8-12 hours for full processing
"""

import asyncio
import argparse
import sys
import logging
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from sqlalchemy import func

# Import models and services
try:
    from models.base import get_db
    from models.document import Document
    from services.ocr_service import OCRService
    from services.file_storage import FileStorageService
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure you're running this from the casehub directory")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('batch_reprocess.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class BatchReprocessor:
    """Batch reprocessing for existing documents."""

    def __init__(self, db: Session):
        self.db = db
        self.ocr = OCRService()
        self.storage = FileStorageService()
        self.stats = {
            "processed": 0,
            "skipped": 0,
            "errors": 0,
            "start_time": datetime.now()
        }

    async def calculate_content_hashes(self, limit: int = None, skip_existing: bool = True):
        """
        Calculate content hashes for documents that don't have them.

        Args:
            limit: Maximum number of documents to process (None = all)
            skip_existing: Skip documents that already have content_hash
        """
        logger.info("=" * 80)
        logger.info("PHASE 1: Calculate Content Hashes")
        logger.info("=" * 80)

        # Build query
        query = self.db.query(Document)

        if skip_existing:
            query = query.filter(Document.content_hash == None)

        # Order by ID for consistent processing
        query = query.order_by(Document.id)

        if limit:
            query = query.limit(limit)

        docs = query.all()
        total = len(docs)

        if total == 0:
            logger.info("No documents to process (all have content_hash)")
            return

        logger.info(f"Processing {total} documents...")

        for idx, doc in enumerate(docs, 1):
            try:
                # Get file path (try new storage_path first, fallback to file_path)
                file_path = Path(doc.storage_path or doc.file_path)

                if not file_path.exists():
                    logger.warning(
                        f"[{idx}/{total}] Document {doc.id} ({doc.name}): "
                        f"File not found at {file_path}"
                    )
                    self.stats["skipped"] += 1
                    continue

                # Calculate hash
                content_hash = self.storage.calculate_hash(file_path)
                doc.content_hash = content_hash
                self.db.commit()

                self.stats["processed"] += 1

                if idx % 100 == 0:  # Progress update every 100 docs
                    elapsed = (datetime.now() - self.stats["start_time"]).total_seconds()
                    rate = idx / elapsed
                    eta_seconds = (total - idx) / rate if rate > 0 else 0
                    logger.info(
                        f"[{idx}/{total}] Progress: {idx/total*100:.1f}% | "
                        f"Rate: {rate:.1f} docs/s | ETA: {eta_seconds/60:.1f} min"
                    )

                logger.debug(
                    f"[{idx}/{total}] Document {doc.id} ({doc.name}): "
                    f"Hash = {content_hash[:16]}..."
                )

            except Exception as e:
                logger.error(f"[{idx}/{total}] Hash calculation failed for doc {doc.id}: {e}")
                self.stats["errors"] += 1

        logger.info(f"✅ Phase 1 complete: {self.stats['processed']} hashes calculated")

    async def detect_duplicates(self):
        """
        Detect and link duplicate documents by content hash.

        Sets duplicate_of field to point to original document.
        """
        logger.info("=" * 80)
        logger.info("PHASE 2: Detect Duplicates")
        logger.info("=" * 80)

        # Find all content hashes with multiple documents
        duplicates = self.db.query(
            Document.content_hash,
            func.count(Document.id).label('count'),
            func.min(Document.id).label('original_id')
        ).filter(
            Document.content_hash != None
        ).group_by(
            Document.content_hash
        ).having(
            func.count(Document.id) > 1
        ).all()

        if not duplicates:
            logger.info("No duplicates found")
            return

        logger.info(f"Found {len(duplicates)} sets of duplicate documents")

        total_duplicates = 0

        for content_hash, count, original_id in duplicates:
            # Mark all except original as duplicates
            dups = self.db.query(Document).filter(
                Document.content_hash == content_hash,
                Document.id != original_id
            ).all()

            logger.info(
                f"Hash {content_hash[:16]}... has {count} copies "
                f"(original: doc {original_id})"
            )

            for dup in dups:
                dup.duplicate_of = original_id
                logger.info(f"  → Document {dup.id} ({dup.name}) marked as duplicate")
                total_duplicates += 1

            self.db.commit()

        logger.info(f"✅ Phase 2 complete: {total_duplicates} duplicates linked")

    async def reprocess_ocr(
        self,
        limit: int = None,
        client_id: int = None,
        skip_completed: bool = True
    ):
        """
        Run OCR on documents that don't have OCR text yet.

        Args:
            limit: Maximum number of documents to process
            client_id: Process only documents for specific client
            skip_completed: Skip documents with ocr_status='completed'
        """
        logger.info("=" * 80)
        logger.info("PHASE 3: OCR Processing")
        logger.info("=" * 80)

        # Build query
        query = self.db.query(Document).filter(
            Document.mime_type == 'application/pdf'
        )

        if skip_completed:
            query = query.filter(Document.ocr_status.in_(['pending', 'failed']))

        if client_id:
            query = query.filter(Document.client_id == client_id)

        query = query.order_by(Document.id)

        if limit:
            query = query.limit(limit)

        docs = query.all()
        total = len(docs)

        if total == 0:
            logger.info("No documents to process (all have OCR)")
            return

        logger.info(f"Processing OCR for {total} PDF documents...")

        for idx, doc in enumerate(docs, 1):
            try:
                logger.info(f"[{idx}/{total}] Processing document {doc.id} ({doc.name})")

                # Run OCR (synchronous version for batch processing)
                await self.ocr.process_document_async(doc.id, self.db)

                self.stats["processed"] += 1

                # Small delay to avoid overwhelming system
                await asyncio.sleep(0.5)

                if idx % 10 == 0:  # Progress update every 10 docs
                    elapsed = (datetime.now() - self.stats["start_time"]).total_seconds()
                    rate = idx / elapsed
                    eta_seconds = (total - idx) / rate if rate > 0 else 0
                    logger.info(
                        f"[{idx}/{total}] Progress: {idx/total*100:.1f}% | "
                        f"Rate: {rate:.2f} docs/s | ETA: {eta_seconds/60:.1f} min"
                    )

            except Exception as e:
                logger.error(f"[{idx}/{total}] OCR failed for doc {doc.id}: {e}")
                self.stats["errors"] += 1

        logger.info(f"✅ Phase 3 complete: {self.stats['processed']} documents processed")

    def print_statistics(self):
        """Print final statistics."""
        elapsed = (datetime.now() - self.stats["start_time"]).total_seconds()

        logger.info("=" * 80)
        logger.info("FINAL STATISTICS")
        logger.info("=" * 80)
        logger.info(f"Processed:  {self.stats['processed']}")
        logger.info(f"Skipped:    {self.stats['skipped']}")
        logger.info(f"Errors:     {self.stats['errors']}")
        logger.info(f"Total time: {elapsed/60:.1f} minutes ({elapsed/3600:.2f} hours)")
        logger.info("=" * 80)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Batch reprocess documents for CaseHub V2 schema"
    )
    parser.add_argument(
        "--mode",
        choices=["hash", "ocr", "dedupe", "all"],
        required=True,
        help="Processing mode: hash (calculate hashes), ocr (run OCR), dedupe (detect duplicates), all (run all phases)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of documents to process (for testing)"
    )
    parser.add_argument(
        "--client-id",
        type=int,
        help="Process only documents for specific client ID"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess even if already processed (don't skip existing)"
    )

    args = parser.parse_args()

    # Get database session
    db = next(get_db())

    # Create reprocessor
    reprocessor = BatchReprocessor(db)

    try:
        # Run requested mode
        if args.mode == "hash" or args.mode == "all":
            await reprocessor.calculate_content_hashes(
                limit=args.limit,
                skip_existing=not args.force
            )

        if args.mode == "dedupe" or args.mode == "all":
            await reprocessor.detect_duplicates()

        if args.mode == "ocr" or args.mode == "all":
            await reprocessor.reprocess_ocr(
                limit=args.limit,
                client_id=args.client_id,
                skip_completed=not args.force
            )

        # Print final statistics
        reprocessor.print_statistics()

    except KeyboardInterrupt:
        logger.warning("\n⚠️  Interrupted by user")
        reprocessor.print_statistics()
        sys.exit(1)

    except Exception as e:
        logger.exception(f"❌ Fatal error: {e}")
        reprocessor.print_statistics()
        sys.exit(1)

    logger.info("✅ Batch processing complete!")


if __name__ == "__main__":
    asyncio.run(main())
