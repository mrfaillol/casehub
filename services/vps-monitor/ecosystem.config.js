module.exports = {
  apps: [{
    name: 'vps-monitor',
    script: 'main.py',
    interpreter: 'python3',
    cwd: '/var/www/${process.env.ORG_WEBSITE || "casehub.app"}/vps-monitor',
    env: {
      NOTION_TOKEN: ''
    }
  }]
}
