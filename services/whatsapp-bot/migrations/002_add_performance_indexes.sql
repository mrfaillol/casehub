-- Migration 002: Add missing indexes for common query patterns
-- Date: 2026-03-06

-- leads: conversation_state is queried by message-handler, lead-monitor
CREATE INDEX IF NOT EXISTS idx_conversation_state ON leads(conversation_state);

-- leads: contact_type is queried by known-clients, message-handler
CREATE INDEX IF NOT EXISTS idx_contact_type ON leads(contact_type);

-- leads: bot_enabled + human_takeover checked on every incoming message
CREATE INDEX IF NOT EXISTS idx_bot_enabled ON leads(bot_enabled);

-- leads: never_contact checked on every incoming message
CREATE INDEX IF NOT EXISTS idx_never_contact ON leads(never_contact);

-- leads: source_platform for analytics
CREATE INDEX IF NOT EXISTS idx_source_platform ON leads(source_platform);

-- leads: last_interaction for lead-monitor age queries
CREATE INDEX IF NOT EXISTS idx_last_interaction ON leads(last_interaction);

-- conversations: compound index for dedup check in message_create handler
CREATE INDEX IF NOT EXISTS idx_phone_role_created ON conversations(phone, role, created_at)
