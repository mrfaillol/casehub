-- financial_entries: soft-delete + trilha de edição inline (Financeiro editável, 2026-06-04).
-- ADITIVA e idempotente (ADD COLUMN IF NOT EXISTS). Aplicada automaticamente no
-- startup por core/app_factory.py::_run_pending_migrations (lista programática);
-- este arquivo versiona o schema vivo (sem commit, sem deploy).
--
-- Política (dado financeiro REAL, org 4 ~3913 lançamentos):
--   * "excluir" na UI NÃO faz DELETE. Faz UPDATE ... SET ativo = FALSE.
--   * Todas as leituras/agregações em /reports/financeiro filtram `ativo IS NOT FALSE`
--     (NULL legado e TRUE permanecem visíveis; só FALSE some dos totais).
--   * Restaurar = UPDATE ... SET ativo = TRUE.
-- 'ativo IS NOT FALSE' (em vez de '= TRUE') garante que linhas pré-existentes
-- com ativo NULL continuem contando, sem precisar de backfill.
ALTER TABLE financial_entries ADD COLUMN IF NOT EXISTS ativo BOOLEAN DEFAULT TRUE;
ALTER TABLE financial_entries ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;

-- Índice parcial: a maioria das queries quer só os ativos.
CREATE INDEX IF NOT EXISTS ix_fin_org_ativo ON financial_entries (org_id, ativo);
