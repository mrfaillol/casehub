#!/usr/bin/env python3
"""
CaseHub - Batch Document Re-classification Script

Re-classifies documents (especially "Other Document") using OCR text for better accuracy.
Uses the Enhanced Classifier V2 with multi-LLM chain.

Usage:
    python batch_reclassify_documents.py --filter outro --limit 100
    python batch_reclassify_documents.py --all
    python batch_reclassify_documents.py --low-confidence

Created: 2026-03-02
Runs after batch_reprocess_documents.py OCR phase completes
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
    from services.document_classifier import classify_with_ocr
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure you're running this from the casehub directory")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('batch_reclassify.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class BatchReclassifier:
    """Batch re-classification for existing documents."""

    def __init__(self, db: Session):
        self.db = db
        self.stats = {
            "processed": 0,
            "reclassified": 0,  # Changed from "Other Document" to something else
            "kept_same": 0,     # Classification stayed the same
            "errors": 0,
            "skipped": 0,       # No OCR text available
            "start_time": datetime.now()
        }
        self.category_changes = {}  # Track Other Document -> NewCategory counts

    async def reclassify_documents(
        self,
        filter_type: str = "outro",
        limit: int = None,
        skip_without_ocr: bool = True
    ):
        """
        Re-classify documents using OCR text.

        Args:
            filter_type: "outro" (only "Other Document" docs), "all" (all docs), "low-confidence" (confidence < 0.7)
            limit: Maximum number of documents to process (None = all)
            skip_without_ocr: Skip documents that don't have OCR text yet
        """
        logger.info("=" * 80)
        logger.info("BATCH RE-CLASSIFICATION")
        logger.info("=" * 80)

        # Build query based on filter
        query = self.db.query(Document)

        if filter_type == "outro":
            query = query.filter(Document.doc_type == "Other Document")
            logger.info("Filter: Only documents classified as 'Other Document'")
        elif filter_type == "low-confidence":
            query = query.filter(Document.classification_confidence < 0.7)
            logger.info("Filter: Only low-confidence classifications (< 0.7)")
        elif filter_type == "all":
            logger.info("Filter: ALL documents")
        else:
            logger.error(f"Unknown filter type: {filter_type}")
            return

        if skip_without_ocr:
            query = query.filter(
                Document.ocr_text != None,
                Document.ocr_text != ""
            )

        # Order by ID for consistent processing
        query = query.order_by(Document.id)

        if limit:
            query = query.limit(limit)

        docs = query.all()
        total = len(docs)

        if total == 0:
            logger.info("No documents to process")
            return

        logger.info(f"Processing {total} documents...")

        for idx, doc in enumerate(docs, 1):
            try:
                old_type = doc.doc_type
                old_confidence = doc.classification_confidence or 0.0

                logger.info(
                    f"[{idx}/{total}] Document {doc.id} ({doc.name}): "
                    f"Current={old_type} (conf={old_confidence:.2f})"
                )

                # Check if OCR text is available
                if not doc.ocr_text or len(doc.ocr_text.strip()) < 50:
                    logger.warning(
                        f"[{idx}/{total}] Document {doc.id}: Insufficient OCR text "
                        f"({len(doc.ocr_text or '')} chars), skipping"
                    )
                    self.stats["skipped"] += 1
                    continue

                # Run enhanced classification with OCR text
                result = await classify_with_ocr(doc.id, self.db)

                if "error" in result:
                    if result.get("retry"):
                        logger.warning(f"[{idx}/{total}] OCR not ready yet, skipping")
                        self.stats["skipped"] += 1
                    else:
                        logger.error(f"[{idx}/{total}] Classification error: {result['error']}")
                        self.stats["errors"] += 1
                    continue

                new_type = result.get("doc_type", old_type)
                new_confidence = result.get("confidence", old_confidence)

                # Update document if classification changed
                if new_type != old_type:
                    doc.doc_type = new_type
                    doc.classification_confidence = new_confidence
                    doc.llm_classified = True
                    self.db.commit()

                    # Track category change
                    change_key = f"{old_type} → {new_type}"
                    self.category_changes[change_key] = self.category_changes.get(change_key, 0) + 1

                    logger.info(
                        f"[{idx}/{total}] ✅ RECLASSIFIED: {old_type} → {new_type} "
                        f"(conf: {old_confidence:.2f} → {new_confidence:.2f})"
                    )
                    self.stats["reclassified"] += 1
                else:
                    # Classification stayed the same (but maybe confidence improved)
                    if new_confidence != old_confidence:
                        doc.classification_confidence = new_confidence
                        doc.llm_classified = True
                        self.db.commit()

                    logger.info(
                        f"[{idx}/{total}] Kept same: {old_type} "
                        f"(conf: {old_confidence:.2f} → {new_confidence:.2f})"
                    )
                    self.stats["kept_same"] += 1

                self.stats["processed"] += 1

                # Progress update every 50 docs
                if idx % 50 == 0:
                    elapsed = (datetime.now() - self.stats["start_time"]).total_seconds()
                    rate = idx / elapsed
                    eta_seconds = (total - idx) / rate if rate > 0 else 0
                    logger.info(
                        f"[{idx}/{total}] Progress: {idx/total*100:.1f}% | "
                        f"Rate: {rate:.2f} docs/s | ETA: {eta_seconds/60:.1f} min"
                    )

                # Small delay to avoid overwhelming LLM APIs
                await asyncio.sleep(1.0)

            except Exception as e:
                logger.error(f"[{idx}/{total}] Re-classification failed for doc {doc.id}: {e}")
                self.stats["errors"] += 1
                # Rollback transaction to continue with next doc
                self.db.rollback()

        logger.info(f"✅ Re-classification complete: {self.stats['reclassified']} documents reclassified")

    def print_statistics(self):
        """Print final statistics."""
        elapsed = (datetime.now() - self.stats["start_time"]).total_seconds()

        logger.info("=" * 80)
        logger.info("FINAL STATISTICS")
        logger.info("=" * 80)
        logger.info(f"Processed:     {self.stats['processed']}")
        logger.info(f"Reclassified:  {self.stats['reclassified']}")
        logger.info(f"Kept same:     {self.stats['kept_same']}")
        logger.info(f"Skipped:       {self.stats['skipped']}")
        logger.info(f"Errors:        {self.stats['errors']}")
        logger.info(f"Total time:    {elapsed/60:.1f} minutes ({elapsed/3600:.2f} hours)")
        logger.info("=" * 80)

        if self.category_changes:
            logger.info("")
            logger.info("CATEGORY CHANGES:")
            logger.info("-" * 80)
            for change, count in sorted(self.category_changes.items(), key=lambda x: x[1], reverse=True):
                logger.info(f"  {change}: {count} documents")
            logger.info("=" * 80)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Batch re-classify documents using OCR text"
    )
    parser.add_argument(
        "--filter",
        choices=["outro", "all", "low-confidence"],
        default="outro",
        help="Filter documents: outro (only 'Other Document'), all (all docs), low-confidence (conf < 0.7)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of documents to process (for testing)"
    )
    parser.add_argument(
        "--include-no-ocr",
        action="store_true",
        help="Include documents without OCR text (will skip them with warning)"
    )

    args = parser.parse_args()

    # Get database session
    db = next(get_db())

    # Create reclassifier
    reclassifier = BatchReclassifier(db)

    try:
        # Run re-classification
        await reclassifier.reclassify_documents(
            filter_type=args.filter,
            limit=args.limit,
            skip_without_ocr=not args.include_no_ocr
        )

        # Print final statistics
        reclassifier.print_statistics()

    except KeyboardInterrupt:
        logger.warning("\n⚠️  Interrupted by user")
        reclassifier.print_statistics()
        sys.exit(1)

    except Exception as e:
        logger.exception(f"❌ Fatal error: {e}")
        reclassifier.print_statistics()
        sys.exit(1)

    logger.info("✅ Batch re-classification complete!")


if __name__ == "__main__":
    asyncio.run(main())
