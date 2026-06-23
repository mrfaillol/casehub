-- Card attachments (FB3, alpha UsuarioDemo): anexar documento no cartão Kanban (Trello-style).
-- Adiciona documents.task_id (FK lógica -> tasks.id). Nullable: a grande maioria dos
-- documentos NÃO pertence a uma tarefa (continuam ligados a client/case). ON DELETE SET
-- NULL preserva o arquivo quando a tarefa é apagada — o documento vira solto da org, não
-- some junto com o cartão.
--
-- Idempotente: o app também cria esta coluna via _ensure_kanban_schema() (lazy, roda no
-- load do board). Este arquivo versiona a migração para auditoria/deploy explícito.
-- Postgres >= 9.6 suporta ADD COLUMN IF NOT EXISTS.

ALTER TABLE documents ADD COLUMN IF NOT EXISTS task_id INTEGER;

-- FK só é adicionada se ainda não existir (Postgres não tem ADD CONSTRAINT IF NOT EXISTS).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_documents_task_id'
          AND table_name = 'documents'
    ) THEN
        ALTER TABLE documents
            ADD CONSTRAINT fk_documents_task_id
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL;
    END IF;
END$$;

-- Index p/ listar anexos por cartão (GET /tasks/api/{id}/documents).
CREATE INDEX IF NOT EXISTS idx_documents_task_id ON documents (task_id);
