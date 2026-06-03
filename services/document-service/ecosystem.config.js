const docServiceDir = process.env.DOC_SERVICE_DIR || '/opt/casehub/document-service';

module.exports = {
  apps: [{
    name: 'document-watcher',
    script: 'document_watcher.py',
    interpreter: docServiceDir + '/venv/bin/python3',
    cwd: docServiceDir,
    env: {
      DB_HOST: process.env.DB_HOST || 'localhost',
      DB_NAME: process.env.PG_DATABASE || 'casehub',
      DB_USER: process.env.PG_USER || 'casehub',
      DB_PASSWORD: process.env.PG_PASSWORD || '',
      OLLAMA_URL: process.env.OLLAMA_URL || 'http://localhost:11434/api/generate',
      OLLAMA_MODEL: process.env.OLLAMA_MODEL || 'llama3.2:3b'
    },
    watch: false,
    max_restarts: 10,
    restart_delay: 5000
  }]
};
