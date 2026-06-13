-- Agenda: Perícia support (aba Peric + Pe-Das1 da planilha VS, 03/06)
-- Replica audiencia: type='pericia' nos appointments + dois campos extras.
--   local          -> "Local" da perícia (físico/online)
--   pericia_status -> "Status" de acompanhamento (agendada, realizada, etc.)
-- Campos da planilha sem coluna nova mapeiam para o appointment existente:
--   Data -> date | Hora -> time_start | Processo -> case_id/client_name
--   Advogado Responsável -> assigned_to | Detalhes/Observações -> notes
--   "Dias até a Perícia" -> calculado (date - CURRENT_DATE), não persistido.
-- Additive e nullable: idempotente, espelha o _ensure lazy em core/app_factory.py.

ALTER TABLE appointments ADD COLUMN IF NOT EXISTS local VARCHAR(255);
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS pericia_status VARCHAR(50);
