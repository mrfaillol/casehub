"""
VPS Monitor Configuration
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Database (same as CaseHub)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://casehub:casehub@localhost:5432/casehub")

# Services to monitor
SERVICES = {
    "casehub": {
        "name": "CaseHub",
        "port": 8001,
        "health_url": "http://127.0.0.1:8001/login",
        "pm2_name": "casehub"
    },
    "ilc-tools": {
        "name": "CaseHub Tools",
        "port": 8000,
        "health_url": "http://127.0.0.1:8000/",
        "pm2_name": "ilc-tools"
    },
    "whatsapp-bot": {
        "name": "WhatsApp Bot",
        "port": None,
        "health_url": None,
        "pm2_name": "whatsapp-bot"
    },
    "orchestra": {
        "name": "Orchestra",
        "port": 8002,
        "health_url": "http://127.0.0.1:8002/health",
        "pm2_name": "orchestra"
    },
    "intake": {
        "name": "Intake Portal",
        "port": None,  # Servido pelo CaseHub na rota /intake
        "health_url": "http://127.0.0.1:8001/intake",
        "pm2_name": None,  # Não tem processo PM2 próprio - usa casehub
        "parent_service": "casehub"
    }
}

# Update intervals (seconds)
SYSTEM_UPDATE_INTERVAL = 5
PM2_UPDATE_INTERVAL = 10
SERVICES_UPDATE_INTERVAL = 15
APPS_UPDATE_INTERVAL = 30

# History retention (data points)
HISTORY_MAX_POINTS = 720  # 2 hours at 5s intervals
