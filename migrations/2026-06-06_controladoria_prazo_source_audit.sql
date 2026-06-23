-- Controladoria: provenance/audit fields for imported procedural deadlines.
-- Keeps official PDPJ/ComunicaAPI deadlines distinct from manual/subsidiary data.

ALTER TABLE prazos_processuais ADD COLUMN IF NOT EXISTS source_provider VARCHAR(120);
ALTER TABLE prazos_processuais ADD COLUMN IF NOT EXISTS source_status VARCHAR(50) DEFAULT 'manual';
ALTER TABLE prazos_processuais ADD COLUMN IF NOT EXISTS source_reference VARCHAR(255);
ALTER TABLE prazos_processuais ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE prazos_processuais ADD COLUMN IF NOT EXISTS source_payload_hash VARCHAR(64);
ALTER TABLE prazos_processuais ADD COLUMN IF NOT EXISTS source_fetched_at TIMESTAMP;
ALTER TABLE prazos_processuais ADD COLUMN IF NOT EXISTS source_version VARCHAR(80);
ALTER TABLE prazos_processuais ADD COLUMN IF NOT EXISTS official_source BOOLEAN DEFAULT FALSE;
ALTER TABLE prazos_processuais ADD COLUMN IF NOT EXISTS calculation_engine_version VARCHAR(80);
ALTER TABLE prazos_processuais ADD COLUMN IF NOT EXISTS calculation_notes TEXT;

CREATE INDEX IF NOT EXISTS ix_prazos_org_source_status
    ON prazos_processuais (org_id, source_status);

CREATE INDEX IF NOT EXISTS ix_prazos_org_source_hash
    ON prazos_processuais (org_id, source_payload_hash);
