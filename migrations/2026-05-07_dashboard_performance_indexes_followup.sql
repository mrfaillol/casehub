-- Follow-up CaseHub dashboard performance indexes.
--
-- Run manually against PostgreSQL with autocommit enabled. These statements use
-- CREATE INDEX CONCURRENTLY and therefore must not run inside a transaction.
-- They cover access patterns still observed as sequential scans after the
-- 2026-05-02 dashboard index migration on the Oracle dev benchmark snapshot.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_org_due_created_open
    ON tasks (org_id, due_date ASC NULLS LAST, created_at DESC)
    WHERE status <> 'completed';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cases_org_updated_created
    ON cases (org_id, updated_at DESC NULLS LAST, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_time_entries_org_date
    ON time_entries (org_id, date);
