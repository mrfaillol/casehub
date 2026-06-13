-- Agenda: lightweight Trello-like details for commitments.
-- Maria feedback via WhatsApp video 2026-06-12.

ALTER TABLE appointments ADD COLUMN IF NOT EXISTS checklist TEXT;
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS attachments TEXT;

CREATE TABLE IF NOT EXISTS appointment_attachments (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL,
    appointment_id INTEGER NOT NULL,
    file_path VARCHAR(255) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    mime_type VARCHAR(120),
    size_bytes INTEGER,
    uploaded_by INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_appointment_attachments_org_appt
    ON appointment_attachments(org_id, appointment_id);
