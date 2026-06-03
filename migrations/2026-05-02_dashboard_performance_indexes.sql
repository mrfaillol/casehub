-- CaseHub dashboard performance indexes.
--
-- Run manually against PostgreSQL with autocommit enabled. These statements use
-- CREATE INDEX CONCURRENTLY and therefore must not run inside a transaction.
-- Example:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/2026-05-02_dashboard_performance_indexes.sql

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cases_org_status_updated_at
    ON cases (org_id, status, updated_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cases_org_created_at
    ON cases (org_id, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cases_org_expiration_status_open
    ON cases (org_id, expiration_date, status)
    WHERE expiration_date IS NOT NULL
      AND status NOT IN ('approved', 'denied', 'closed');

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_org_status_due_date_open
    ON tasks (org_id, status, due_date)
    WHERE status <> 'completed';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_billing_items_org_status_created_at
    ON billing_items (org_id, status, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_billing_items_org_status_paid_date
    ON billing_items (org_id, status, paid_date)
    WHERE paid_date IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_documents_org_created_at
    ON documents (org_id, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_clients_org_created_at
    ON clients (org_id, created_at DESC);
