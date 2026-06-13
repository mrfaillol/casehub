-- Adiciona coluna "Aguarda Correção" ao kanban de todas as orgs que ainda não a têm
INSERT INTO kanban_columns (org_id, name, slug, position, color, is_done, visibility)
SELECT o.id, 'Aguarda Correção', 'awaiting_correction', 4, '#f59e0b', false, 'shared'
FROM organizations o
WHERE NOT EXISTS (
    SELECT 1 FROM kanban_columns kc
    WHERE kc.org_id = o.id AND kc.slug = 'awaiting_correction'
)
ON CONFLICT DO NOTHING;
