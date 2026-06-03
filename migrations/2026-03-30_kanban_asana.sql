ALTER TABLE tasks ADD COLUMN IF NOT EXISTS tags VARCHAR;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS estimated_hours FLOAT;

CREATE TABLE IF NOT EXISTS task_comments (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id),
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_task_comments_task ON task_comments(task_id);
