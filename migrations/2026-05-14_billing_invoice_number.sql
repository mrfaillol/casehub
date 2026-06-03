-- Migration: Add invoice_number to billing_items
-- Date: 2026-05-14
-- Purpose: Keep invoice/payment routes compatible with existing databases.

ALTER TABLE billing_items ADD COLUMN IF NOT EXISTS invoice_number VARCHAR(50);

CREATE INDEX IF NOT EXISTS ix_billing_items_invoice_number
    ON billing_items(invoice_number);
