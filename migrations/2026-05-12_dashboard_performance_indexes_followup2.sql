-- Follow-up #2 CaseHub dashboard performance indexes (VALIDADO EM ORACLE-DEV).
--
-- Issue: #283 (perf P0 post-HALT — índices compostos para queries do dashboard).
--
-- Validado em Oracle-dev/casehub_dev em 2026-05-15:
--   1. EXPLAIN ANALYZE da query do widget de prazos no snapshot Oracle-dev
--      confirmou Seq Scan antes e Index Scan depois;
--   2. nomes reais confirmados: reminders(org_id, due_date, is_completed);
--   3. benchmark p95 caiu de 1.198 ms para 0.116 ms (~90%).
-- Ver docs/performance/2026-05-12-dashboard-index-followup-candidates.md.
--
-- Run manually against PostgreSQL with autocommit enabled. These statements use
-- CREATE INDEX CONCURRENTLY and therefore must not run inside a transaction.
-- Example:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/2026-05-12_dashboard_performance_indexes_followup2.sql

-- routes/dashboard_api.py::_widget_prazos:
--   tenant_query(Reminder, org_id)
--     .filter(due_date >= <hoje 00:00>, due_date <= <hoje+7d 23:59>, is_completed IS FALSE)
--     .order_by(due_date ASC).limit(5)
-- As migrations 2026-05-02 / 2026-05-07 cobriram tasks.due_date mas nunca
-- reminders.due_date. Índice parcial (só reminders abertos) cobre o WHERE + ORDER BY:
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_reminders_org_due_open
    ON reminders (org_id, due_date)
    WHERE is_completed IS FALSE;

-- ROLLBACK:
--   DROP INDEX CONCURRENTLY IF EXISTS idx_reminders_org_due_open;
