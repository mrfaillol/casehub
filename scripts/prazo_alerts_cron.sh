#!/bin/bash
# CaseHub — Prazo/Deadline Alert Cron Job
# Checks approaching deadlines and sends email notifications.
#
# Crontab entry (run daily at 7 AM Brasília = 10:00 UTC):
#   0 10 * * * /home/ubuntu/casehub/scripts/prazo_alerts_cron.sh >> /home/ubuntu/backups/prazo-alerts.log 2>&1

LOGFILE="/home/ubuntu/backups/prazo-alerts.log"
CASEHUB_DIR="/home/ubuntu/casehub"

echo "----------------------------------------------"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting prazo alert check..."

cd "$CASEHUB_DIR" || { echo "FATAL: cannot cd to $CASEHUB_DIR"; exit 1; }

docker compose exec -T casehub-lite python -c \
    "from services.prazo_alertas import check_and_alert_prazos; sent = check_and_alert_prazos(); print(f'Alerts sent: {sent}')"

EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Prazo alert check completed successfully."
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: prazo alert check failed (exit $EXIT_CODE)" >&2
fi
