-- Task privacy (Equipe CaseHub 03/06/2026: "listas privadas bem claras")
-- Tarefa privada (visibility='private') só é visível ao CRIADOR (created_by) e ao
-- RESPONSÁVEL (assigned_to), sempre org-scoped. Default 'org' preserva o comportamento
-- atual (toda a org vê) p/ não quebrar tarefas existentes.
--
-- Idempotente: o app também cria estas colunas via _ensure_kanban_schema() (lazy).
-- Este arquivo versiona a migração para auditoria/deploy explícito.
-- Postgres >= 9.6 suporta ADD COLUMN IF NOT EXISTS.

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS visibility VARCHAR(20) DEFAULT 'org';
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS created_by INTEGER;

-- Backfill defensivo: tarefas legadas sem visibility ficam 'org' (visíveis a toda a org).
UPDATE tasks SET visibility = 'org' WHERE visibility IS NULL;

-- Index parcial p/ acelerar o filtro de privacidade no Kanban (org + privacidade + dono).
CREATE INDEX IF NOT EXISTS ix_tasks_visibility_owner
  ON tasks (org_id, visibility, created_by, assigned_to);
