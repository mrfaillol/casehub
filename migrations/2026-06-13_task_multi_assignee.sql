CREATE TABLE IF NOT EXISTS task_assignees (
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_task_assignees_user
    ON task_assignees (user_id);
CREATE INDEX IF NOT EXISTS idx_task_assignees_task
    ON task_assignees (task_id);

-- Migrar responsáveis existentes (assignment singular -> junction)
INSERT INTO task_assignees (task_id, user_id)
SELECT id, assigned_to
FROM tasks
WHERE assigned_to IS NOT NULL
ON CONFLICT DO NOTHING;
