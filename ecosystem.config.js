const casehubDir = process.env.CASEHUB_DIR;
if (!casehubDir) throw new Error("CASEHUB_DIR environment variable is required (e.g. /opt/casehub/app)");

module.exports = {
  apps: [{
    name: "casehub",
    script: "venv/bin/uvicorn",
    args: "app:app --host 0.0.0.0 --port 8001 --workers 1",
    cwd: casehubDir,
    max_memory_restart: "2500M",
    env: {
      PATH: casehubDir + "/venv/bin:" + process.env.PATH
    }
  }]
};
