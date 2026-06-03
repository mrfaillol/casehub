CREATE TABLE IF NOT EXISTS whatsapp_messages (
    id SERIAL PRIMARY KEY,
    org_id INTEGER REFERENCES organizations(id),
    phone VARCHAR NOT NULL,
    direction VARCHAR DEFAULT 'outgoing',
    message TEXT,
    template_name VARCHAR,
    status VARCHAR DEFAULT 'sent',
    client_id INTEGER,
    case_id INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_org ON whatsapp_messages(org_id);
CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_phone ON whatsapp_messages(phone);
