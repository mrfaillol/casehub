#!/bin/bash
APP_DIR="${APP_BASE_PATH:-/opt/casehub}/ilc-tools"
cd "$APP_DIR"
source venv/bin/activate
exec uvicorn app:app --host 0.0.0.0 --port "${ILC_TOOLS_PORT:-8000}"
