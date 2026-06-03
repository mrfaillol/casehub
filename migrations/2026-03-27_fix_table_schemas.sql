-- Migration: Fix table schemas causing 500 errors
-- Date: 2026-03-27
-- Issues:
--   1. /casehub/emails  — query referenced clients.assigned_to (doesn't exist) → fixed in route
--   2. /casehub/letters — letter_templates.org_id is VARCHAR but compared to INTEGER org id
--   3. /casehub/custom-fields — custom_field_definitions.org_id same VARCHAR vs INTEGER mismatch
--   All tables from 2026-03-26_missing_tables.sql had org_id as VARCHAR(100) instead of INTEGER

-- ============================================================
-- Fix org_id type: VARCHAR(100) → INTEGER for all affected tables
-- Must drop FK-incompatible default, alter type, then optionally add FK
-- ============================================================

-- 1. letter_templates
ALTER TABLE letter_templates
    ALTER COLUMN org_id TYPE INTEGER USING org_id::INTEGER;

-- 2. generated_letters
ALTER TABLE generated_letters
    ALTER COLUMN org_id TYPE INTEGER USING org_id::INTEGER;

-- 3. custom_field_definitions
ALTER TABLE custom_field_definitions
    ALTER COLUMN org_id TYPE INTEGER USING org_id::INTEGER;

-- 4. email_accounts
ALTER TABLE email_accounts
    ALTER COLUMN org_id TYPE INTEGER USING org_id::INTEGER;

-- 5. email_messages
ALTER TABLE email_messages
    ALTER COLUMN org_id TYPE INTEGER USING org_id::INTEGER;

-- 6. entity_webhooks
ALTER TABLE entity_webhooks
    ALTER COLUMN org_id TYPE INTEGER USING org_id::INTEGER;

-- 7. unified_messages
ALTER TABLE unified_messages
    ALTER COLUMN org_id TYPE INTEGER USING org_id::INTEGER;

-- ============================================================
-- Add is_active column to letter_templates (used by update route)
-- ============================================================
ALTER TABLE letter_templates ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

-- ============================================================
-- Add foreign key constraints to organizations table (optional, for integrity)
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'letter_templates_org_id_fkey') THEN
        ALTER TABLE letter_templates ADD CONSTRAINT letter_templates_org_id_fkey
            FOREIGN KEY (org_id) REFERENCES organizations(id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'generated_letters_org_id_fkey') THEN
        ALTER TABLE generated_letters ADD CONSTRAINT generated_letters_org_id_fkey
            FOREIGN KEY (org_id) REFERENCES organizations(id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'custom_field_definitions_org_id_fkey') THEN
        ALTER TABLE custom_field_definitions ADD CONSTRAINT custom_field_definitions_org_id_fkey
            FOREIGN KEY (org_id) REFERENCES organizations(id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'email_accounts_org_id_fkey') THEN
        ALTER TABLE email_accounts ADD CONSTRAINT email_accounts_org_id_fkey
            FOREIGN KEY (org_id) REFERENCES organizations(id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'email_messages_org_id_fkey') THEN
        ALTER TABLE email_messages ADD CONSTRAINT email_messages_org_id_fkey
            FOREIGN KEY (org_id) REFERENCES organizations(id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entity_webhooks_org_id_fkey') THEN
        ALTER TABLE entity_webhooks ADD CONSTRAINT entity_webhooks_org_id_fkey
            FOREIGN KEY (org_id) REFERENCES organizations(id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'unified_messages_org_id_fkey') THEN
        ALTER TABLE unified_messages ADD CONSTRAINT unified_messages_org_id_fkey
            FOREIGN KEY (org_id) REFERENCES organizations(id);
    END IF;
END $$;
