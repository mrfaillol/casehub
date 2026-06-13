-- Migration: User real-presence timestamp
-- Date: 2026-06-05
-- Purpose: Support AuditContextMiddleware real-presence updates and dashboard
--          "Online agora" without crashing existing dev/alpha databases.
-- Idempotent: safe to re-run.

ALTER TABLE users ADD COLUMN IF NOT EXISTS last_activity TIMESTAMP WITH TIME ZONE;

CREATE INDEX IF NOT EXISTS ix_users_last_activity ON users(last_activity);
