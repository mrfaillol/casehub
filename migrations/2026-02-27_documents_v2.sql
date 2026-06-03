-- CaseHub Documents System V2 Migration
-- Created: 2026-02-27
-- Purpose: Add OCR fields, deduplication, unified workflow state, path management
-- Risk: LOW (all ADD COLUMN with defaults, indexes CONCURRENTLY)
-- Estimated time: 2-3 minutes

-- CRITICAL: Before running this migration, ensure 2026-02-20_intake_document_integration.sql
--           has been applied. That migration adds:
--           - intake_package_id, intake_item_id, drive_sync_status, drive_synced_at,
--             drive_sync_error, drive_retry_count, client_notified_at,
--             approval_notification_sent, rejection_notification_sent

BEGIN;

-- =============================================================================
-- STEP 1: Add OCR fields (for PDF text extraction)
-- =============================================================================

ALTER TABLE documents
ADD COLUMN IF NOT EXISTS ocr_text TEXT,
ADD COLUMN IF NOT EXISTS ocr_language VARCHAR(10) DEFAULT 'en',
ADD COLUMN IF NOT EXISTS ocr_confidence FLOAT,
ADD COLUMN IF NOT EXISTS ocr_processed_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS ocr_status VARCHAR(20) DEFAULT 'pending'
    CHECK (ocr_status IN ('pending', 'processing', 'completed', 'failed'));

-- =============================================================================
-- STEP 2: Add deduplication fields (content-based duplicate detection)
-- =============================================================================

ALTER TABLE documents
ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64),  -- SHA256 of file content
ADD COLUMN IF NOT EXISTS duplicate_of INTEGER REFERENCES documents(id) ON DELETE SET NULL;

-- =============================================================================
-- STEP 3: Add path management fields (unified file storage)
-- =============================================================================

ALTER TABLE documents
ADD COLUMN IF NOT EXISTS storage_path VARCHAR(1000),  -- Actual file location (replaces scattered file_path usage)
ADD COLUMN IF NOT EXISTS public_slug VARCHAR(500),    -- Human-readable URL slug (e.g., "john-doe-passport-20260227")
ADD COLUMN IF NOT EXISTS storage_backend VARCHAR(20) DEFAULT 'local'
    CHECK (storage_backend IN ('local', 'drive', 's3'));

-- =============================================================================
-- STEP 4: Add unified workflow state (replaces confusing "status" field)
-- =============================================================================

ALTER TABLE documents
ADD COLUMN IF NOT EXISTS workflow_state VARCHAR(30) DEFAULT 'uploaded'
    CHECK (workflow_state IN (
        'uploaded',           -- Initial upload (replaces "pending"/"received")
        'pending_review',     -- Awaiting paralegal review (replaces "pending_approval")
        'approved',          -- Approved by staff
        'rejected',          -- Rejected by staff
        'pending_client',    -- Awaiting client action
        'archived'           -- Archived/deleted (replaces "expired")
    ));

COMMIT;

-- =============================================================================
-- STEP 5: Create indexes for performance (run CONCURRENTLY to avoid locks)
-- =============================================================================

-- Note: CREATE INDEX CONCURRENTLY cannot run inside transaction block
-- Must be run separately after the ALTER TABLE statements

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_documents_ocr_status ON documents(ocr_status);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_documents_workflow_state ON documents(workflow_state);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_documents_public_slug ON documents(public_slug);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_documents_duplicate_of ON documents(duplicate_of);

-- =============================================================================
-- STEP 6: Migrate existing data (backfill new fields)
-- =============================================================================

BEGIN;

-- Migrate old "status" to new "workflow_state"
UPDATE documents SET workflow_state =
    CASE
        WHEN LOWER(status) = 'approved' THEN 'approved'
        WHEN LOWER(status) = 'rejected' THEN 'rejected'
        WHEN LOWER(status) IN ('pending', 'pending_approval') THEN 'pending_review'
        WHEN LOWER(status) = 'received' THEN 'uploaded'
        WHEN LOWER(status) = 'expired' THEN 'archived'
        ELSE 'uploaded'
    END
WHERE workflow_state IS NULL;

-- Backfill storage_path from file_path (if not already set)
UPDATE documents SET storage_path = file_path WHERE storage_path IS NULL AND file_path IS NOT NULL;

-- Generate public_slug from name (simple version: lowercase, replace special chars with hyphens)
UPDATE documents SET public_slug =
    LOWER(
        REGEXP_REPLACE(
            REGEXP_REPLACE(name, '[^a-zA-Z0-9\s-]', '', 'g'),  -- Remove special chars
            '\s+', '-', 'g'  -- Replace spaces with hyphens
        )
    )
WHERE public_slug IS NULL;

-- Set OCR status for existing PDFs (will be processed by batch script)
UPDATE documents
SET ocr_status = 'pending'
WHERE ocr_status IS NULL
  AND mime_type = 'application/pdf';

-- Set OCR status to 'completed' for non-PDFs (no OCR needed)
UPDATE documents
SET ocr_status = 'completed'
WHERE ocr_status IS NULL
  AND mime_type != 'application/pdf';

COMMIT;

-- =============================================================================
-- STEP 7: Verification queries (run after migration to confirm success)
-- =============================================================================

-- Check that all new columns exist
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'documents'
  AND column_name IN ('ocr_text', 'ocr_status', 'content_hash', 'duplicate_of',
                      'storage_path', 'public_slug', 'workflow_state')
ORDER BY column_name;

-- Check that indexes were created
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'documents'
  AND indexname LIKE 'idx_documents_%'
ORDER BY indexname;

-- Verify data migration
SELECT
    COUNT(*) AS total_documents,
    COUNT(workflow_state) AS with_workflow_state,
    COUNT(storage_path) AS with_storage_path,
    COUNT(public_slug) AS with_public_slug,
    COUNT(CASE WHEN ocr_status = 'pending' THEN 1 END) AS pending_ocr,
    COUNT(CASE WHEN ocr_status = 'completed' THEN 1 END) AS completed_ocr
FROM documents;

-- =============================================================================
-- ROLLBACK PLAN (if migration fails)
-- =============================================================================

-- To rollback this migration:
-- 1. DROP the new columns:
--    ALTER TABLE documents DROP COLUMN IF EXISTS ocr_text, ocr_language, ocr_confidence,
--                                                ocr_processed_at, ocr_status, content_hash,
--                                                duplicate_of, storage_path, public_slug,
--                                                storage_backend, workflow_state;
-- 2. DROP the indexes:
--    DROP INDEX CONCURRENTLY IF EXISTS idx_documents_ocr_status, idx_documents_content_hash,
--                                       idx_documents_workflow_state, idx_documents_public_slug,
--                                       idx_documents_duplicate_of;
-- 3. Restart casehub: pm2 restart casehub

-- =============================================================================
-- NOTES
-- =============================================================================

-- 1. This migration is SAFE to run on production:
--    - All ADD COLUMN with defaults → no downtime
--    - Indexes created CONCURRENTLY → no table locks
--    - Data migration uses UPDATE → can be rolled back
--
-- 2. After this migration:
--    - Old "status" field still exists (for backward compatibility)
--    - New "workflow_state" field should be used going forward
--    - FileStorageService will populate storage_path, public_slug, content_hash
--    - OCRService will populate ocr_text, ocr_confidence, ocr_processed_at
--
-- 3. Estimated runtime: 2-3 minutes (depends on number of documents)
--
-- 4. Next steps after migration:
--    - Deploy FileStorageService (Step 2)
--    - Install OCR dependencies (Step 3)
--    - Deploy OCRService (Step 4)
--    - Run batch reprocessing to populate content_hash and ocr_text (Step 5)
