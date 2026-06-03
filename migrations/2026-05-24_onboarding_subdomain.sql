-- Migration: Onboarding state + subdomain provisioning
-- Date: 2026-05-24
-- Purpose: Support self-service signup with auto-subdomain (cliente.example.com),
--          persistent onboarding tour progress (cross-device), email verification tokens,
--          and a reserved-subdomains blocklist enforced by the slug-validation API.
-- Idempotent: safe to re-run.

-- ---------------------------------------------------------------------------
-- 1. USERS: onboarding state + email verification
-- ---------------------------------------------------------------------------
ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_completed_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_tour_step VARCHAR(50);
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP WITH TIME ZONE;

CREATE INDEX IF NOT EXISTS ix_users_onboarding_completed_at ON users(onboarding_completed_at);
CREATE INDEX IF NOT EXISTS ix_users_email_verified_at ON users(email_verified_at);

-- Existing users (pre-migration) are considered "already verified + onboarded".
-- Self-service signup will leave these NULL for new users until they verify.
UPDATE users
   SET email_verified_at = COALESCE(email_verified_at, created_at, NOW())
 WHERE email_verified_at IS NULL
   AND must_change_password = FALSE;

-- ---------------------------------------------------------------------------
-- 2. ORGANIZATIONS: provenance + slug lockdown
-- ---------------------------------------------------------------------------
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS created_via VARCHAR(20) DEFAULT 'manual';
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS subdomain_locked BOOLEAN DEFAULT FALSE;

-- Backfill: existing orgs are 'manual' provisioning, subdomain not locked yet.
UPDATE organizations
   SET created_via = COALESCE(created_via, 'manual')
 WHERE created_via IS NULL;

CREATE INDEX IF NOT EXISTS ix_organizations_created_via ON organizations(created_via);

-- ---------------------------------------------------------------------------
-- 3. RESERVED SUBDOMAINS: blocklist enforced by /api/onboarding/check-subdomain
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reserved_subdomains (
    slug VARCHAR(100) PRIMARY KEY,
    reason VARCHAR(50) NOT NULL,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_reserved_subdomains_reason ON reserved_subdomains(reason);

-- ---------------------------------------------------------------------------
-- 4. EMAIL VERIFICATIONS: tokens for self-service signup (Fatia B)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS email_verifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(255) NOT NULL UNIQUE,
    email VARCHAR(200) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    consumed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ip_address VARCHAR(64),
    user_agent TEXT
);

CREATE INDEX IF NOT EXISTS ix_email_verifications_token ON email_verifications(token);
CREATE INDEX IF NOT EXISTS ix_email_verifications_user_id ON email_verifications(user_id);
CREATE INDEX IF NOT EXISTS ix_email_verifications_expires_at ON email_verifications(expires_at);

-- ---------------------------------------------------------------------------
-- 5. SIGNUP AUDIT LOG: append-only record for Sentinela review (Fatia B)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS signup_audit_log (
    id SERIAL PRIMARY KEY,
    org_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    email VARCHAR(200) NOT NULL,
    slug VARCHAR(100) NOT NULL,
    firm_name VARCHAR(255),
    ip_address VARCHAR(64),
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    captcha_score NUMERIC(3,2),
    flagged_reason VARCHAR(200)
);

CREATE INDEX IF NOT EXISTS ix_signup_audit_log_email ON signup_audit_log(email);
CREATE INDEX IF NOT EXISTS ix_signup_audit_log_slug ON signup_audit_log(slug);
CREATE INDEX IF NOT EXISTS ix_signup_audit_log_created_at ON signup_audit_log(created_at);

-- ---------------------------------------------------------------------------
-- 6. RESERVED SUBDOMAINS: seed canonical blocklist
-- Categories: infrastructure, security, app, monitoring, billing, marketing,
-- brand (casehub/vingren/customer), environment, government (BR legal), inappropriate.
-- ---------------------------------------------------------------------------
INSERT INTO reserved_subdomains (slug, reason, notes) VALUES
    -- Infrastructure
    ('www', 'infrastructure', 'web root'),
    ('mail', 'infrastructure', 'email'),
    ('email', 'infrastructure', 'email'),
    ('smtp', 'infrastructure', 'email outbound'),
    ('imap', 'infrastructure', 'email inbound'),
    ('pop', 'infrastructure', 'email legacy'),
    ('pop3', 'infrastructure', 'email legacy'),
    ('ftp', 'infrastructure', 'file transfer'),
    ('sftp', 'infrastructure', 'file transfer'),
    ('ssh', 'infrastructure', 'shell access'),
    ('vpn', 'infrastructure', 'private network'),
    ('dns', 'infrastructure', 'name service'),
    ('ns', 'infrastructure', 'name service'),
    ('ns1', 'infrastructure', 'name service'),
    ('ns2', 'infrastructure', 'name service'),
    ('cdn', 'infrastructure', 'content delivery'),
    ('static', 'infrastructure', 'static assets'),
    ('assets', 'infrastructure', 'static assets'),
    ('media', 'infrastructure', 'uploaded media'),
    ('img', 'infrastructure', 'images'),
    ('images', 'infrastructure', 'images'),
    ('files', 'infrastructure', 'files'),
    ('upload', 'infrastructure', 'upload endpoint'),
    ('uploads', 'infrastructure', 'upload endpoint'),
    ('storage', 'infrastructure', 'storage'),

    -- Auth / admin / system
    ('admin', 'security', 'administration'),
    ('administrator', 'security', 'administration'),
    ('root', 'security', 'superuser'),
    ('superadmin', 'security', 'system admin'),
    ('sysadmin', 'security', 'system admin'),
    ('login', 'security', 'authentication'),
    ('signup', 'security', 'registration'),
    ('signin', 'security', 'authentication'),
    ('register', 'security', 'registration'),
    ('auth', 'security', 'authentication'),
    ('oauth', 'security', 'authentication'),
    ('sso', 'security', 'single sign on'),
    ('saml', 'security', 'authentication'),
    ('logout', 'security', 'authentication'),
    ('reset', 'security', 'authentication'),
    ('verify', 'security', 'authentication'),
    ('secure', 'security', 'security'),
    ('security', 'security', 'security'),
    ('ssl', 'security', 'TLS'),
    ('tls', 'security', 'TLS'),

    -- API / app surfaces
    ('api', 'reserved_app', 'API endpoint'),
    ('app', 'reserved_app', 'main app'),
    ('apps', 'reserved_app', 'main app'),
    ('dashboard', 'reserved_app', 'dashboard'),
    ('panel', 'reserved_app', 'admin panel'),
    ('portal', 'reserved_app', 'portal'),
    ('console', 'reserved_app', 'console'),
    ('manager', 'reserved_app', 'manager'),
    ('webhooks', 'reserved_app', 'webhook receiver'),
    ('webhook', 'reserved_app', 'webhook receiver'),
    ('events', 'reserved_app', 'event stream'),
    ('graphql', 'reserved_app', 'GraphQL endpoint'),
    ('grpc', 'reserved_app', 'gRPC endpoint'),
    ('ws', 'reserved_app', 'websocket'),
    ('socket', 'reserved_app', 'websocket'),

    -- Status / monitoring
    ('status', 'monitoring', 'status page'),
    ('health', 'monitoring', 'health check'),
    ('healthz', 'monitoring', 'health check'),
    ('readiness', 'monitoring', 'health check'),
    ('liveness', 'monitoring', 'health check'),
    ('metrics', 'monitoring', 'metrics'),
    ('logs', 'monitoring', 'logs'),
    ('monitoring', 'monitoring', 'monitoring'),
    ('grafana', 'monitoring', 'grafana'),
    ('kibana', 'monitoring', 'kibana'),

    -- Billing / commerce
    ('billing', 'billing', 'billing'),
    ('pay', 'billing', 'payment'),
    ('payment', 'billing', 'payment'),
    ('payments', 'billing', 'payment'),
    ('checkout', 'billing', 'checkout'),
    ('invoice', 'billing', 'invoice'),
    ('invoices', 'billing', 'invoice'),
    ('stripe', 'billing', 'stripe webhook'),
    ('subscribe', 'billing', 'subscription'),
    ('subscription', 'billing', 'subscription'),

    -- Marketing / public
    ('home', 'reserved_marketing', 'landing'),
    ('site', 'reserved_marketing', 'public site'),
    ('marketing', 'reserved_marketing', 'marketing'),
    ('blog', 'reserved_marketing', 'blog'),
    ('news', 'reserved_marketing', 'news'),
    ('docs', 'reserved_marketing', 'documentation'),
    ('documentation', 'reserved_marketing', 'documentation'),
    ('help', 'reserved_marketing', 'help center'),
    ('support', 'reserved_marketing', 'support'),
    ('contact', 'reserved_marketing', 'contact'),
    ('about', 'reserved_marketing', 'about'),
    ('legal', 'reserved_marketing', 'legal'),
    ('terms', 'reserved_marketing', 'terms'),
    ('privacy', 'reserved_marketing', 'privacy'),
    ('press', 'reserved_marketing', 'press'),
    ('careers', 'reserved_marketing', 'careers'),
    ('jobs', 'reserved_marketing', 'careers'),
    ('partners', 'reserved_marketing', 'partners'),

    -- Casehub product brand
    ('casehub', 'brand_casehub', 'product brand'),
    ('case-hub', 'brand_casehub', 'product brand'),
    ('case', 'brand_casehub', 'product brand'),
    ('hub', 'brand_casehub', 'product brand'),
    ('maestro', 'brand_casehub', 'feature brand'),
    ('controladoria', 'brand_casehub', 'feature brand'),
    ('agenda', 'brand_casehub', 'feature brand'),
    ('processos', 'brand_casehub', 'feature brand'),
    ('clientes', 'brand_casehub', 'feature brand'),
    ('tarefas', 'brand_casehub', 'feature brand'),

    -- Vingren / org brand
    ('vingren', 'brand_company', 'company brand'),
    ('victor', 'brand_company', 'owner'),
    ('vitor', 'brand_company', 'owner alt'),
    ('ilc', 'brand_company', 'related company'),

    -- Existing customer reservations (prevent squatting of legitimate clients)
    ('cliente-alpha', 'brand_customer', 'o cliente — alpha customer'),
    ('vs', 'brand_customer', 'o cliente abbreviation'),
    ('vieira-salles', 'brand_customer', 'o cliente hyphenated'),
    ('vieira', 'brand_customer', 'o cliente short'),
    ('vsadv', 'brand_customer', 'o cliente abbreviation'),

    -- Common envs / staging
    ('dev', 'environment', 'development'),
    ('develop', 'environment', 'development'),
    ('staging', 'environment', 'staging'),
    ('stage', 'environment', 'staging'),
    ('test', 'environment', 'test'),
    ('tests', 'environment', 'test'),
    ('qa', 'environment', 'quality assurance'),
    ('uat', 'environment', 'user acceptance testing'),
    ('preview', 'environment', 'preview'),
    ('prod', 'environment', 'production'),
    ('production', 'environment', 'production'),
    ('sandbox', 'environment', 'sandbox'),
    ('demo', 'environment', 'demo'),
    ('alpha', 'environment', 'alpha'),
    ('beta', 'environment', 'beta'),

    -- Government / BR legal (anti-spoofing in law-firm context)
    ('gov', 'reserved_government', 'government'),
    ('oab', 'reserved_government', 'Order of Lawyers'),
    ('cnj', 'reserved_government', 'National Council of Justice'),
    ('stf', 'reserved_government', 'Supreme Federal Court'),
    ('stj', 'reserved_government', 'Superior Court of Justice'),
    ('tjsp', 'reserved_government', 'TJ-SP'),
    ('tjrj', 'reserved_government', 'TJ-RJ'),
    ('tjmg', 'reserved_government', 'TJ-MG'),
    ('tjrs', 'reserved_government', 'TJ-RS'),
    ('tjpr', 'reserved_government', 'TJ-PR'),
    ('tjsc', 'reserved_government', 'TJ-SC'),
    ('tjba', 'reserved_government', 'TJ-BA'),
    ('tjdf', 'reserved_government', 'TJ-DF'),
    ('trf1', 'reserved_government', 'TRF-1'),
    ('trf2', 'reserved_government', 'TRF-2'),
    ('trf3', 'reserved_government', 'TRF-3'),
    ('trf4', 'reserved_government', 'TRF-4'),
    ('trf5', 'reserved_government', 'TRF-5'),
    ('pje', 'reserved_government', 'PJe'),
    ('datajud', 'reserved_government', 'DataJud'),
    ('pdpj', 'reserved_government', 'PDPJ'),
    ('justica', 'reserved_government', 'justice'),
    ('judiciario', 'reserved_government', 'judiciary'),
    ('mp', 'reserved_government', 'public ministry'),

    -- Inappropriate / brand-safety
    ('porn', 'reserved_inappropriate', 'inappropriate'),
    ('sex', 'reserved_inappropriate', 'inappropriate'),
    ('casino', 'reserved_inappropriate', 'inappropriate'),
    ('xxx', 'reserved_inappropriate', 'inappropriate'),

    -- Misc
    ('null', 'reserved_misc', 'reserved word'),
    ('undefined', 'reserved_misc', 'reserved word'),
    ('true', 'reserved_misc', 'reserved word'),
    ('false', 'reserved_misc', 'reserved word')
ON CONFLICT (slug) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 7. Verification: log row counts (visible in psql output)
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    reserved_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO reserved_count FROM reserved_subdomains;
    RAISE NOTICE 'Migration 2026-05-24_onboarding_subdomain.sql applied. reserved_subdomains rows: %', reserved_count;
END $$;
