-- Migration: Add Brazilian law fields for CaseHub Lite
-- Date: 2026-03-25
-- Description: Adds Brazil-specific fields to clients and cases tables
--              alongside existing immigration fields (backwards compatible)

-- === Clients table: Brazilian PII and metadata ===
ALTER TABLE clients ADD COLUMN IF NOT EXISTS cpf VARCHAR(200);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS rg VARCHAR(200);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS cnpj VARCHAR(200);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS oab_number VARCHAR(50);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS nationality VARCHAR(100);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS client_type VARCHAR(20) DEFAULT 'individual';

-- === Cases table: Brazilian court fields ===
ALTER TABLE cases ADD COLUMN IF NOT EXISTS numero_processo VARCHAR(50);
ALTER TABLE cases ADD COLUMN IF NOT EXISTS tipo_acao VARCHAR(100);
ALTER TABLE cases ADD COLUMN IF NOT EXISTS vara VARCHAR(100);
ALTER TABLE cases ADD COLUMN IF NOT EXISTS comarca VARCHAR(100);
ALTER TABLE cases ADD COLUMN IF NOT EXISTS tribunal VARCHAR(100);
ALTER TABLE cases ADD COLUMN IF NOT EXISTS fase_processual VARCHAR(100);
ALTER TABLE cases ADD COLUMN IF NOT EXISTS polo_ativo TEXT;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS polo_passivo TEXT;

-- Index for Brazilian process number lookups
CREATE INDEX IF NOT EXISTS ix_cases_numero_processo ON cases (numero_processo);
