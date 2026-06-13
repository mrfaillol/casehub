#!/usr/bin/env python3
"""
CaseHub - Intelligent Document Re-classification Script

Multi-phase intelligent re-classification for "Outro" documents:
- Phase 1: Re-classify PDFs with OCR text using LLM
- Phase 2: Context-based classification for non-PDFs (images, etc)
- Phase 3: Dynamic category suggestion based on patterns

Usage:
    python intelligent_reclassifier.py --phase 1 --limit 100
    python intelligent_reclassifier.py --phase 2 --dry-run
    python intelligent_reclassifier.py --phase 3
    python intelligent_reclassifier.py --all

Created: 2026-03-02
Purpose: Reduce "Outro" documents from 4,950 to <500 using intelligent classification
"""

import asyncio
import argparse
import sys
import logging
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from sqlalchemy import func

# Import models and services
try:
    from models.base import get_db
    from models.document import Document
    from models.client import Client
    from models.case import Case
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
        logging.FileHandler('intelligent_reclassify.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# Enhanced categories mapping - ALL IN ENGLISH (for Client Portal)
# Updated: 2026-03-03 - Aligned with migration 2026-03-03_standardize_categories_english.sql
ENHANCED_CATEGORIES = {
    # Personal Documents
    "Passport": ["passport", "passaport", "passaporte", "pasaporte"],
    "I-94 Travel Record": ["i-94", "i94", "arrival", "departure", "travel record"],
    "Visa": ["visa", "stamp", "visto"],
    "EAD Card": ["ead", "employment authorization", "work permit"],
    "Green Card": ["green card", "permanent resident", "i-551"],
    "Birth Certificate": ["birth certificate", "certidão de nascimento", "certidao nascimento"],
    "Marriage Certificate": ["marriage certificate", "certidão de casamento", "certidao casamento"],
    "Photo": ["photo", "photograph", "image", "picture", "foto"],

    # Educational Documents
    "Diploma": ["diploma", "degree", "graduation", "graduacao"],
    "Academic Transcript": ["transcript", "histórico escolar", "historico", "academic record", "grades"],
    "Credential Evaluation": ["credential eval", "wes", "evaluation", "avaliacao"],

    # Professional Documents
    "Resume/CV": ["cv", "resume", "curriculum", "curriculo"],
    "Letter of Recommendation": ["recommendation", "reference letter", "carta de recomendação", "lor", "recomendacao"],
    "Employment Letter": ["employment letter", "job offer", "carta de emprego", "work letter"],
    "Employment Contract": ["contract", "agreement", "contrato", "employment agreement"],
    "Award/Recognition": ["award", "recognition", "prize", "premio", "reconhecimento"],
    "Professional Membership": ["membership", "association", "society", "associacao"],
    "Publication": ["publication", "article", "paper", "journal", "publicacao"],
    "Portfolio/Work Samples": ["portfolio", "work sample", "sample", "artwork", "design"],

    # Financial Documents
    "Tax Return": ["tax return", "1040", "w-2", "imposto de renda", "tax document"],
    "Financial Statement": ["financial", "assets", "savings", "investment", "bank", "extrato"],
    "Pay Stub": ["pay stub", "paycheck", "holerite", "contracheque", "payment"],

    # Immigration Documents
    "USCIS Form": ["i-129", "i-140", "i-485", "i-765", "form ", "petition", "application", "uscis"],
    "Receipt Notice": ["receipt", "i-797", "recibo"],
    "Approval Notice": ["approval", "approved", "aprovacao"],
    "Request for Evidence": ["rfe", "request for evidence", "solicitacao"],
    "Supporting Evidence": ["evidence", "proof", "supporting", "evidencia", "prova"],
    "Personal Statement": ["statement", "letter", "declaracao", "carta"],

    # Additional Categories
    "Medical Records": ["medical", "exam", "vaccination", "health", "doctor", "medico"],
    "Police Certificate": ["police", "criminal", "background check", "antecedentes", "certidao"],
    "Cover Letter": ["cover letter", "carta de apresentação", "apresentacao"],
    "Affidavit": ["affidavit", "sworn statement", "declaração jurada"],

    # Fallback
    "Other Document": ["other", "outro", "misc", "additional", "supplemental"],
}


class IntelligentReclassifier:
    """Intelligent multi-phase document re-classification."""

    def __init__(self, db: Session):
        self.db = db
        self.stats = {
            "processed": 0,
            "reclassified": 0,
            "kept_outro": 0,
            "errors": 0,
            "skipped": 0,
            "start_time": datetime.now()
        }
        self.category_changes = {}
        self.new_categories_suggested = Counter()
        self.context_patterns = defaultdict(list)

    async def phase1_pdf_ocr_reclassification(
        self,
        limit: int = None,
        dry_run: bool = False
    ):
        """
        Phase 1: Re-classify "Outro" PDFs that have OCR text.

        Uses enhanced classifier with OCR text and multi-LLM chain.
        """
        logger.info("=" * 80)
        logger.info("PHASE 1: PDF OCR Re-classification")
        logger.info("=" * 80)

        # Query "Other Document" PDFs with OCR text
        # NOTE: After migration, "Outro" becomes "Other Document"
        query = self.db.query(Document).filter(
            Document.doc_type == "Other Document",
            Document.mime_type == "application/pdf",
            Document.ocr_status == "completed",
            Document.ocr_text != None,
            Document.ocr_text != ""
        ).order_by(Document.id)

        if limit:
            query = query.limit(limit)

        docs = query.all()
        total = len(docs)

        if total == 0:
            logger.info("No PDFs with OCR text to process")
            return

        logger.info(f"Processing {total} PDFs with OCR text...")

        for idx, doc in enumerate(docs, 1):
            try:
                old_type = doc.doc_type

                logger.info(
                    f"[{idx}/{total}] Document {doc.id} ({doc.name}): "
                    f"OCR chars={len(doc.ocr_text or '')}"
                )

                if dry_run:
                    logger.info(f"  [DRY RUN] Would re-classify using OCR")
                    self.stats["skipped"] += 1
                    continue

                # Run enhanced classification with OCR text
                result = await classify_with_ocr(doc.id, self.db)

                if "error" in result:
                    logger.error(f"[{idx}/{total}] Classification error: {result['error']}")
                    self.stats["errors"] += 1
                    continue

                new_type = result.get("doc_type", old_type)
                new_confidence = result.get("confidence", 0.0)

                # Update document if classification changed
                if new_type != old_type and new_type != "Other Document":
                    doc.doc_type = new_type
                    doc.classification_confidence = new_confidence
                    doc.llm_classified = True
                    self.db.commit()

                    change_key = f"{old_type} → {new_type}"
                    self.category_changes[change_key] = self.category_changes.get(change_key, 0) + 1

                    logger.info(
                        f"[{idx}/{total}] ✅ RECLASSIFIED: {old_type} → {new_type} "
                        f"(conf: {new_confidence:.2f})"
                    )
                    self.stats["reclassified"] += 1
                else:
                    logger.info(f"[{idx}/{total}] Kept as: {new_type}")
                    self.stats["kept_outro"] += 1

                self.stats["processed"] += 1

                # Progress update every 50 docs
                if idx % 50 == 0:
                    elapsed = (datetime.now() - self.stats["start_time"]).total_seconds()
                    rate = idx / elapsed if elapsed > 0 else 0
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
                self.db.rollback()

        logger.info(f"✅ Phase 1 complete: {self.stats['reclassified']} documents reclassified")

    async def phase2_context_based_classification(
        self,
        limit: int = None,
        dry_run: bool = False
    ):
        """
        Phase 2: Context-based classification for non-PDFs (images, etc).

        Uses:
        - Client's visa category (O-1 → Portfolio, H-1B → Employment docs)
        - Case type and status
        - Upload date and sequence
        - Patterns from other documents of same client
        """
        logger.info("=" * 80)
        logger.info("PHASE 2: Context-Based Classification (Non-PDFs)")
        logger.info("=" * 80)

        # Query "Other Document" non-PDFs
        # NOTE: After migration, "Outro" becomes "Other Document"
        query = self.db.query(Document).filter(
            Document.doc_type == "Other Document",
            Document.mime_type != "application/pdf"
        ).order_by(Document.client_id, Document.created_at)

        if limit:
            query = query.limit(limit)

        docs = query.all()
        total = len(docs)

        if total == 0:
            logger.info("No non-PDFs to process")
            return

        logger.info(f"Processing {total} non-PDF documents using context...")

        for idx, doc in enumerate(docs, 1):
            try:
                old_type = doc.doc_type

                # Get client and case context
                client = doc.client if doc.client else None
                case = doc.case if doc.case else None

                logger.info(
                    f"[{idx}/{total}] Document {doc.id} ({doc.name}): "
                    f"Client={client.id if client else 'N/A'}, "
                    f"Mime={doc.mime_type}"
                )

                if dry_run:
                    logger.info(f"  [DRY RUN] Would classify by context")
                    self.stats["skipped"] += 1
                    continue

                # Classify based on context
                new_type = self._classify_by_context(doc, client, case)

                if new_type and new_type != old_type:
                    doc.doc_type = new_type
                    doc.classification_confidence = 0.7  # Medium confidence for context-based
                    doc.llm_classified = False  # Mark as rule-based, not LLM
                    self.db.commit()

                    change_key = f"{old_type} → {new_type}"
                    self.category_changes[change_key] = self.category_changes.get(change_key, 0) + 1

                    logger.info(
                        f"[{idx}/{total}] ✅ RECLASSIFIED (context): {old_type} → {new_type}"
                    )
                    self.stats["reclassified"] += 1
                else:
                    logger.info(f"[{idx}/{total}] No context match, kept as Other Document")
                    self.stats["kept_outro"] += 1

                self.stats["processed"] += 1

                # Progress update every 100 docs
                if idx % 100 == 0:
                    elapsed = (datetime.now() - self.stats["start_time"]).total_seconds()
                    rate = idx / elapsed if elapsed > 0 else 0
                    eta_seconds = (total - idx) / rate if rate > 0 else 0
                    logger.info(
                        f"[{idx}/{total}] Progress: {idx/total*100:.1f}% | "
                        f"Rate: {rate:.2f} docs/s | ETA: {eta_seconds/60:.1f} min"
                    )

            except Exception as e:
                logger.error(f"[{idx}/{total}] Context classification failed for doc {doc.id}: {e}")
                self.stats["errors"] += 1
                self.db.rollback()

        logger.info(f"✅ Phase 2 complete: {self.stats['reclassified']} documents reclassified by context")

    def _classify_by_context(self, doc: Document, client, case) -> str:
        """
        Classify document based on context (visa category, case type, mime type).

        Returns:
            Category name or None if no match
        """
        # Check filename patterns first
        name_lower = doc.name.lower()

        for category, keywords in ENHANCED_CATEGORIES.items():
            if any(keyword in name_lower for keyword in keywords):
                return category

        # If no filename match, use client/case context
        if case and hasattr(case, 'visa_category'):
            visa_cat = case.visa_category or ""

            # O-1 visa → likely Portfolio/Evidence for images
            if "O-1" in visa_cat or "EB-1" in visa_cat:
                if doc.mime_type in ["image/jpeg", "image/png", "image/gif"]:
                    return "Portfolio/Evidence"

            # H-1B → likely Employment docs
            elif "H-1B" in visa_cat:
                if doc.mime_type in ["image/jpeg", "image/png"]:
                    return "Employment Letter"

            # Green Card / Adjustment of Status → likely supporting docs
            elif "I-485" in visa_cat or "Green Card" in visa_cat:
                return "Supporting Documents"

        # Check mime type patterns
        if doc.mime_type in ["image/jpeg", "image/png", "image/gif"]:
            # Images are likely photos if no other context
            if "photo" in name_lower or "foto" in name_lower:
                return "Photos"
            # Otherwise, could be scanned documents → Supporting Documents
            return "Supporting Documents"

        # No match found
        return None

    async def phase3_suggest_new_categories(self):
        """
        Phase 3: Analyze remaining "Other Document" documents and suggest new categories.

        Groups similar documents and suggests category names based on patterns.
        """
        logger.info("=" * 80)
        logger.info("PHASE 3: New Category Suggestion")
        logger.info("=" * 80)

        # Query remaining "Other Document" documents
        outros = self.db.query(Document).filter(
            Document.doc_type == "Other Document"
        ).all()

        if len(outros) == 0:
            logger.info("No 'Other Document' documents remaining!")
            return

        logger.info(f"Analyzing {len(outros)} remaining 'Other Document' documents...")

        # Analyze patterns
        name_patterns = Counter()
        mime_patterns = Counter()
        client_patterns = defaultdict(int)

        for doc in outros:
            # Extract potential category from filename
            name_parts = doc.name.lower().replace("-", " ").replace("_", " ").split()
            for part in name_parts:
                if len(part) > 3:  # Ignore short words
                    name_patterns[part] += 1

            # Track mime types
            mime_patterns[doc.mime_type] += 1

            # Track clients with most "Outro"
            if doc.client_id:
                client_patterns[doc.client_id] += 1

        # Suggest new categories based on patterns
        logger.info("")
        logger.info("SUGGESTED NEW CATEGORIES:")
        logger.info("-" * 80)

        for word, count in name_patterns.most_common(20):
            if count >= 10:  # Only suggest if pattern appears 10+ times
                logger.info(f"  • '{word.capitalize()}' - appears in {count} documents")
                self.new_categories_suggested[word] = count

        logger.info("")
        logger.info("MIME TYPE DISTRIBUTION:")
        logger.info("-" * 80)
        for mime, count in mime_patterns.most_common(10):
            logger.info(f"  • {mime}: {count} documents")

        logger.info("")
        logger.info("TOP CLIENTS WITH 'OUTRO' DOCUMENTS:")
        logger.info("-" * 80)
        for client_id, count in sorted(client_patterns.items(), key=lambda x: x[1], reverse=True)[:10]:
            client = self.db.query(Client).filter(Client.id == client_id).first()
            if client:
                logger.info(f"  • Client {client_id} ({client.first_name} {client.last_name}): {count} docs")

    def print_statistics(self):
        """Print final statistics."""
        elapsed = (datetime.now() - self.stats["start_time"]).total_seconds()

        logger.info("=" * 80)
        logger.info("FINAL STATISTICS")
        logger.info("=" * 80)
        logger.info(f"Processed:     {self.stats['processed']}")
        logger.info(f"Reclassified:  {self.stats['reclassified']}")
        logger.info(f"Kept as Outro: {self.stats['kept_outro']}")
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

        if self.new_categories_suggested:
            logger.info("")
            logger.info("NEW CATEGORIES SUGGESTED:")
            logger.info("-" * 80)
            for category, count in self.new_categories_suggested.most_common(10):
                logger.info(f"  • {category}: {count} occurrences")
            logger.info("=" * 80)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Intelligent multi-phase document re-classification"
    )
    parser.add_argument(
        "--phase",
        type=int,
        choices=[1, 2, 3],
        help="Run specific phase: 1 (PDF OCR), 2 (Context-based), 3 (Suggest categories)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all phases sequentially"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of documents to process (for testing)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run - show what would be done without making changes"
    )

    args = parser.parse_args()

    # Get database session
    db = next(get_db())

    # Create reclassifier
    reclassifier = IntelligentReclassifier(db)

    try:
        # Run requested phase(s)
        if args.all or args.phase == 1:
            await reclassifier.phase1_pdf_ocr_reclassification(
                limit=args.limit,
                dry_run=args.dry_run
            )

        if args.all or args.phase == 2:
            await reclassifier.phase2_context_based_classification(
                limit=args.limit,
                dry_run=args.dry_run
            )

        if args.all or args.phase == 3:
            await reclassifier.phase3_suggest_new_categories()

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

    logger.info("✅ Intelligent re-classification complete!")


if __name__ == "__main__":
    asyncio.run(main())
