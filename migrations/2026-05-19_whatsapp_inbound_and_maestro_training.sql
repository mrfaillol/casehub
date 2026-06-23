-- Migration: WhatsApp inbound support + field-request tracking + Maestro training samples
-- Date: 2026-05-19
-- Author: Claude Opus 4.7 (session-2026-05-19-maestro-backend, authorized by Equipe CaseHub 19/05)
--
-- Purpose:
--   1. Enable inbound WhatsApp messages to be persisted on existing whatsapp_messages table
--      (additive ALTERs — schema already has `direction` column from 2026-03-30 migration).
--   2. Track "field requests" sent to clients ("we need your CEP — please reply").
--   3. Seed schema for Maestro training-sample collection (DISABLED by default — gate via
--      CASEHUB_MAESTRO_TRAINING_COLLECTION_ENABLED env flag + per-org consent).
--
-- Idempotency: all CREATE / ALTER statements use IF (NOT) EXISTS guards. Safe to re-run.

-- ============================================================
-- 1. Extend whatsapp_messages for inbound flow (additive)
-- ============================================================
ALTER TABLE whatsapp_messages
    ADD COLUMN IF NOT EXISTS from_phone VARCHAR(64);

ALTER TABLE whatsapp_messages
    ADD COLUMN IF NOT EXISTS inbound_processed_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE whatsapp_messages
    ADD COLUMN IF NOT EXISTS inbound_processed_by_user_id INTEGER
        REFERENCES users(id) ON DELETE SET NULL;

ALTER TABLE whatsapp_messages
    ADD COLUMN IF NOT EXISTS raw_payload JSONB;

ALTER TABLE whatsapp_messages
    ADD COLUMN IF NOT EXISTS media_type VARCHAR(32);
    -- 'text' | 'image' | 'audio' | 'document' | 'video' | 'unsupported'

CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_inbound_unprocessed
    ON whatsapp_messages(org_id, inbound_processed_at)
    WHERE direction = 'incoming' AND inbound_processed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_client
    ON whatsapp_messages(client_id) WHERE client_id IS NOT NULL;

-- ============================================================
-- 2. whatsapp_field_requests — admin-initiated "please send me X" flow
-- ============================================================
CREATE TABLE IF NOT EXISTS whatsapp_field_requests (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    requested_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,

    -- Which field on the client/case we want filled (e.g., 'cep', 'cpf', 'rg', 'profession')
    field_name VARCHAR(64) NOT NULL,
    field_label VARCHAR(128) NOT NULL,
    field_target VARCHAR(32) DEFAULT 'client',
        -- 'client' | 'case' | 'document' — which entity this fills

    -- The exact message dispatched (for audit / retraining)
    message_sent TEXT NOT NULL,
    whatsapp_message_id INTEGER REFERENCES whatsapp_messages(id) ON DELETE SET NULL,
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Linked inbound response (filled by inbound handler when matching succeeds)
    responded_inbound_id INTEGER REFERENCES whatsapp_messages(id) ON DELETE SET NULL,
    responded_at TIMESTAMP WITH TIME ZONE,

    -- Final resolution by admin (the value they pasted into the actual field)
    resolved_value TEXT,
    resolved_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    resolved_at TIMESTAMP WITH TIME ZONE,

    -- For UI display / cancel flow
    cancelled_at TIMESTAMP WITH TIME ZONE,
    cancelled_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_whatsapp_field_requests_client_pending
    ON whatsapp_field_requests(client_id, resolved_at)
    WHERE resolved_at IS NULL AND cancelled_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_whatsapp_field_requests_org_pending
    ON whatsapp_field_requests(org_id, resolved_at)
    WHERE resolved_at IS NULL AND cancelled_at IS NULL;

-- ============================================================
-- 3. maestro_training_samples — gated dataset for ML pipeline (beta agosto)
-- ============================================================
-- IMPORTANT: rows are inserted only when:
--   - CASEHUB_MAESTRO_TRAINING_COLLECTION_ENABLED=true (env)
--   - AND org has explicit per-provider consent recorded (org_settings).
-- Default behavior is OFF until Council ruling on Maestro pipeline implementation (ref PR #479).

CREATE TABLE IF NOT EXISTS maestro_training_samples (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- Source linkage
    source_inbound_id INTEGER REFERENCES whatsapp_messages(id) ON DELETE SET NULL,
    source_field_request_id INTEGER REFERENCES whatsapp_field_requests(id) ON DELETE SET NULL,
    source_field_name VARCHAR(64),

    -- The (admin-validated) labelled example
    raw_message TEXT NOT NULL,           -- the inbound message body
    extracted_value TEXT,                -- the value the admin pasted as correct
    validated_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    validated_at TIMESTAMP WITH TIME ZONE,
    is_correct_label BOOLEAN,            -- could be FALSE if admin rejected
    label_provenance VARCHAR(32) DEFAULT 'admin_resolve',
        -- 'admin_resolve' | 'admin_correct' | 'admin_reject' | 'auto_synthetic'

    -- Consent / provenance audit
    consent_recorded BOOLEAN DEFAULT FALSE,
    consent_provider VARCHAR(32),
        -- which LLM provider's DPA covers this sample if used in training/eval
    redaction_applied BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_maestro_training_samples_org_field
    ON maestro_training_samples(org_id, source_field_name);

CREATE INDEX IF NOT EXISTS idx_maestro_training_samples_eligibility
    ON maestro_training_samples(consent_recorded, is_correct_label)
    WHERE consent_recorded = TRUE AND is_correct_label = TRUE;

-- ============================================================
-- 4. org_settings: maestro training opt-in flag (idempotent)
-- ============================================================
-- Assumes org_settings table exists from earlier multitenant migration.
-- If not present, this is a no-op (would error; should fail-fast).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'org_settings') THEN
        BEGIN
            ALTER TABLE org_settings
                ADD COLUMN IF NOT EXISTS maestro_training_consent BOOLEAN DEFAULT FALSE;
            ALTER TABLE org_settings
                ADD COLUMN IF NOT EXISTS maestro_training_consent_provider VARCHAR(32);
            ALTER TABLE org_settings
                ADD COLUMN IF NOT EXISTS maestro_training_consent_recorded_at TIMESTAMP WITH TIME ZONE;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'org_settings consent columns: %', SQLERRM;
        END;
    ELSE
        RAISE NOTICE 'org_settings table not present — skipping maestro consent columns. Add in later migration.';
    END IF;
END $$;
