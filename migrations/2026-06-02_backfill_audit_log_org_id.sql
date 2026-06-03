-- migrations/2026-06-02_backfill_audit_log_org_id.sql
-- Backfill audit_log.org_id for legacy rows BEFORE enabling tenant scoping in routes/audit.py.
--
-- Why: the org_id column exists but legacy rows were never populated (NULL). Applying the
-- WHERE al.org_id = :org_id filter without backfill returns zero rows -> audit view goes dark
-- (this already happened once and was reverted, commit dd0e0f62). Run THIS first, deploy the
-- route filter SECOND.
--
-- Properties: idempotent (only touches NULL rows), no DELETE/TRUNCATE, preserves the full trail.
--
-- !! PRODUCTION WARNING !!
-- Step 2 assigns orphan rows (no user / user without org) to a FALLBACK org id.
-- The fallback below is `1` (correct for DEV, slug='dev'). In PRODUCTION you MUST set this to
-- the correct tenant or a dedicated 'system' org id for that instance -- do NOT guess. Confirm
-- with `SELECT id, slug FROM organizations;` before running.

BEGIN;

-- 1) Rows linked to a user: inherit the user's organization.
UPDATE audit_log al
SET org_id = u.org_id
FROM users u
WHERE al.org_id IS NULL
  AND al.user_id = u.id
  AND u.org_id IS NOT NULL;

-- 2) Orphan rows (no user_id, or user without org): assign to the environment fallback org.
--    REPLACE `1` with the correct fallback org id for this environment before running in prod.
UPDATE audit_log
SET org_id = 1
WHERE org_id IS NULL;

COMMIT;

-- 3) Verify (must return 0):
--    SELECT count(*) FROM audit_log WHERE org_id IS NULL;
-- 4) Verify total unchanged (no data zeroed):
--    SELECT count(*) FROM audit_log;
