-- financial_entries — lançamentos financeiros (receitas/despesas) do escritório.
-- Origem: "Planilha de Controle Geral" (abas Fina-R = receitas, Fina-D = despesas).
-- Org-scoped (multi-tenant). DADO SENSÍVEL (PF/PJ): a UI /reports/financeiro é
-- gestor-only (admin/superadmin) + org-scoped. Loader reprodutível:
--   scripts/import_financeiro_planilha.py <caminho.xlsm> <org_id>
-- Provenance: criada originalmente por import ad-hoc no alpha (org 4) em 2026-06-03;
-- esta migração versiona o schema vivo (sem commit, sem deploy).
CREATE TABLE IF NOT EXISTS financial_entries (
    id            SERIAL PRIMARY KEY,
    org_id        INTEGER NOT NULL,
    kind          VARCHAR(10) NOT NULL,            -- 'receita' | 'despesa'
    valor         NUMERIC(14,2),
    data_prevista DATE,
    data_efetiva  DATE,
    settled       BOOLEAN DEFAULT FALSE,           -- Recebido? / Pago?
    tipo          VARCHAR(120),                    -- Honorários / categoria de despesa
    descricao     TEXT,
    processo_ref  VARCHAR(160),
    cliente       VARCHAR(200),
    tipo_cliente  VARCHAR(10),                     -- 'PF' | 'PJ'
    parcela       VARCHAR(20),                     -- 'X de Y'
    source        VARCHAR(20) DEFAULT 'planilha',
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_fin_org_kind_dt ON financial_entries (org_id, kind, data_prevista);
