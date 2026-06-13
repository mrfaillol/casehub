#!/bin/bash
cd /var/www/immigrant.law/client-intake
/var/www/immigrant.law/client-intake/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8003
