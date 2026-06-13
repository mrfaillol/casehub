#!/usr/bin/env python3
"""
CaseHub - Deep Reclassification of 'Other Document' entries.

Two-phase approach using real filenames (from file_path) + LLM fallback.

Phase A1: Pattern-match reclassify using filename from file_path (no LLM needed)
    - Runs FILENAME_PATTERNS against the document name (which was updated to the real filename)
    - Instant, no API calls required
    - Sets classification_confidence = 0.7, llm_classified = False

Phase A2: LLM reclassify using Gemini for remaining 'Other Document' entries
    - Only processes documents that still have physical files (status != 'file_missing')
    - Uses OCR text when available for better accuracy
    - Calls classify_with_ocr from document_classifier.py
    - Sets llm_classified = True

Usage:
    python deep_reclassify.py --phase a1                    # Pattern matching only
    python deep_reclassify.py --phase a1 --dry-run          # Preview pattern matches
    python deep_reclassify.py --phase a2 --limit 500        # LLM classify up to 500 docs
    python deep_reclassify.py --all                         # Both phases
    python deep_reclassify.py --all --dry-run               # Preview both phases

Run on VPS:
    cd /var/www/immigrant.law/casehub && venv/bin/python scripts/deep_reclassify.py --phase a1

Created: 2026-03-04
"""

import asyncio
import argparse
import sys
import logging
from pathlib import Path
from datetime import datetime
from collections import Counter

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import models and services
try:
    from models.base import get_db
    from models.document import Document
    from models.client import Client
    from models.case import Case
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure you're running this from the casehub directory:")
    print("  cd /var/www/immigrant.law/casehub && venv/bin/python scripts/deep_reclassify.py")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('deep_reclassify.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# =============================================================================
# FILENAME_PATTERNS - Comprehensive keyword matching for document classification
# Includes English, Portuguese, and Spanish keywords.
# Order matters: more specific patterns should come first to avoid false matches.
# =============================================================================
FILENAME_PATTERNS = {
    # --- Immigration Forms (check FIRST - very specific patterns) ---
    "USCIS Form": [
        "i-129", "i-140", "i-485", "i-765", "i-131", "i-130", "i-20",
        "i-797", "i-539", "i-907", "i-821", "i-589", "n-400", "g-28",
        "g-639", "ar-11", "form ", "uscis", "510k"
    ],
    "Receipt Notice": ["receipt notice", "i-797c", "recibo"],
    "Approval Notice": ["approval notice", "approval", "approved", "aprovacao"],
    "Request for Evidence": ["rfe", "request for evidence", "solicitacao"],

    # --- Personal Identity Documents ---
    "Passport": ["passport", "pasaporte", "passaporte"],
    "I-94 Travel Record": ["i-94", "i94", "arrival", "departure", "travel record"],
    "Visa": ["visa", "visto", "stamp"],
    "EAD Card": ["ead", "employment authorization", "work permit"],
    "Green Card": ["green card", "permanent resident", "i-551"],
    "Birth Certificate": [
        "birth certificate", "certidao de nascimento",
        "certidao nascimento", "birth cert"
    ],
    "Marriage Certificate": [
        "marriage certificate", "certidao de casamento",
        "certidao casamento", "marriage cert"
    ],
    "Photo": ["photo id", "passport photo", "foto 3x4"],

    # --- Educational Documents ---
    "Diploma": [
        "diploma", "degree", "graduacao", "bachelor", "master", "phd",
        "mba", "education assessment", "education assetment"
    ],
    "Academic Transcript": [
        "transcript", "historico escolar", "historico",
        "academic record", "grades"
    ],
    "Credential Evaluation": [
        "credential eval", "wes", "evaluation report", "spantran",
        "world education services", "educational credential"
    ],

    # --- Professional Documents ---
    "Resume/CV": [
        "resume", "curriculum vitae", "curriculo",
        "cv ", "cv.", "cv-", "cv_"
    ],
    "Letter of Recommendation": [
        "recommendation", "recomendacao",
        "lor ", "lor.", "lor_", "lor-",
        "reference letter", "support letter", "endorsement letter"
    ],
    "Employment Letter": [
        "employment letter", "carta de emprego", "job letter", "offer letter",
        "employment verification", "job offer", "verification letter",
        "loa ", "loa.", "loa_", "letter of appointment"
    ],
    "Employment Contract": [
        "contract", "agreement", "contrato",
        "employment agreement"
    ],
    "Award/Recognition": [
        "award", "recognition", "prize", "premio", "reconhecimento",
        "honor", "honours", "medal", "distinction", "competition"
    ],
    "Professional Membership": [
        "membership", "association", "society", "associacao",
        "affiliation", "certification", "certified", "member"
    ],
    "Publication": [
        "publication", "article", "paper", "journal", "published",
        "publicacao", "abstract", "proceedings", "conference paper",
        "manuscript", "supply chain", "manufacturing", "sustainability"
    ],
    "Portfolio/Work Samples": [
        "portfolio", "sample", "work product", "artwork", "design",
        "patent", "provisional patent", "invention"
    ],

    # --- Financial Documents ---
    "Tax Return": [
        "tax return", "1040", "w-2", "imposto de renda",
        "tax document", "tax filing", "w2", "1099"
    ],
    "Financial Statement": [
        "financial", "assets", "savings", "investment",
        "bank statement", "extrato", "balance sheet"
    ],
    "Pay Stub": [
        "pay stub", "paycheck", "holerite", "contracheque",
        "payment", "salary", "remuneration", "pay slip",
        "folha de pagamento"
    ],

    # --- Evidence & Statements ---
    "Supporting Evidence": [
        "evidence", "proof", "supporting", "evidencia", "prova",
        "exhibit", "criteria", "legal criteria", "critical role",
        "original contribution", "judging", "peer review", "peer-review",
        "metrics", "case review"
    ],
    "Personal Statement": [
        "statement", "declaracao", "personal statement", "cover letter"
    ],

    # --- Medical & Police ---
    "Medical Records": [
        "medical", "exam", "vaccination", "health", "doctor",
        "medico", "dermatitis", "clinical"
    ],
    "Police Certificate": [
        "police", "criminal", "background check", "antecedentes"
    ],
}

# Exhibit mapping (for setting suggested_exhibit on reclassified docs)
EXHIBIT_MAP = {
    "Passport": "C", "I-94 Travel Record": "C", "Visa": "C",
    "EAD Card": "C", "Green Card": "C", "Birth Certificate": "C",
    "Marriage Certificate": "C", "Photo": "C",
    "Diploma": "C", "Academic Transcript": "C", "Credential Evaluation": "C",
    "Employment Letter": "C", "Employment Contract": "C",
    "Letter of Recommendation": "D", "Resume/CV": "C",
    "Award/Recognition": "C", "Professional Membership": "C",
    "Publication": "D", "Portfolio/Work Samples": "D",
    "Tax Return": "E", "Pay Stub": "E", "Financial Statement": "E",
    "USCIS Form": "A", "Receipt Notice": "A", "Approval Notice": "A",
    "Request for Evidence": "A",
    "Supporting Evidence": None, "Personal Statement": "D",
    "Medical Records": "C", "Police Certificate": "C",
}


class DeepReclassifier:
    """Two-phase deep reclassification of 'Other Document' entries."""

    def __init__(self, db):
        self.db = db
        self.stats = Counter()
        self.changes = Counter()
        self.start_time = datetime.now()

    # Keywords that need word-boundary checking (short/ambiguous terms)
    # These must appear as whole words, not as substrings of other words
    BOUNDARY_KEYWORDS = {
        "w-2", "w2", "cv ", "cv.", "cv-", "cv_",
        "lor ", "lor.", "lor_", "lor-",
        "loa ", "loa.", "loa_",
        "wes", "rfe", "ead",
    }

    # =========================================================================
    # Phase A1: Pattern-match reclassify using real filenames
    # =========================================================================
    def phase_a1_pattern_match(self, dry_run: bool = False):
        """
        Pattern-match reclassify using real filenames.

        For each 'Other Document', check the name column against FILENAME_PATTERNS.
        If a keyword matches, reclassify the document.
        Skips documents with generic 'Outro -' names (no useful info for matching).

        Args:
            dry_run: If True, do not commit changes - just log what would happen.
        """
        logger.info("=" * 80)
        logger.info("PHASE A1: Pattern-Match Reclassification (filename-based)")
        logger.info("=" * 80)

        docs = self.db.query(Document).filter(
            Document.doc_type == 'Other Document'
        ).order_by(Document.id).all()

        total = len(docs)
        logger.info(f"Found {total} 'Other Document' entries to analyze")

        if total == 0:
            logger.info("Nothing to process.")
            return

        batch_size = 100
        batch_count = 0
        skipped_generic = 0

        for idx, doc in enumerate(docs, 1):
            filename = (doc.name or "").lower()

            # Skip documents with generic "Outro -" names — no useful info
            if filename.startswith("outro -") or filename.startswith("outro-"):
                skipped_generic += 1
                self.stats['kept'] += 1
                continue

            # Also normalize underscores/hyphens to spaces for better matching
            filename_normalized = filename.replace("_", " ").replace("-", " ")

            matched_type = None
            matched_keyword = None

            for doc_type, keywords in FILENAME_PATTERNS.items():
                for keyword in keywords:
                    # For short/ambiguous keywords, only match on original filename
                    # (no normalization) to avoid false positives like "thaw 29" -> "w 2"
                    if keyword in self.BOUNDARY_KEYWORDS:
                        if keyword in filename:
                            matched_type = doc_type
                            matched_keyword = keyword
                            break
                        continue

                    # Match against both original (lowered) and normalized filename
                    if keyword in filename or keyword in filename_normalized:
                        matched_type = doc_type
                        matched_keyword = keyword
                        break
                    # Also try normalized keyword against normalized filename
                    # but ONLY for keywords >= 5 chars to avoid false positives
                    if len(keyword) >= 5:
                        kw_normalized = keyword.replace("-", " ").replace("_", " ")
                        if kw_normalized in filename_normalized:
                            matched_type = doc_type
                            matched_keyword = keyword
                            break
                if matched_type:
                    break

            if matched_type:
                if dry_run:
                    logger.info(
                        f"[{idx}/{total}] [DRY RUN] Doc {doc.id} '{doc.name}' "
                        f"-> {matched_type} (keyword: '{matched_keyword}')"
                    )
                else:
                    doc.doc_type = matched_type
                    doc.classification_confidence = 0.7
                    doc.llm_classified = False
                    doc.suggested_exhibit = EXHIBIT_MAP.get(matched_type)
                    batch_count += 1

                    logger.info(
                        f"[{idx}/{total}] RECLASSIFIED Doc {doc.id} '{doc.name}' "
                        f"-> {matched_type} (keyword: '{matched_keyword}')"
                    )

                self.stats['reclassified'] += 1
                self.changes[matched_type] += 1
            else:
                self.stats['kept'] += 1
                if idx <= 20 or idx % 500 == 0:
                    logger.debug(
                        f"[{idx}/{total}] No match for Doc {doc.id} '{doc.name}'"
                    )

            # Commit in batches to avoid holding huge transactions
            if not dry_run and batch_count > 0 and batch_count % batch_size == 0:
                try:
                    self.db.commit()
                    logger.info(f"  -- Committed batch ({batch_count} changes so far)")
                except Exception as e:
                    logger.error(f"  -- Batch commit failed: {e}")
                    self.db.rollback()

            # Progress log every 500 docs
            if idx % 500 == 0:
                elapsed = (datetime.now() - self.start_time).total_seconds()
                rate = idx / elapsed if elapsed > 0 else 0
                eta = (total - idx) / rate if rate > 0 else 0
                logger.info(
                    f"  Progress: {idx}/{total} ({idx/total*100:.1f}%) | "
                    f"Rate: {rate:.1f} docs/s | ETA: {eta:.0f}s | "
                    f"Reclassified: {self.stats['reclassified']} | "
                    f"Kept: {self.stats['kept']}"
                )

        # Final commit for any remaining changes
        if not dry_run and batch_count > 0:
            try:
                self.db.commit()
                logger.info(f"  -- Final commit ({batch_count} total changes)")
            except Exception as e:
                logger.error(f"  -- Final commit failed: {e}")
                self.db.rollback()

        logger.info(f"  Skipped generic 'Outro -' names: {skipped_generic}")
        self._print_phase_summary("A1")

    # =========================================================================
    # Phase A2: LLM reclassify using Gemini for remaining 'Other Document'
    # =========================================================================
    async def phase_a2_llm(self, limit: int = None, dry_run: bool = False):
        """
        LLM reclassify remaining 'Other Document' docs that have physical files.

        Uses classify_with_ocr from document_classifier.py which chains:
        LM Studio -> Gemini (enhanced with OCR) -> Gemini (basic) -> Perplexity -> filename pattern

        Args:
            limit: Maximum number of documents to process.
            dry_run: If True, do not commit changes.
        """
        # Import here to avoid loading LLM dependencies for phase A1
        from services.document_classifier import classify_with_ocr

        logger.info("=" * 80)
        logger.info("PHASE A2: LLM Reclassification (Gemini + OCR)")
        logger.info("=" * 80)

        # Reset phase stats (keep cumulative if running --all)
        phase_stats = Counter()

        query = self.db.query(Document).filter(
            Document.doc_type == 'Other Document',
            Document.status != 'file_missing'
        ).order_by(Document.id)

        if limit:
            query = query.limit(limit)
            logger.info(f"Limiting to {limit} documents")

        docs = query.all()
        total = len(docs)

        if total == 0:
            logger.info("No remaining 'Other Document' entries with files to process.")
            return

        logger.info(f"Found {total} 'Other Document' entries with files for LLM classification")

        # Show OCR status breakdown
        ocr_completed = sum(1 for d in docs if d.ocr_status == 'completed' and d.ocr_text)
        ocr_pending = sum(1 for d in docs if d.ocr_status == 'pending')
        ocr_failed = sum(1 for d in docs if d.ocr_status == 'failed')
        ocr_none = total - ocr_completed - ocr_pending - ocr_failed
        logger.info(
            f"  OCR breakdown: completed={ocr_completed}, pending={ocr_pending}, "
            f"failed={ocr_failed}, none/other={ocr_none}"
        )

        for idx, doc in enumerate(docs, 1):
            try:
                # Build context info for logging
                client_name = "Unknown"
                visa_type = "Unknown"
                if doc.client:
                    client_name = f"{doc.client.first_name} {doc.client.last_name}"
                if doc.case:
                    visa_type = doc.case.visa_type or "Unknown"

                ocr_chars = len(doc.ocr_text) if doc.ocr_text else 0

                logger.info(
                    f"[{idx}/{total}] Doc {doc.id} '{doc.name}' | "
                    f"Client: {client_name} | Visa: {visa_type} | "
                    f"OCR: {ocr_chars} chars"
                )

                if dry_run:
                    logger.info(f"  [DRY RUN] Would classify via LLM")
                    phase_stats['skipped'] += 1
                    continue

                # Call the multi-LLM classifier
                result = await classify_with_ocr(doc.id, self.db)

                if 'error' in result:
                    if result.get('retry'):
                        logger.warning(
                            f"  OCR not ready (retry later): {result['error']}"
                        )
                        phase_stats['retry_later'] += 1
                    else:
                        logger.error(f"  Classification error: {result['error']}")
                        phase_stats['errors'] += 1
                    continue

                new_type = result.get('doc_type', 'Other Document')
                confidence = result.get('confidence', 0.0)
                method = result.get('method', 'unknown')

                if new_type != 'Other Document' and confidence >= 0.5:
                    doc.doc_type = new_type
                    doc.classification_confidence = confidence
                    doc.llm_classified = True
                    doc.suggested_exhibit = result.get('suggested_exhibit') or EXHIBIT_MAP.get(new_type)

                    try:
                        self.db.commit()
                    except Exception as e:
                        logger.error(f"  Commit failed for doc {doc.id}: {e}")
                        self.db.rollback()
                        phase_stats['errors'] += 1
                        continue

                    logger.info(
                        f"  RECLASSIFIED -> {new_type} "
                        f"(confidence: {confidence:.2f}, method: {method})"
                    )
                    phase_stats['reclassified'] += 1
                    self.stats['reclassified'] += 1
                    self.changes[new_type] += 1
                else:
                    logger.info(
                        f"  Kept as Other Document "
                        f"(LLM said: {new_type}, confidence: {confidence:.2f})"
                    )
                    phase_stats['kept'] += 1
                    self.stats['kept'] += 1

                phase_stats['processed'] += 1

                # Progress log every 25 docs (LLM is slower)
                if idx % 25 == 0:
                    elapsed = (datetime.now() - self.start_time).total_seconds()
                    rate = idx / elapsed if elapsed > 0 else 0
                    eta = (total - idx) / rate if rate > 0 else 0
                    logger.info(
                        f"  Progress: {idx}/{total} ({idx/total*100:.1f}%) | "
                        f"Rate: {rate:.2f} docs/s | ETA: {eta/60:.1f} min | "
                        f"Reclassified: {phase_stats['reclassified']} | "
                        f"Kept: {phase_stats['kept']} | "
                        f"Errors: {phase_stats['errors']}"
                    )

                # Rate limit to avoid overwhelming LLM APIs
                await asyncio.sleep(1.0)

            except Exception as e:
                logger.error(
                    f"[{idx}/{total}] Unexpected error for doc {doc.id}: {e}",
                    exc_info=True
                )
                self.db.rollback()
                phase_stats['errors'] += 1
                self.stats['errors'] += 1

        # Log phase A2 summary
        logger.info("")
        logger.info(f"Phase A2 Summary:")
        logger.info(f"  Processed:    {phase_stats['processed']}")
        logger.info(f"  Reclassified: {phase_stats['reclassified']}")
        logger.info(f"  Kept:         {phase_stats['kept']}")
        logger.info(f"  Retry later:  {phase_stats['retry_later']}")
        logger.info(f"  Skipped:      {phase_stats['skipped']}")
        logger.info(f"  Errors:       {phase_stats['errors']}")

    # =========================================================================
    # Helpers
    # =========================================================================
    def _print_phase_summary(self, phase_name: str):
        """Print summary statistics for a phase."""
        elapsed = (datetime.now() - self.start_time).total_seconds()

        logger.info("")
        logger.info(f"Phase {phase_name} Summary:")
        logger.info(f"  Reclassified: {self.stats['reclassified']}")
        logger.info(f"  Kept as Other Document: {self.stats['kept']}")
        logger.info(f"  Errors: {self.stats['errors']}")
        logger.info(f"  Elapsed: {elapsed:.1f}s ({elapsed/60:.1f} min)")

        if self.changes:
            logger.info("")
            logger.info("  Reclassified by category:")
            for doc_type, count in self.changes.most_common():
                logger.info(f"    {doc_type}: {count}")

    def print_final_statistics(self):
        """Print final combined statistics for all phases."""
        elapsed = (datetime.now() - self.start_time).total_seconds()

        logger.info("")
        logger.info("=" * 80)
        logger.info("FINAL STATISTICS")
        logger.info("=" * 80)
        logger.info(f"  Total reclassified: {self.stats['reclassified']}")
        logger.info(f"  Total kept:         {self.stats['kept']}")
        logger.info(f"  Total errors:       {self.stats['errors']}")
        logger.info(f"  Total time:         {elapsed:.1f}s ({elapsed/60:.1f} min)")

        # Check remaining Other Documents
        remaining = self.db.query(Document).filter(
            Document.doc_type == 'Other Document'
        ).count()
        logger.info(f"  Remaining 'Other Document': {remaining}")

        if self.changes:
            logger.info("")
            logger.info("  Changes by category:")
            logger.info("  " + "-" * 50)
            for doc_type, count in self.changes.most_common():
                logger.info(f"    {doc_type:40s} {count:5d}")
            logger.info("  " + "-" * 50)
            logger.info(f"    {'TOTAL':40s} {sum(self.changes.values()):5d}")

        logger.info("=" * 80)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Deep reclassification of 'Other Document' entries using "
            "real filenames (Phase A1) and LLM (Phase A2)."
        )
    )
    parser.add_argument(
        '--phase',
        choices=['a1', 'a2'],
        help="Run a specific phase: a1 (pattern matching) or a2 (LLM)"
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help="Run all phases sequentially (A1 then A2)"
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help="Limit number of documents to process (applies to A2)"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Preview what would be done without making any database changes"
    )

    args = parser.parse_args()

    # Require at least --phase or --all
    if not args.phase and not args.all:
        parser.print_help()
        print("\nError: specify --phase a1, --phase a2, or --all")
        sys.exit(1)

    # Get database session
    db = next(get_db())
    reclassifier = DeepReclassifier(db)

    mode = "DRY RUN" if args.dry_run else "LIVE"
    logger.info(f"Deep Reclassifier starting ({mode})")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")

    # Show initial count
    other_count = db.query(Document).filter(
        Document.doc_type == 'Other Document'
    ).count()
    logger.info(f"Current 'Other Document' count: {other_count}")
    logger.info("")

    try:
        # Phase A1
        if args.all or args.phase == 'a1':
            reclassifier.phase_a1_pattern_match(dry_run=args.dry_run)

        # Phase A2
        if args.all or args.phase == 'a2':
            await reclassifier.phase_a2_llm(
                limit=args.limit,
                dry_run=args.dry_run
            )

        # Final stats
        reclassifier.print_final_statistics()

    except KeyboardInterrupt:
        logger.warning("\nInterrupted by user (Ctrl+C)")
        reclassifier.print_final_statistics()
        sys.exit(1)

    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        reclassifier.print_final_statistics()
        sys.exit(1)

    finally:
        db.close()

    logger.info("Deep reclassification complete.")


if __name__ == '__main__':
    asyncio.run(main())
