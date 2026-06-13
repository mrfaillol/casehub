-- ============================================================================
-- CaseHub Multi-Tenancy Migration
-- Date: 2026-03-20
-- Description: Adds organizations table and org_id to all existing tables
--              to support white-label multi-tenant operation.
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. CREATE organizations table
-- ============================================================================
CREATE TABLE IF NOT EXISTS organizations (
    id              SERIAL PRIMARY KEY,
    uuid            UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    name            VARCHAR(255) NOT NULL,
    slug            VARCHAR(100) NOT NULL UNIQUE,       -- URL-safe identifier (e.g., "immigrant-law-center")
    domain          VARCHAR(255),                        -- Custom domain (e.g., "casehub.immigrant.law")
    logo_url        VARCHAR(500),
    favicon_url     VARCHAR(500),
    primary_color   VARCHAR(7) DEFAULT '#1a56db',        -- Hex color for branding
    secondary_color VARCHAR(7) DEFAULT '#7c3aed',

    -- Contact info
    email           VARCHAR(255),                        -- Primary org email
    phone           VARCHAR(50),
    website         VARCHAR(255),
    address         TEXT,

    -- Operational settings
    timezone        VARCHAR(50) DEFAULT 'America/New_York',
    locale          VARCHAR(10) DEFAULT 'en',
    case_prefix     VARCHAR(10) DEFAULT 'CH',            -- Prefix for case numbers
    currency        VARCHAR(3) DEFAULT 'USD',

    -- Integration credentials (encrypted at app level)
    google_drive_root_id    VARCHAR(255),
    google_credentials_path VARCHAR(500),
    smtp_host       VARCHAR(255),
    smtp_port       INTEGER DEFAULT 587,
    smtp_user       VARCHAR(255),
    smtp_pass       VARCHAR(255),                        -- Encrypted at app level
    smtp_from_name  VARCHAR(255),

    -- Subscription / billing
    plan            VARCHAR(50) DEFAULT 'starter',       -- starter, professional, enterprise
    max_users       INTEGER DEFAULT 5,
    max_clients     INTEGER DEFAULT 100,
    max_storage_gb  INTEGER DEFAULT 10,
    stripe_customer_id      VARCHAR(255),
    stripe_subscription_id  VARCHAR(255),
    subscription_status     VARCHAR(50) DEFAULT 'active', -- active, past_due, canceled, trialing

    -- Feature flags (JSON for flexibility)
    features        JSONB DEFAULT '{
        "whatsapp_bot": false,
        "email_automation": false,
        "document_sync": true,
        "client_portal": true,
        "billing": true,
        "aila_search": false,
        "package_builder": false,
        "lor_generator": false
    }'::jsonb,

    -- Metadata
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Index for domain lookups (tenant resolution)
CREATE UNIQUE INDEX IF NOT EXISTS idx_organizations_domain ON organizations(domain) WHERE domain IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_organizations_slug ON organizations(slug);
CREATE INDEX IF NOT EXISTS idx_organizations_active ON organizations(is_active) WHERE is_active = TRUE;

-- ============================================================================
-- 2. INSERT default organization (for migration of existing data)
-- ============================================================================
INSERT INTO organizations (name, slug, domain, email, website, plan, max_users, max_clients, max_storage_gb, features)
VALUES (
    'Default Organization',
    'default',
    NULL,
    '',
    '',
    'enterprise',
    999,
    99999,
    1000,
    '{
        "whatsapp_bot": true,
        "email_automation": true,
        "document_sync": true,
        "client_portal": true,
        "billing": true,
        "aila_search": true,
        "package_builder": true,
        "lor_generator": true
    }'::jsonb
)
ON CONFLICT (slug) DO NOTHING;

-- ============================================================================
-- 3. ALTER existing tables to add org_id column
-- ============================================================================

-- users
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE;
UPDATE users SET org_id = (SELECT id FROM organizations WHERE slug = 'default') WHERE org_id IS NULL;

-- clients
ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE;
UPDATE clients SET org_id = (SELECT id FROM organizations WHERE slug = 'default') WHERE org_id IS NULL;

-- cases
ALTER TABLE cases
    ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE;
UPDATE cases SET org_id = (SELECT id FROM organizations WHERE slug = 'default') WHERE org_id IS NULL;

-- documents
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE;
UPDATE documents SET org_id = (SELECT id FROM organizations WHERE slug = 'default') WHERE org_id IS NULL;

-- tasks
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE;
UPDATE tasks SET org_id = (SELECT id FROM organizations WHERE slug = 'default') WHERE org_id IS NULL;

-- reminders
ALTER TABLE reminders
    ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE;
UPDATE reminders SET org_id = (SELECT id FROM organizations WHERE slug = 'default') WHERE org_id IS NULL;

-- billing_items
ALTER TABLE billing_items
    ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE;
UPDATE billing_items SET org_id = (SELECT id FROM organizations WHERE slug = 'default') WHERE org_id IS NULL;

-- time_entries
ALTER TABLE time_entries
    ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE;
UPDATE time_entries SET org_id = (SELECT id FROM organizations WHERE slug = 'default') WHERE org_id IS NULL;

-- invoices
ALTER TABLE invoices
    ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE;
UPDATE invoices SET org_id = (SELECT id FROM organizations WHERE slug = 'default') WHERE org_id IS NULL;

-- invoice_items
ALTER TABLE invoice_items
    ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE;
UPDATE invoice_items SET org_id = (SELECT id FROM organizations WHERE slug = 'default') WHERE org_id IS NULL;

-- notifications
ALTER TABLE notifications
    ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE;
UPDATE notifications SET org_id = (SELECT id FROM organizations WHERE slug = 'default') WHERE org_id IS NULL;

-- questionnaire_templates
ALTER TABLE questionnaire_templates
    ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE;
UPDATE questionnaire_templates SET org_id = (SELECT id FROM organizations WHERE slug = 'default') WHERE org_id IS NULL;

-- questionnaire_fields
ALTER TABLE questionnaire_fields
    ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE;
UPDATE questionnaire_fields SET org_id = (SELECT id FROM organizations WHERE slug = 'default') WHERE org_id IS NULL;

-- questionnaire_responses
ALTER TABLE questionnaire_responses
    ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE;
UPDATE questionnaire_responses SET org_id = (SELECT id FROM organizations WHERE slug = 'default') WHERE org_id IS NULL;

-- questionnaire_field_responses
ALTER TABLE questionnaire_field_responses
    ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE;
UPDATE questionnaire_field_responses SET org_id = (SELECT id FROM organizations WHERE slug = 'default') WHERE org_id IS NULL;

-- ============================================================================
-- 4. CREATE indexes for org_id columns (performance for tenant queries)
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_users_org_id ON users(org_id);
CREATE INDEX IF NOT EXISTS idx_clients_org_id ON clients(org_id);
CREATE INDEX IF NOT EXISTS idx_cases_org_id ON cases(org_id);
CREATE INDEX IF NOT EXISTS idx_documents_org_id ON documents(org_id);
CREATE INDEX IF NOT EXISTS idx_tasks_org_id ON tasks(org_id);
CREATE INDEX IF NOT EXISTS idx_reminders_org_id ON reminders(org_id);
CREATE INDEX IF NOT EXISTS idx_billing_items_org_id ON billing_items(org_id);
CREATE INDEX IF NOT EXISTS idx_time_entries_org_id ON time_entries(org_id);
CREATE INDEX IF NOT EXISTS idx_invoices_org_id ON invoices(org_id);
CREATE INDEX IF NOT EXISTS idx_invoice_items_org_id ON invoice_items(org_id);
CREATE INDEX IF NOT EXISTS idx_notifications_org_id ON notifications(org_id);
CREATE INDEX IF NOT EXISTS idx_questionnaire_templates_org_id ON questionnaire_templates(org_id);
CREATE INDEX IF NOT EXISTS idx_questionnaire_fields_org_id ON questionnaire_fields(org_id);
CREATE INDEX IF NOT EXISTS idx_questionnaire_responses_org_id ON questionnaire_responses(org_id);
CREATE INDEX IF NOT EXISTS idx_questionnaire_field_responses_org_id ON questionnaire_field_responses(org_id);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_users_org_email ON users(org_id, email);
CREATE INDEX IF NOT EXISTS idx_clients_org_status ON clients(org_id, status);
CREATE INDEX IF NOT EXISTS idx_cases_org_status ON cases(org_id, status);
CREATE INDEX IF NOT EXISTS idx_documents_org_client ON documents(org_id, client_id);

-- ============================================================================
-- 5. Add NOT NULL constraint after data migration
--    (Run this AFTER verifying all rows have org_id set)
-- ============================================================================
-- Uncomment these after confirming migration is complete:
-- ALTER TABLE users ALTER COLUMN org_id SET NOT NULL;
-- ALTER TABLE clients ALTER COLUMN org_id SET NOT NULL;
-- ALTER TABLE cases ALTER COLUMN org_id SET NOT NULL;
-- ALTER TABLE documents ALTER COLUMN org_id SET NOT NULL;
-- ALTER TABLE tasks ALTER COLUMN org_id SET NOT NULL;
-- ALTER TABLE reminders ALTER COLUMN org_id SET NOT NULL;
-- ALTER TABLE billing_items ALTER COLUMN org_id SET NOT NULL;
-- ALTER TABLE time_entries ALTER COLUMN org_id SET NOT NULL;
-- ALTER TABLE invoices ALTER COLUMN org_id SET NOT NULL;
-- ALTER TABLE invoice_items ALTER COLUMN org_id SET NOT NULL;
-- ALTER TABLE notifications ALTER COLUMN org_id SET NOT NULL;
-- ALTER TABLE questionnaire_templates ALTER COLUMN org_id SET NOT NULL;
-- ALTER TABLE questionnaire_fields ALTER COLUMN org_id SET NOT NULL;
-- ALTER TABLE questionnaire_responses ALTER COLUMN org_id SET NOT NULL;
-- ALTER TABLE questionnaire_field_responses ALTER COLUMN org_id SET NOT NULL;

COMMIT;
