-- AI Knowledge Sources (documents fed to the assistant)
CREATE TABLE IF NOT EXISTS ai_knowledge_sources (
    id SERIAL PRIMARY KEY,
    org_id INTEGER REFERENCES organizations(id),
    name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) DEFAULT 'manual',
    content TEXT,
    file_path VARCHAR(500),
    file_size INTEGER DEFAULT 0,
    chunks_count INTEGER DEFAULT 0,
    indexed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_sources_org ON ai_knowledge_sources(org_id);

-- AI Chat History
CREATE TABLE IF NOT EXISTS ai_chat_history (
    id SERIAL PRIMARY KEY,
    org_id INTEGER REFERENCES organizations(id),
    user_id INTEGER,
    message TEXT NOT NULL,
    response TEXT,
    tokens_used INTEGER DEFAULT 0,
    model VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_history_org ON ai_chat_history(org_id);
CREATE INDEX IF NOT EXISTS idx_ai_history_created ON ai_chat_history(created_at);
