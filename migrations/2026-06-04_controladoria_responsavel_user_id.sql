-- Controladoria: connect prazo responsaveis to users while preserving legacy names.
ALTER TABLE prazos_processuais ADD COLUMN IF NOT EXISTS responsavel_user_id INTEGER;

UPDATE prazos_processuais p
SET responsavel_user_id = u.id
FROM users u
WHERE p.responsavel_user_id IS NULL
  AND p.org_id = u.org_id
  AND LOWER(TRIM(p.responsavel)) = LOWER(TRIM(u.name));

CREATE INDEX IF NOT EXISTS ix_prazos_org_responsavel_user
    ON prazos_processuais (org_id, responsavel_user_id);
