-- Fix: a tabela `contacts` não tinha a coluna `org_id`, mas routes/contacts.py
-- faz INSERT/SELECT com org_id → POST /contacts/create dava HTTP 500 (módulo morto)
-- E os contatos não tinham isolamento de tenant (gap de IDOR multi-tenant).
-- Aditivo, idempotente. Aplicado manualmente no Mumbai (alpha) em 2026-05-29 (0 linhas → sem backfill).
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS org_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_contacts_org_id ON contacts(org_id);
