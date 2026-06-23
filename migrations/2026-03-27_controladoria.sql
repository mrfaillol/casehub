-- Controladoria Juridica - Controle de Prazos Processuais
-- CaseHub Lite module for Escritorio Demo
-- 2026-03-27

-- Tabela de prazos processuais
CREATE TABLE IF NOT EXISTS prazos_processuais (
    id SERIAL PRIMARY KEY,
    case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE,
    org_id INTEGER REFERENCES organizations(id),
    tipo VARCHAR(100) NOT NULL,  -- contestacao, recurso, embargos, etc.
    data_intimacao DATE NOT NULL,
    data_inicio DATE NOT NULL,  -- dia util seguinte
    data_vencimento DATE NOT NULL,  -- calculado automaticamente
    dias_prazo INTEGER NOT NULL DEFAULT 15,
    responsavel VARCHAR(255),
    status VARCHAR(50) DEFAULT 'pendente',  -- pendente, em_andamento, concluido, perdido
    descricao TEXT,
    uf VARCHAR(2) DEFAULT 'MG',
    dobro BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prazos_org ON prazos_processuais(org_id);
CREATE INDEX IF NOT EXISTS idx_prazos_case ON prazos_processuais(case_id);
CREATE INDEX IF NOT EXISTS idx_prazos_vencimento ON prazos_processuais(data_vencimento);
CREATE INDEX IF NOT EXISTS idx_prazos_status ON prazos_processuais(status);

-- Campo resultado no cases
ALTER TABLE cases ADD COLUMN IF NOT EXISTS resultado VARCHAR(20) DEFAULT 'em_andamento';
ALTER TABLE cases ADD COLUMN IF NOT EXISTS setor VARCHAR(50);
