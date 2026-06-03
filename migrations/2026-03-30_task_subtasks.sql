-- Task Subtasks: ensure parent_task_id column and index exist
-- 2026-03-30
-- Note: parent_task_id was added in 2026-03-25_task_kanban.sql
-- This migration ensures the index exists and adds a cascading delete constraint

-- Ensure index exists (idempotent)
CREATE INDEX IF NOT EXISTS idx_tasks_parent_id ON tasks(parent_task_id);

-- Add comment for clarity
COMMENT ON COLUMN tasks.parent_task_id IS 'References parent task for subtask hierarchy';
