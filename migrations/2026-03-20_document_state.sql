-- ============================================================================
-- CaseHub Document State Unification Migration
-- Date: 2026-03-20
-- Description: Adds a unified `state` column to documents, computed from the
--              overlapping status, workflow_state, ocr_status, and
--              drive_sync_status fields.
-- ============================================================================

BEGIN;

-- 1. Add the unified state column
ALTER TABLE documents ADD COLUMN IF NOT EXISTS state VARCHAR(30) DEFAULT 'uploaded';

-- 2. Backfill from existing fields
UPDATE documents SET state = CASE
    WHEN workflow_state = 'approved' AND drive_sync_status = 'synced' THEN 'synced'
    WHEN workflow_state = 'approved' THEN 'approved'
    WHEN workflow_state = 'pending_review' OR status = 'pending_approval' THEN 'pending_review'
    WHEN workflow_state = 'rejected' OR status = 'rejected' THEN 'rejected'
    ELSE 'uploaded'
END;

-- 3. Index for fast filtering on the new column
CREATE INDEX IF NOT EXISTS idx_documents_state ON documents(state);

COMMIT;
