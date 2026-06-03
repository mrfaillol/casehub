-- ============================================================================
-- CaseHub Subscription — Two-Plan Pricing Reset
-- Date: 2026-05-28
-- Spec (Victor): exactly two plans + usuários ILIMITADOS por enquanto.
--   1. office     R$ 129/mês  — "Pequenos escritórios e Sociedade Unipessoal
--                                de Advocacia"
--   2. enterprise Sob consulta — grandes escritórios, sem preço fixo
--                                (CTA de contato, sem checkout self-service)
--
-- Conventions:
--   * price_monthly is INTEGER cents. Enterprise = 0 (sem preço fixo; o app
--     exibe "Sob consulta" via routes/subscription.PLAN_FEATURES.price_label).
--   * max_users = -1 => unlimited (ver middleware/plan_enforcement.py).
--   * stripe_price_id NÃO é inventado aqui — fica NULL até ser provisionado
--     no Stripe e configurado (env STRIPE_PRICE_OFFICE ou via superadmin).
--
-- Idempotente: pode rodar mais de uma vez sem efeito colateral.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. Canonical plan rows
-- ----------------------------------------------------------------------------
INSERT INTO plans (name, display_name, price_monthly, max_users, max_cases, features, is_active)
VALUES
    (
        'office',
        'Pequenos escritórios e Sociedade Unipessoal de Advocacia',
        12900,        -- R$ 129,00 (cents)
        -1,           -- usuários ilimitados (por enquanto)
        -1,           -- processos ilimitados (por enquanto)
        '["cases","clients","documents","drive_sync","email","tasks","ai_lor","ai_ps","package_builder","crm","whatsapp","reports"]'::jsonb,
        TRUE
    ),
    (
        'enterprise',
        'Enterprise',
        0,            -- sob consulta — sem preço fixo
        -1,           -- usuários ilimitados (por enquanto)
        -1,
        '["cases","clients","documents","drive_sync","email","tasks","ai_lor","ai_ps","package_builder","crm","whatsapp","reports","sso","custom_domain","api_access","audit","priority_support"]'::jsonb,
        TRUE
    )
ON CONFLICT (name) DO UPDATE SET
    display_name  = EXCLUDED.display_name,
    price_monthly = EXCLUDED.price_monthly,
    max_users     = EXCLUDED.max_users,
    max_cases     = EXCLUDED.max_cases,
    features      = EXCLUDED.features,
    is_active     = TRUE,
    updated_at    = NOW();

-- ----------------------------------------------------------------------------
-- 2. Retire legacy plans (keep rows for history, hide from "available plans").
-- ----------------------------------------------------------------------------
UPDATE plans
SET is_active = FALSE, updated_at = NOW()
WHERE name IN ('starter', 'professional');

-- ----------------------------------------------------------------------------
-- 3. Migrate existing orgs off legacy plans → office, with unlimited users.
--    (Enterprise orgs, if any, are left as-is.)
-- ----------------------------------------------------------------------------
UPDATE organizations
SET plan = 'office',
    max_users = -1,
    updated_at = NOW()
WHERE plan IN ('starter', 'professional') OR plan IS NULL;

-- ----------------------------------------------------------------------------
-- 4. Belt-and-suspenders: usuários ilimitados em qualquer org (por enquanto).
--    Neutraliza limites de seats legados em orgs já existentes.
-- ----------------------------------------------------------------------------
UPDATE organizations
SET max_users = -1, updated_at = NOW()
WHERE max_users IS NULL OR max_users >= 0;

COMMIT;
