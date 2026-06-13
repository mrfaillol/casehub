-- CaseHub Complete Seed Data (correct column names)

-- Kanban columns
INSERT INTO kanban_columns (org_id, name, slug, position, color, is_done) VALUES
(1, 'A Fazer', 'a-fazer', 0, '#6b7280', false),
(1, 'Em Andamento', 'em-andamento', 1, '#3b82f6', false),
(1, 'Revisão', 'revisao', 2, '#f59e0b', false),
(1, 'Concluído', 'concluido', 3, '#22c55e', true);

UPDATE tasks SET column_id = 1 WHERE status = 'pending' AND org_id = 1;
UPDATE tasks SET column_id = 2 WHERE status = 'in_progress' AND org_id = 1;
UPDATE tasks SET column_id = 4 WHERE status = 'completed' AND org_id = 1;

-- Prazos processuais
INSERT INTO prazos_processuais (org_id, case_id, tipo, descricao, data_inicio, data_vencimento, status, responsavel) VALUES
(1, 1, 'Contestação', 'Contestação trabalhista - Maria Silva', '2026-04-01', '2026-04-20', 'pendente', 'Victor Vingren'),
(1, 2, 'Petição', 'Petição inicial cível - Pedro Santos', '2026-04-05', '2026-04-25', 'pendente', 'Victor Vingren'),
(1, 3, 'Impugnação', 'Impugnação fiscal - Construtora ABC', '2026-03-15', '2026-04-15', 'vencido', 'Victor Vingren'),
(1, 1, 'Audiência', 'Audiência conciliação - Maria Silva', '2026-04-10', '2026-04-30', 'pendente', 'Victor Vingren'),
(1, 2, 'Réplica', 'Réplica - Pedro Santos', '2026-04-08', '2026-05-08', 'pendente', 'Victor Vingren'),
(1, 3, 'Recurso', 'Recurso especial - Construtora ABC', '2026-03-20', '2026-04-10', 'cumprido', 'Victor Vingren'),
(1, 1, 'Juntada', 'Juntada de documentos - Maria Silva', '2026-04-12', '2026-05-02', 'pendente', 'Victor Vingren'),
(1, 2, 'Perícia', 'Laudo pericial - Pedro Santos', '2026-04-15', '2026-05-15', 'pendente', 'Victor Vingren'),
(1, 3, 'Embargos', 'Embargos declaração - Construtora ABC', '2026-04-01', '2026-04-11', 'cumprido', 'Victor Vingren'),
(1, 1, 'C.razões', 'Contrarrazões recurso - Maria Silva', '2026-04-20', '2026-05-20', 'pendente', 'Victor Vingren');

-- Appointments (agenda)
INSERT INTO appointments (org_id, title, type, assigned_to, client_name, case_id, date, time_start, time_end, notes) VALUES
(1, 'Reunião com Maria Silva', 'atendimento', 1, 'Maria Silva', 1, '2026-04-15', '10:00', '11:00', 'Alinhamento sobre audiência'),
(1, 'Perícia - Pedro Santos', 'audiencia', 1, 'Pedro Santos', 2, '2026-04-18', '14:00', '16:00', 'Acompanhar laudo pericial no Fórum JF'),
(1, 'Audiência fiscal - ABC', 'audiencia', 1, 'Construtora ABC', 3, '2026-04-22', '09:00', '10:30', 'Defesa execução fiscal - Vara da Fazenda');

-- Documents
INSERT INTO documents (org_id, client_id, case_id, name, doc_type, file_path, file_size, status, uploaded_by) VALUES
(1, 1, 1, 'Petição Inicial - Reclamação Trabalhista', 'petition', '/uploads/docs/pet_001.pdf', 245000, 'approved', 1),
(1, 1, 1, 'CTPS Maria Silva', 'identification', '/uploads/docs/ctps_001.pdf', 180000, 'approved', 1),
(1, 2, 2, 'Procuração Pedro Santos', 'power_of_attorney', '/uploads/docs/proc_002.pdf', 95000, 'pending_review', 1),
(1, 4, 3, 'Notificação Fiscal', 'government_notice', '/uploads/docs/notif_003.pdf', 320000, 'uploaded', 1),
(1, 3, NULL, 'RG Ana Oliveira', 'identification', '/uploads/docs/rg_003.pdf', 150000, 'approved', 1);

-- Notifications
INSERT INTO notifications (org_id, user_id, title, message, notification_type, read) VALUES
(1, 1, 'Prazo vencendo', 'Prazo de contestação vence em 2 dias', 'warning', false),
(1, 1, 'Novo documento', 'Procuração de Pedro Santos aguarda revisão', 'info', false),
(1, 1, 'Audiência amanhã', 'Reunião com Maria Silva às 10h', 'reminder', false),
(1, 1, 'Prazo cumprido', 'Recurso especial - Construtora ABC concluído', 'success', true),
(1, 1, 'ComunicaAPI', '3 novas intimações encontradas', 'info', false);
