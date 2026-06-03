-- ============================================================================
-- CaseHub Security Migration - Phase 4
-- Date: 2026-03-20
-- Description: Password reset tokens table, user login tracking columns,
--              expanded audit_log columns for automatic CRUD logging.
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. CREATE password_reset_tokens table
-- ============================================================================
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token           VARCHAR(255) NOT NULL UNIQUE,
    expires_at      TIMESTAMPTZ NOT NULL,
    used            BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prt_token ON password_reset_tokens(token);
CREATE INDEX IF NOT EXISTS idx_prt_user ON password_reset_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_prt_expires ON password_reset_tokens(expires_at) WHERE used = FALSE;

-- ============================================================================
-- 2. ALTER users table - add login tracking columns
-- ============================================================================
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS login_count INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_count INTEGER DEFAULT 0;

-- ============================================================================
-- 3. Ensure audit_log has all columns needed for expanded audit
-- ============================================================================
-- These columns may already exist; IF NOT EXISTS prevents errors.
-- The existing audit_log table has: action, entity_type, entity_id,
-- user_id, user_email, description, details, ip_address, user_agent, created_at.
-- We add org_id if not present.
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS org_id INTEGER;

-- Index for org-scoped audit queries
CREATE INDEX IF NOT EXISTS idx_audit_log_org ON audit_log(org_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);

COMMIT;
