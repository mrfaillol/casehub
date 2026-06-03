module.exports = {
  apps: [{
    name: "client-intake",
    script: "/var/www/${process.env.ORG_WEBSITE || "casehub.app"}/client-intake/venv/bin/uvicorn",
    args: "app:app --host 127.0.0.1 --port 8003",
    cwd: "/var/www/${process.env.ORG_WEBSITE || "casehub.app"}/client-intake",
    interpreter: "none",
    kill_timeout: 5000,
    treekill: true,
    max_restarts: 10,
    min_uptime: 5000,
    restart_delay: 2000
  }]
};
