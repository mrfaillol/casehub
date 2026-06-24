-- Task archive (FB2 alpha UsuarioDemo): arquivar CARTÃO do Kanban (soft-archive).
-- Antes só existia "Excluir" (hard delete) e apenas kanban_columns tinha is_archived.
-- Tarefa arquivada (is_archived=TRUE) some do board mas NÃO é apagada — reversível
-- via /tasks/api/{id}/unarchive. Default FALSE preserva tarefas legadas no board.
--
-- Idempotente: o app também cria estas colunas via _ensure_kanban_schema() (lazy).
-- Este arquivo versiona a migração para auditoria/deploy explícito.
-- Postgres >= 9.6 suporta ADD COLUMN IF NOT EXISTS.

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS is_archived BOOLEAN DEFAULT FALSE;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP;

-- Backfill defensivo: tarefas legadas sem flag ficam não-arquivadas (visíveis no board).
UPDATE tasks SET is_archived = FALSE WHERE is_archived IS NULL;

-- Index parcial p/ o board: filtra cartões ativos por org sem varrer arquivados.
CREATE INDEX IF NOT EXISTS ix_tasks_org_active
  ON tasks (org_id, column_id)
  WHERE COALESCE(is_archived, FALSE) = FALSE;
