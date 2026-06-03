-- Kanban: dynamic columns (K1-K3)
-- Replaces hardcoded 4 statuses with user-configurable columns

CREATE TABLE IF NOT EXISTS kanban_columns (
    id SERIAL PRIMARY KEY,
    org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(50) NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    color VARCHAR(20) DEFAULT '#94a3b8',
    is_done BOOLEAN DEFAULT FALSE,  -- marks "completed" equivalent
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kanban_columns_org ON kanban_columns(org_id, position);

-- Seed default columns for existing orgs
INSERT INTO kanban_columns (org_id, name, slug, position, color, is_done)
SELECT DISTINCT o.id, 'Pendente', 'pendente', 0, '#94a3b8', FALSE
FROM organizations o
WHERE NOT EXISTS (SELECT 1 FROM kanban_columns kc WHERE kc.org_id = o.id)
ON CONFLICT DO NOTHING;

INSERT INTO kanban_columns (org_id, name, slug, position, color, is_done)
SELECT DISTINCT o.id, 'Em Andamento', 'em_andamento', 1, '#3b82f6', FALSE
FROM organizations o
WHERE NOT EXISTS (SELECT 1 FROM kanban_columns kc WHERE kc.org_id = o.id AND kc.slug = 'em_andamento')
ON CONFLICT DO NOTHING;

INSERT INTO kanban_columns (org_id, name, slug, position, color, is_done)
SELECT DISTINCT o.id, 'Bloqueada', 'blocked', 2, '#ef4444', FALSE
FROM organizations o
WHERE NOT EXISTS (SELECT 1 FROM kanban_columns kc WHERE kc.org_id = o.id AND kc.slug = 'blocked')
ON CONFLICT DO NOTHING;

INSERT INTO kanban_columns (org_id, name, slug, position, color, is_done)
SELECT DISTINCT o.id, 'Concluida', 'completed', 3, '#22c55e', TRUE
FROM organizations o
WHERE NOT EXISTS (SELECT 1 FROM kanban_columns kc WHERE kc.org_id = o.id AND kc.slug = 'completed')
ON CONFLICT DO NOTHING;

-- Add column_id to tasks (nullable — old tasks use status field)
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS column_id INTEGER REFERENCES kanban_columns(id);
