#!/usr/bin/env python3
import os
import json
from datetime import datetime

try:
    with open(os.getenv('APP_BASE_PATH', '/opt/casehub') + '/ilc-tools/data/activity.json', 'r') as f:
        data = json.load(f)
    now = datetime.now()
    for email, info in data.items():
        last = datetime.fromisoformat(info.get('last_seen', now.isoformat()))
        ago = int((now - last).total_seconds())
        if 0 <= ago < 900:
            time_str = f'{ago}s' if ago < 60 else f'{ago//60}m'
            print(f"{email[:22]}|{info.get('page', '?')[:15]}|{time_str}")
except:
    pass
