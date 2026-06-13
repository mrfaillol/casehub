#!/bin/bash
# CaseHub Database Backup
# Run daily via cron: 0 3 * * * /home/ubuntu/casehub/scripts/backup_db.sh

BACKUP_DIR="/home/ubuntu/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="casehub"
DB_USER="casehub"
KEEP_DAYS=30

mkdir -p $BACKUP_DIR

# Dump inside Docker container
docker compose exec -T postgres pg_dump -U $DB_USER $DB_NAME | gzip > "$BACKUP_DIR/casehub_$DATE.sql.gz"

# Check if backup was created
if [ -f "$BACKUP_DIR/casehub_$DATE.sql.gz" ] && [ -s "$BACKUP_DIR/casehub_$DATE.sql.gz" ]; then
    echo "[$(date)] Backup OK: casehub_$DATE.sql.gz ($(du -h "$BACKUP_DIR/casehub_$DATE.sql.gz" | cut -f1))"
else
    echo "[$(date)] BACKUP FAILED!" >&2
    exit 1
fi

# Remove backups older than KEEP_DAYS
find $BACKUP_DIR -name "casehub_*.sql.gz" -mtime +$KEEP_DAYS -delete
echo "[$(date)] Cleaned backups older than $KEEP_DAYS days"
