#!/bin/bash
cd /var/www/legacy.example/client-intake
/var/www/legacy.example/client-intake/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8003
