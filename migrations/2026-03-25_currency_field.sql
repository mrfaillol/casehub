-- Migration: Add currency field to billing tables
-- Date: 2026-03-25
-- Purpose: Support multi-currency (BRL, USD, EUR, GBP) for billing and time entries

-- Add currency column to billing_items if not exists
ALTER TABLE billing_items ADD COLUMN IF NOT EXISTS currency VARCHAR(3) DEFAULT 'USD';

-- Add currency column to time_entries if not exists
ALTER TABLE time_entries ADD COLUMN IF NOT EXISTS currency VARCHAR(3) DEFAULT 'USD';

-- Update currency based on org's product_type for lite orgs (assumed BRL)
UPDATE billing_items bi SET currency = 'BRL'
WHERE currency = 'USD'
  AND EXISTS (
    SELECT 1 FROM cases c
    JOIN organizations o ON c.org_id = o.id
    WHERE c.id = bi.case_id AND o.currency = 'BRL'
);

UPDATE time_entries te SET currency = 'BRL'
WHERE currency = 'USD'
  AND EXISTS (
    SELECT 1 FROM cases c
    JOIN organizations o ON c.org_id = o.id
    WHERE c.id = te.case_id AND o.currency = 'BRL'
);

-- Index for currency filtering
CREATE INDEX IF NOT EXISTS idx_billing_items_currency ON billing_items(currency);
CREATE INDEX IF NOT EXISTS idx_time_entries_currency ON time_entries(currency);
