-- Controladoria: manual deadlines need enough party context to avoid
-- unidentified process-number-only rows.

ALTER TABLE prazos_processuais ADD COLUMN IF NOT EXISTS processo_override VARCHAR;
ALTER TABLE prazos_processuais ADD COLUMN IF NOT EXISTS cliente_override VARCHAR;
ALTER TABLE prazos_processuais ADD COLUMN IF NOT EXISTS parte_contraria_override VARCHAR;
