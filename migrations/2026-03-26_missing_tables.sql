-- Migration: Create missing tables causing 500 errors
-- Date: 2026-03-26
-- Tables: custom_field_definitions, custom_field_values, email_messages,
--         email_accounts, email_attachments, entity_webhooks, webhook_logs,
--         letter_templates, generated_letters

-- ============================================================
-- 1. custom_field_definitions
--    Used by: routes/custom_fields.py, routes/clients.py, routes/cases.py
-- ============================================================
CREATE TABLE IF NOT EXISTS custom_field_definitions (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,         -- 'client', 'case', 'document', 'contact'
    field_name VARCHAR(100) NOT NULL,
    field_label VARCHAR(200) NOT NULL,
    field_type VARCHAR(50) NOT NULL DEFAULT 'text',  -- text, textarea, number, date, select, checkbox, file
    options TEXT,                               -- JSON: array of options for select fields
    required BOOLEAN DEFAULT FALSE,
    display_order INTEGER DEFAULT 0,
    org_id INTEGER,                             -- tenant isolation (FK to organizations.id)
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(entity_type, field_name)
);

CREATE INDEX IF NOT EXISTS idx_cfd_entity_type ON custom_field_definitions(entity_type);
CREATE INDEX IF NOT EXISTS idx_cfd_org_id ON custom_field_definitions(org_id);

-- ============================================================
-- 2. custom_field_values
--    Used by: routes/custom_fields.py (API endpoints for saving/loading values)
-- ============================================================
CREATE TABLE IF NOT EXISTS custom_field_values (
    id SERIAL PRIMARY KEY,
    definition_id INTEGER NOT NULL REFERENCES custom_field_definitions(id) ON DELETE CASCADE,
    entity_id INTEGER NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    value TEXT,                                -- JSON-encoded value
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(definition_id, entity_id, entity_type)
);

CREATE INDEX IF NOT EXISTS idx_cfv_entity ON custom_field_values(entity_type, entity_id);

-- ============================================================
-- 3. email_accounts
--    Used by: routes/emails.py, routes/emails_sync.py
-- ============================================================
CREATE TABLE IF NOT EXISTS email_accounts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    email_address VARCHAR(300) NOT NULL,
    imap_server VARCHAR(200) NOT NULL,
    imap_port INTEGER DEFAULT 993,
    smtp_server VARCHAR(200),
    smtp_port INTEGER DEFAULT 587,
    username VARCHAR(200) NOT NULL,
    password_encrypted TEXT NOT NULL,
    use_ssl BOOLEAN DEFAULT TRUE,
    enabled BOOLEAN DEFAULT TRUE,
    org_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 4. email_messages
--    Used by: routes/emails.py, routes/emails_sync.py, routes/emails_compose.py
-- ============================================================
CREATE TABLE IF NOT EXISTS email_messages (
    id SERIAL PRIMARY KEY,
    account_id INTEGER REFERENCES email_accounts(id) ON DELETE SET NULL,
    message_id VARCHAR(500),                   -- IMAP message ID
    subject VARCHAR(500),
    sender VARCHAR(300),
    recipients TEXT,
    cc TEXT,
    body_text TEXT,
    body_html TEXT,
    folder VARCHAR(200),
    received_at TIMESTAMP,
    is_read BOOLEAN DEFAULT FALSE,
    archived BOOLEAN DEFAULT FALSE,
    client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
    case_id INTEGER REFERENCES cases(id) ON DELETE SET NULL,
    email_references VARCHAR(2000),            -- In-Reply-To / References headers
    org_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_em_account_msg ON email_messages(account_id, message_id);
CREATE INDEX IF NOT EXISTS idx_em_client ON email_messages(client_id);
CREATE INDEX IF NOT EXISTS idx_em_case ON email_messages(case_id);
CREATE INDEX IF NOT EXISTS idx_em_received ON email_messages(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_em_org_id ON email_messages(org_id);

-- ============================================================
-- 5. email_attachments
--    Used by: routes/emails_sync.py, routes/emails.py
-- ============================================================
CREATE TABLE IF NOT EXISTS email_attachments (
    id SERIAL PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES email_messages(id) ON DELETE CASCADE,
    filename VARCHAR(300),
    mime_type VARCHAR(100),
    file_size INTEGER,
    file_path VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- 6. entity_webhooks
--    Used by: routes/webhooks.py
-- ============================================================
CREATE TABLE IF NOT EXISTS entity_webhooks (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,          -- 'client', 'case', 'document', 'task', 'billing', '*'
    entity_id INTEGER,                         -- NULL = all entities of this type
    event_type VARCHAR(100) NOT NULL,          -- e.g. 'client.created', 'case.status_changed'
    webhook_url TEXT NOT NULL,
    headers TEXT,                               -- JSON: custom headers
    enabled BOOLEAN DEFAULT TRUE,
    last_triggered_at TIMESTAMP,
    last_response_code INTEGER,
    failure_count INTEGER DEFAULT 0,
    org_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ew_event ON entity_webhooks(event_type, entity_type);
CREATE INDEX IF NOT EXISTS idx_ew_org_id ON entity_webhooks(org_id);

-- ============================================================
-- 7. webhook_logs
--    Used by: routes/webhooks.py (trigger_webhook, view_webhook_logs)
-- ============================================================
CREATE TABLE IF NOT EXISTS webhook_logs (
    id SERIAL PRIMARY KEY,
    webhook_id INTEGER NOT NULL REFERENCES entity_webhooks(id) ON DELETE CASCADE,
    event_type VARCHAR(100),
    payload TEXT,                               -- JSON payload sent
    response_code INTEGER,
    response_body TEXT,
    error_message TEXT,
    triggered_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wl_webhook ON webhook_logs(webhook_id);

-- ============================================================
-- 8. letter_templates
--    Used by: routes/letters.py
-- ============================================================
CREATE TABLE IF NOT EXISTS letter_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    subject VARCHAR(500),
    body TEXT,
    variables TEXT,                             -- JSON: list of template variables
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    org_id INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lt_org_id ON letter_templates(org_id);

-- ============================================================
-- 9. generated_letters
--    Used by: routes/letters.py
-- ============================================================
CREATE TABLE IF NOT EXISTS generated_letters (
    id SERIAL PRIMARY KEY,
    template_id INTEGER REFERENCES letter_templates(id) ON DELETE SET NULL,
    case_id INTEGER REFERENCES cases(id) ON DELETE SET NULL,
    client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
    subject VARCHAR(500),
    body TEXT,
    generated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    org_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gl_template ON generated_letters(template_id);
CREATE INDEX IF NOT EXISTS idx_gl_client ON generated_letters(client_id);

-- ============================================================
-- 10. unified_messages (referenced in emails.py link endpoint)
-- ============================================================
CREATE TABLE IF NOT EXISTS unified_messages (
    id SERIAL PRIMARY KEY,
    source_table VARCHAR(50) NOT NULL,         -- 'email_messages', 'whatsapp_messages', etc.
    source_id INTEGER NOT NULL,
    client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
    case_id INTEGER REFERENCES cases(id) ON DELETE SET NULL,
    direction VARCHAR(10),                     -- 'in', 'out'
    channel VARCHAR(50),                       -- 'email', 'whatsapp', 'sms'
    subject VARCHAR(500),
    body_preview TEXT,
    sender VARCHAR(300),
    received_at TIMESTAMP,
    org_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_um_source ON unified_messages(source_table, source_id);
CREATE INDEX IF NOT EXISTS idx_um_client ON unified_messages(client_id);
