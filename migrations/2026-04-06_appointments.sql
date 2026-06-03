-- Agenda: Appointments table (A1-A10)
-- Separate from tasks — [parceiro]: "nessa agenda NÃO ter tarefas, tarefas ficam no kanban"

CREATE TABLE IF NOT EXISTS appointments (
    id SERIAL PRIMARY KEY,
    org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL DEFAULT 'atendimento',  -- audiencia, reuniao, atendimento, outro
    assigned_to INTEGER REFERENCES users(id),
    client_name VARCHAR(255),
    case_id INTEGER REFERENCES cases(id),
    date DATE NOT NULL,
    time_start TIME,
    time_end TIME,
    is_virtual BOOLEAN DEFAULT FALSE,
    notes TEXT,
    color VARCHAR(20),  -- override (otherwise uses user color)
    gcal_event_id VARCHAR(255),  -- Google Calendar event ID for sync
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_appointments_org ON appointments(org_id, date);
CREATE INDEX IF NOT EXISTS idx_appointments_assigned ON appointments(assigned_to, date);

-- Add color field to users for per-collaborator colors
ALTER TABLE users ADD COLUMN IF NOT EXISTS color VARCHAR(20);

-- Set default colors for VS ([parceiro]=roxo, Lucas=vermelho, Valéria=rosa, [usuário]=azul)
-- These will be applied by the app on first load if not set
