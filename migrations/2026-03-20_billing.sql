-- ============================================================================
-- CaseHub Billing / Plans Migration
-- Date: 2026-03-20
-- Description: Creates the plans table and seeds the three subscription tiers.
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. plans table
-- ============================================================================
CREATE TABLE IF NOT EXISTS plans (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(50) NOT NULL UNIQUE,
    display_name    VARCHAR(100),
    price_monthly   INTEGER NOT NULL,                  -- cents (USD)
    stripe_price_id VARCHAR(255),                      -- set after Stripe product creation
    max_users       INTEGER DEFAULT 5,
    max_cases       INTEGER DEFAULT 50,
    features        JSONB DEFAULT '[]'::jsonb,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- 2. Seed default plans
-- ============================================================================
INSERT INTO plans (name, display_name, price_monthly, max_users, max_cases, features)
VALUES
    (
        'starter',
        'Starter',
        29900,
        3,
        25,
        '["cases","clients","documents","drive_sync","email","tasks"]'::jsonb
    ),
    (
        'professional',
        'Professional',
        69900,
        -1,
        100,
        '["cases","clients","documents","drive_sync","email","tasks","ai_lor","ai_ps","package_builder","crm","whatsapp","reports"]'::jsonb
    ),
    (
        'enterprise',
        'Enterprise',
        149900,
        -1,
        -1,
        '["cases","clients","documents","drive_sync","email","tasks","ai_lor","ai_ps","package_builder","crm","whatsapp","reports","sso","custom_domain","api_access","audit","priority_support"]'::jsonb
    )
ON CONFLICT (name) DO NOTHING;

COMMIT;
