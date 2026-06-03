-- Migration: WhatsApp Web clone — contacts / conversations / messages model
-- Date: 2026-05-21
-- Author: Claude Opus 4.7 (1M ctx) — WS-A backend, integration/whatsapp-clone-2026-05
--
-- Purpose:
--   Persistence layer for the web.whatsapp.com clone served at /casehub/whatsapp.
--   Three new tables (wa_contacts / wa_conversations / wa_messages). The bot
--   (services/whatsapp-bot) stays stateless — QR/status/send only — and inbound
--   messages are mirrored here so the FastAPI app owns conversation history.
--
--   The legacy flat `whatsapp_messages` table is intentionally LEFT UNTOUCHED:
--   the field-request matching flow (migration 2026-05-19) still depends on it.
--
-- Idempotency: every CREATE uses IF NOT EXISTS; any future column add must use a
--   guarded DO $$ ... $$ block (see §4 template). Safe to re-run.

-- ============================================================
-- 1. wa_contacts — one row per WhatsApp peer (person / business / group)
-- ============================================================
CREATE TABLE IF NOT EXISTS wa_contacts (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- Identity
    phone VARCHAR(32) NOT NULL,                 -- E.164, e.g. +5511999999999
    wa_jid VARCHAR(128),                        -- raw WhatsApp JID (xxx@c.us / xxx@g.us)
    display_name VARCHAR(255),                  -- WhatsApp pushname / group subject
    profile_pic_url TEXT,

    -- Classification
    is_business BOOLEAN DEFAULT FALSE,
    is_group BOOLEAN DEFAULT FALSE,

    -- CRM linkage (Tier 3 power-features; nullable until a human links)
    client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
    tags JSONB DEFAULT '[]'::jsonb,             -- array of free-form tag strings
    lead_stage VARCHAR(32),                     -- pipeline column: new|contacted|qualified|...

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT uq_wa_contacts_org_phone UNIQUE (org_id, phone)
);

CREATE INDEX IF NOT EXISTS idx_wa_contacts_org
    ON wa_contacts(org_id);
CREATE INDEX IF NOT EXISTS idx_wa_contacts_client
    ON wa_contacts(client_id) WHERE client_id IS NOT NULL;

-- ============================================================
-- 2. wa_conversations — one thread per contact
-- ============================================================
CREATE TABLE IF NOT EXISTS wa_conversations (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    contact_id INTEGER NOT NULL REFERENCES wa_contacts(id) ON DELETE CASCADE,

    -- Recency / ordering authority
    last_message_id INTEGER,                    -- soft ref to wa_messages.id (no FK: avoids cycle)
    last_message_at TIMESTAMP WITH TIME ZONE,
    unread_count INTEGER DEFAULT 0,

    -- WhatsApp-style flags
    archived BOOLEAN DEFAULT FALSE,
    pinned BOOLEAN DEFAULT FALSE,
    muted_until TIMESTAMP WITH TIME ZONE,

    -- Bot / human-takeover control
    bot_enabled BOOLEAN DEFAULT TRUE,
    human_takeover BOOLEAN DEFAULT FALSE,
    assigned_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT uq_wa_conversations_org_contact UNIQUE (org_id, contact_id)
);

-- Conversation list ordering (most recent first), tenant-scoped.
CREATE INDEX IF NOT EXISTS idx_wa_conversations_org_recency
    ON wa_conversations(org_id, last_message_at DESC);
CREATE INDEX IF NOT EXISTS idx_wa_conversations_contact
    ON wa_conversations(contact_id);

-- ============================================================
-- 3. wa_messages — message ledger
-- ============================================================
CREATE TABLE IF NOT EXISTS wa_messages (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    conversation_id INTEGER NOT NULL REFERENCES wa_conversations(id) ON DELETE CASCADE,

    -- Dedup key: WhatsApp message id (e.g. "true_5511...@c.us_3EB0...").
    wa_message_id VARCHAR(128),

    direction VARCHAR(16) NOT NULL DEFAULT 'incoming',  -- 'incoming' | 'outgoing'
    body TEXT,

    -- Media
    media_type VARCHAR(32),                     -- text|image|audio|video|document|sticker|ptt
    media_url TEXT,
    media_mime VARCHAR(128),
    media_filename VARCHAR(255),

    -- Delivery ticks: pending|sent|delivered|read|played|failed
    status VARCHAR(16) DEFAULT 'sent',

    -- Threading / reactions
    reply_to_message_id INTEGER REFERENCES wa_messages(id) ON DELETE SET NULL,
    reactions JSONB DEFAULT '[]'::jsonb,        -- [{emoji, author_phone, ts}, ...]

    from_me BOOLEAN DEFAULT FALSE,
    author_phone VARCHAR(32),                   -- sender (useful in group threads)

    -- sent_at is the WhatsApp-native timestamp — authority for message ORDER.
    sent_at TIMESTAMP WITH TIME ZONE,
    edited_at TIMESTAMP WITH TIME ZONE,
    deleted_at TIMESTAMP WITH TIME ZONE,

    ai_generated BOOLEAN DEFAULT FALSE,         -- TRUE if body came from AI assist (audit)

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT uq_wa_messages_org_wamid UNIQUE (org_id, wa_message_id)
);

-- Message history scroll within a conversation, ordered by WhatsApp timestamp.
CREATE INDEX IF NOT EXISTS idx_wa_messages_conv_sent
    ON wa_messages(conversation_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_wa_messages_org
    ON wa_messages(org_id);

-- ============================================================
-- 4. Guarded column-add template (for future additive changes)
-- ============================================================
-- Keep additive ALTERs idempotent. Example (no-op today; left as the canonical
-- pattern WS-D / future migrations should copy):
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'wa_conversations') THEN
        BEGIN
            ALTER TABLE wa_conversations
                ADD COLUMN IF NOT EXISTS pinned_at TIMESTAMP WITH TIME ZONE;
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'wa_conversations.pinned_at: %', SQLERRM;
        END;
    END IF;
END $$;
