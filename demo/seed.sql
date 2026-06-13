-- CaseHub Demo Seed Data
-- Run: psql -U casehub -d casehub_demo -f seed.sql
-- Resets and populates demo database with fictitious data.
-- Scheduled daily via cron at 3:00 AM.

-- ============================================================
-- CLEANUP (idempotent)
-- ============================================================
DELETE FROM tasks WHERE org_id IN (100, 101);
DELETE FROM cases WHERE org_id IN (100, 101);
DELETE FROM clients WHERE org_id IN (100, 101);
DELETE FROM users WHERE org_id IN (100, 101);
DELETE FROM organizations WHERE id IN (100, 101);

-- ============================================================
-- ORGANIZATIONS
-- ============================================================
INSERT INTO organizations (id, uuid, name, slug, domain, primary_color, secondary_color, email, timezone, locale, currency, case_prefix, plan, max_users, max_clients, is_active)
VALUES
    (100, 'demo-br-00000-00000', 'Escritório Modelo', 'escritorio-modelo', NULL, '#1a6b7a', '#23808c', 'demo@casehub.vingren.me', 'America/Sao_Paulo', 'pt-BR', 'BRL', 'EM', 'enterprise', 50, 9999, true),
    (101, 'demo-us-00000-00000', 'Demo Immigration Firm', 'demo-immigration', NULL, '#1a56db', '#7c3aed', 'demo-us@casehub.vingren.me', 'America/New_York', 'en', 'USD', 'DIF', 'enterprise', 50, 9999, true)
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- USERS (password: demo2026)
-- bcrypt hash: $2b$12$AVSmp475TTneKrwzKJ5GV.vyPK5IX3Pa3or1awER03iLoBkTsTsjq
-- ============================================================
INSERT INTO users (org_id, email, name, password_hash, user_type, enabled, must_change_password, oab_number)
VALUES
    -- BR org (100)
    (100, 'demo@casehub.vingren.me', 'Demo Admin', '$2b$12$AVSmp475TTneKrwzKJ5GV.vyPK5IX3Pa3or1awER03iLoBkTsTsjq', 'admin', true, false, NULL),
    (100, 'advogado@demo.casehub', 'Dr. Carlos Silva', '$2b$12$AVSmp475TTneKrwzKJ5GV.vyPK5IX3Pa3or1awER03iLoBkTsTsjq', 'attorney', true, false, 'MG 654.321'),
    (100, 'estagiario@demo.casehub', 'Ana Santos', '$2b$12$AVSmp475TTneKrwzKJ5GV.vyPK5IX3Pa3or1awER03iLoBkTsTsjq', 'paralegal', true, false, NULL),
    (100, 'advogado2@demo.casehub', 'Dra. Fernanda Costa', '$2b$12$AVSmp475TTneKrwzKJ5GV.vyPK5IX3Pa3or1awER03iLoBkTsTsjq', 'attorney', true, false, 'MG 789.012'),
    -- Immigration org (101)
    (101, 'demo-us@casehub.vingren.me', 'Demo Admin', '$2b$12$AVSmp475TTneKrwzKJ5GV.vyPK5IX3Pa3or1awER03iLoBkTsTsjq', 'admin', true, false, NULL),
    (101, 'attorney@demo.casehub', 'Sarah Johnson', '$2b$12$AVSmp475TTneKrwzKJ5GV.vyPK5IX3Pa3or1awER03iLoBkTsTsjq', 'attorney', true, false, NULL),
    (101, 'paralegal@demo.casehub', 'Maria Garcia', '$2b$12$AVSmp475TTneKrwzKJ5GV.vyPK5IX3Pa3or1awER03iLoBkTsTsjq', 'paralegal', true, false, NULL)
ON CONFLICT (email) DO UPDATE SET
    password_hash = EXCLUDED.password_hash,
    enabled = true,
    must_change_password = false;

-- ============================================================
-- CLIENTS (BR — org 100)
-- ============================================================
INSERT INTO clients (org_id, name, email, phone, created_at)
VALUES
    (100, 'Felício Máquinas Ltda', 'contato@feliciomaquinas.com.br', '(32) 3211-4567', NOW() - INTERVAL '45 days'),
    (100, 'Maria de Souza', 'maria.souza@email.com', '(32) 99876-5432', NOW() - INTERVAL '30 days'),
    (100, 'JP Transportes S.A.', 'juridico@jptransportes.com.br', '(32) 3222-8900', NOW() - INTERVAL '60 days'),
    (100, 'Clínicas Passos ME', 'admin@clinicaspassos.com.br', '(32) 3244-5678', NOW() - INTERVAL '20 days'),
    (100, 'Carlos Alberto Mendes', 'carlos.mendes@email.com', '(32) 99765-4321', NOW() - INTERVAL '15 days'),
    (100, 'Construtora Horizonte Ltda', 'juridico@horizonte.eng.br', '(32) 3255-1234', NOW() - INTERVAL '90 days'),
    (100, 'Ana Paula Ferreira', 'ana.ferreira@email.com', '(32) 99654-3210', NOW() - INTERVAL '10 days'),
    (100, 'Roberto Silva Santos', 'roberto.santos@email.com', '(32) 99543-2109', NOW() - INTERVAL '5 days'),
    (100, 'Metalúrgica Central ME', 'contato@metalcentral.com.br', '(32) 3266-7890', NOW() - INTERVAL '75 days'),
    (100, 'Luciana Oliveira Costa', 'luciana.costa@email.com', '(32) 99432-1098', NOW() - INTERVAL '25 days')
ON CONFLICT DO NOTHING;

-- CLIENTS (Immigration — org 101)
INSERT INTO clients (org_id, name, email, phone, created_at)
VALUES
    (101, 'John Doe', 'john.doe@email.com', '+1 (555) 123-4567', NOW() - INTERVAL '30 days'),
    (101, 'Maria Silva', 'maria.silva@email.com', '+1 (555) 234-5678', NOW() - INTERVAL '45 days'),
    (101, 'Ahmed Hassan', 'ahmed.h@email.com', '+1 (555) 345-6789', NOW() - INTERVAL '20 days'),
    (101, 'Priya Patel', 'priya.patel@email.com', '+1 (555) 456-7890', NOW() - INTERVAL '60 days'),
    (101, 'Wei Chen', 'wei.chen@email.com', '+1 (555) 567-8901', NOW() - INTERVAL '15 days')
ON CONFLICT DO NOTHING;

-- ============================================================
-- CASES (BR — org 100)
-- ============================================================
INSERT INTO cases (org_id, title, status, created_at, numero_processo, tipo_acao, vara, comarca, tribunal, fase_processual)
VALUES
    (100, 'Felício Máquinas vs Estado de MG — Tributário', 'active', NOW() - INTERVAL '40 days', '0001234-56.2024.8.13.0145', 'Mandado de Segurança', '1ª Vara da Fazenda Pública', 'Juiz de Fora', 'TJMG', 'Instrução'),
    (100, 'Maria de Souza — Trabalhista', 'active', NOW() - INTERVAL '25 days', '0007890-12.2025.5.03.0037', 'Reclamação Trabalhista', '2ª Vara do Trabalho', 'Juiz de Fora', 'TRT3', 'Audiência designada'),
    (100, 'JP Transportes — Recurso TRF1', 'active', NOW() - INTERVAL '55 days', '0005678-34.2024.4.01.3801', 'Apelação', '3ª Turma', 'Brasília', 'TRF1', 'Recurso'),
    (100, 'Clínicas Passos — Previdenciário', 'active', NOW() - INTERVAL '18 days', '0003456-78.2025.8.13.0145', 'Ação Previdenciária', '1ª Vara Federal', 'Juiz de Fora', 'TJMG', 'Petição inicial'),
    (100, 'Carlos Mendes — BPC/LOAS', 'active', NOW() - INTERVAL '12 days', '0009012-45.2025.5.03.0037', 'BPC/LOAS', '2ª Vara Federal', 'Juiz de Fora', 'TRF1', 'Perícia'),
    (100, 'Construtora Horizonte — Cível', 'active', NOW() - INTERVAL '80 days', '0004567-89.2024.8.13.0145', 'Ação de Cobrança', '3ª Vara Cível', 'Juiz de Fora', 'TJMG', 'Sentença'),
    (100, 'Ana Paula — Divórcio', 'active', NOW() - INTERVAL '8 days', '0006789-01.2025.8.13.0145', 'Divórcio Consensual', '1ª Vara de Família', 'Juiz de Fora', 'TJMG', 'Homologação'),
    (100, 'Roberto Santos — Criminal', 'active', NOW() - INTERVAL '3 days', '0008901-23.2025.8.13.0145', 'Habeas Corpus', '1ª Vara Criminal', 'Juiz de Fora', 'TJMG', 'Liminar'),
    (100, 'Metalúrgica Central — Trabalhista', 'closed', NOW() - INTERVAL '70 days', '0002345-67.2024.5.03.0037', 'Reclamação Trabalhista', '1ª Vara do Trabalho', 'Juiz de Fora', 'TRT3', 'Transitado em julgado'),
    (100, 'Luciana Costa — Previdenciário', 'active', NOW() - INTERVAL '22 days', '0005432-10.2025.4.01.3801', 'Aposentadoria por Tempo', '1ª Vara Federal', 'Juiz de Fora', 'TRF1', 'Instrução')
ON CONFLICT DO NOTHING;

-- CASES (Immigration — org 101)
INSERT INTO cases (org_id, title, status, created_at, visa_type)
VALUES
    (101, 'EB-2 NIW — John Doe', 'active', NOW() - INTERVAL '25 days', 'EB-2 NIW'),
    (101, 'I-130 Family — Maria Silva', 'active', NOW() - INTERVAL '40 days', 'I-130'),
    (101, 'O-1 Extraordinary — Ahmed Hassan', 'active', NOW() - INTERVAL '15 days', 'O-1'),
    (101, 'H-1B Specialty — Priya Patel', 'rfe', NOW() - INTERVAL '50 days', 'H-1B'),
    (101, 'EB-1A — Wei Chen', 'active', NOW() - INTERVAL '10 days', 'EB-1A')
ON CONFLICT DO NOTHING;

-- ============================================================
-- TASKS (BR — org 100, distributed across kanban columns)
-- ============================================================
INSERT INTO tasks (org_id, title, status, created_at, due_date)
VALUES
    -- Novos (pending)
    (100, 'Petição Inicial — Souza', 'pending', NOW() - INTERVAL '2 days', NOW() + INTERVAL '5 days'),
    (100, 'Recurso Ordinário — MRV', 'pending', NOW() - INTERVAL '1 day', NOW() + INTERVAL '10 days'),
    (100, 'Revisão BPC — Almeida', 'pending', NOW(), NOW() + INTERVAL '15 days'),
    -- Em Andamento (in_progress)
    (100, 'Impugnação RPV — JP Transp.', 'in_progress', NOW() - INTERVAL '5 days', NOW() + INTERVAL '3 days'),
    (100, 'Laudo Pericial — Felício', 'in_progress', NOW() - INTERVAL '3 days', NOW() + INTERVAL '7 days'),
    (100, 'Contestação — Horizonte', 'in_progress', NOW() - INTERVAL '4 days', NOW() + INTERVAL '2 days'),
    -- Aguardando (blocked)
    (100, 'Docs Cliente — Passos', 'blocked', NOW() - INTERVAL '7 days', NOW() + INTERVAL '1 day'),
    (100, 'Perícia Médica — Costa', 'blocked', NOW() - INTERVAL '10 days', NOW() + INTERVAL '8 days'),
    -- Concluído (completed)
    (100, 'Contestação — Oliveira', 'completed', NOW() - INTERVAL '15 days', NOW() - INTERVAL '5 days'),
    (100, 'Acordo Trabalhista — Lima', 'completed', NOW() - INTERVAL '20 days', NOW() - INTERVAL '10 days'),
    (100, 'Recurso Especial — Mendes', 'completed', NOW() - INTERVAL '12 days', NOW() - INTERVAL '2 days'),
    (100, 'Audiência Preparação — Ferreira', 'completed', NOW() - INTERVAL '8 days', NOW() - INTERVAL '1 day')
ON CONFLICT DO NOTHING;

-- ============================================================
-- NOTE: Prazos, appointments, and productivity records are
-- created by the app on first access via controladoria routes.
-- The seed focuses on core tables that the app reads on login.
-- Additional tables (prazos_processuais, appointments, etc.)
-- are populated by the app's startup migrations.
-- ============================================================
