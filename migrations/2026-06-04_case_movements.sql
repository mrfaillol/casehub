-- Proc-M: movimentações/andamentos manuais de processo (04/06)
-- Registro MANUAL de andamentos de um caso (sem integração DataJud — essa exige
-- API key e está fora de escopo). Tabela ADITIVA e ORG-SCOPED: nunca é JOINada
-- automaticamente em queries de Case (sem ORM relationship), então não dispara
-- o "lazy _ensure 500" / UndefinedColumn em páginas que carregam casos.
--
-- Espelha o CREATE TABLE IF NOT EXISTS do startup runner em
-- core/app_factory.py::_run_pending_migrations() (fonte auto-aplicada).
--
-- Invariantes de segurança:
--   org_id NOT NULL — toda linha pertence a um tenant.
--   case_id referencia cases(id); a rota valida via tenant_query que o caso
--     pertence ao request.state.org_id ANTES de inserir.
--   created_by = id do usuário autenticado (server-side, nunca do form).

CREATE TABLE IF NOT EXISTS case_movements (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    data DATE NOT NULL DEFAULT CURRENT_DATE,
    tipo VARCHAR(50) NOT NULL DEFAULT 'Andamento',
    descricao TEXT NOT NULL,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);

-- Listagem cronológica por caso, escopada por org (most-recent-first).
CREATE INDEX IF NOT EXISTS ix_case_movements_org_case_data
    ON case_movements (org_id, case_id, data DESC, id DESC);
