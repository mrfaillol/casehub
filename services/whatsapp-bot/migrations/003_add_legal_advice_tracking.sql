-- Migration: Add legal advice tracking fields to leads table
-- Date: 2026-02-25
-- Purpose: Track when bot blocks legal advice to prevent license risk
-- Related: Correction #1 - Anti-Legal-Advice Filter (PRIORITY #1)

ALTER TABLE leads
ADD COLUMN IF NOT EXISTS needs_human_review TINYINT(1) DEFAULT 0
COMMENT 'Flag for leads that need human review (legal advice blocked, etc)';

ALTER TABLE leads
ADD COLUMN IF NOT EXISTS legal_advice_blocked_count INT DEFAULT 0
COMMENT 'Number of times legal advice was blocked for this lead';

ALTER TABLE leads
ADD COLUMN IF NOT EXISTS last_legal_advice_block TIMESTAMP NULL DEFAULT NULL
COMMENT 'Timestamp of last legal advice block';

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_needs_human_review ON leads(needs_human_review);
CREATE INDEX IF NOT EXISTS idx_legal_advice_blocked ON leads(legal_advice_blocked_count);

-- Verificar campos adicionados
SELECT
  COLUMN_NAME,
  COLUMN_TYPE,
  COLUMN_DEFAULT,
  IS_NULLABLE,
  COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'leads'
  AND COLUMN_NAME IN ('needs_human_review', 'legal_advice_blocked_count', 'last_legal_advice_block')
ORDER BY COLUMN_NAME;
