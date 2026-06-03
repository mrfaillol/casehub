module.exports = {
  apps: [{
    name: 'sentinela',
    script: 'sentinela.py',
    interpreter: 'python3',
    cwd: '/var/www/${process.env.ORG_WEBSITE || "casehub.app"}/sentinela',
    max_memory_restart: '300M',
    env: {
      PYTHONUNBUFFERED: '1'
    }
  }]
}
