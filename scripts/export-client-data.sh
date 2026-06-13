#!/bin/bash
# Export client database dump from CaseHub VPS
# Usage: ./scripts/export-client-data.sh <client-name> [ssh-key-path] [vps-ip]
#
# Example: ./scripts/export-client-data.sh vieira-salles
#
# This creates a timestamped SQL dump in data-exports/<client>/

set -euo pipefail

CLIENT="${1:?Usage: $0 <client-name> [ssh-key-path] [vps-ip]}"
SSH_KEY="${2:-credentials/ssh-key-2026-03-31.key}"
VPS_IP="${3:-168.75.79.237}"
DATE=$(date +%Y-%m-%d)
DUMP_DIR="data-exports/$CLIENT"

mkdir -p "$DUMP_DIR"

echo "Exporting database for client: $CLIENT"
echo "VPS: $VPS_IP | Date: $DATE"

# Run pg_dump inside container
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "ubuntu@$VPS_IP" "
  docker exec casehub-db pg_dump -U casehub -d casehub \
    --no-owner --no-privileges \
    -f /tmp/dump-${DATE}.sql
  echo 'Dump size:'
  docker exec casehub-db ls -lh /tmp/dump-${DATE}.sql
"

# Download dump
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
  "ubuntu@$VPS_IP:/tmp/dump-${DATE}.sql" \
  "$DUMP_DIR/dump-${DATE}.sql"

echo "Exported to $DUMP_DIR/dump-${DATE}.sql"
ls -lh "$DUMP_DIR/dump-${DATE}.sql"
