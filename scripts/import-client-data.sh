#!/bin/bash
# Import client database dump into CaseHub VPS
# Usage: ./scripts/import-client-data.sh <dump-file> [ssh-key-path] [vps-ip]
#
# Example: ./scripts/import-client-data.sh data-exports/vieira-salles/dump-2026-04-02.sql

set -euo pipefail

DUMP_FILE="${1:?Usage: $0 <dump-file> [ssh-key-path] [vps-ip]}"
SSH_KEY="${2:-credentials/ssh-key-2026-03-31.key}"
VPS_IP="${3:-168.75.79.237}"

if [ ! -f "$DUMP_FILE" ]; then
  echo "Error: Dump file not found: $DUMP_FILE"
  exit 1
fi

echo "Importing: $DUMP_FILE"
echo "VPS: $VPS_IP"
echo ""
echo "WARNING: This will overwrite the current database!"
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Aborted."
  exit 0
fi

# Upload dump to VPS
BASENAME=$(basename "$DUMP_FILE")
scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
  "$DUMP_FILE" "ubuntu@$VPS_IP:/tmp/$BASENAME"

# Import into database
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "ubuntu@$VPS_IP" "
  docker cp /tmp/$BASENAME casehub-db:/tmp/$BASENAME
  docker exec casehub-db psql -U casehub -d casehub -f /tmp/$BASENAME
  echo 'Import complete.'
"

echo "Done. Database restored from $DUMP_FILE"
