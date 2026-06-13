#!/bin/bash
# CaseHub - Deploy Script
# Usage: ./scripts/deploy.sh [user@host] [ssh-key]
# Example: ./scripts/deploy.sh ubuntu@137.131.237.130 ~/.oci/casehub_ssh_key
#
# Durante HALT ativo, este rsync so roda para escopo permitido:
#   CASEHUB_DEPLOY_SCOPE=performance-p0 ./scripts/deploy.sh ...
#   CASEHUB_DEPLOY_SCOPE=docs-only ./scripts/deploy.sh ...
# ou com override auditavel:
#   CASEHUB_DEPLOY_HALT_OVERRIDE_ISSUE=<casehub issue> \
#   CASEHUB_DEPLOY_HALT_OVERRIDE_REASON=<motivo> ./scripts/deploy.sh ...

set -e

HOST="${1:-ubuntu@137.131.237.130}"
SSH_KEY="${2:-~/.oci/casehub_ssh_key}"
REMOTE_DIR="/home/ubuntu/casehub"
SSH="ssh -i $SSH_KEY $HOST"

echo "=== CaseHub Deploy ==="
echo "Host: $HOST"
echo "Remote: $REMOTE_DIR"
echo ""

HALT_FILE="docs/security/deploy-halt.json"
if [ -f "$HALT_FILE" ]; then
  halt_fields=()
  while IFS= read -r line; do
    halt_fields+=("$line")
  done < <(python3 - "$HALT_FILE" <<'PY'
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)
print("true" if data.get("active") is True else "false")
print(str(data.get("reason", "")).replace("\n", " "))
print(data.get("canonical_issue", ""))
PY
)
  HALT_ACTIVE="${halt_fields[0]:-false}"
  HALT_REASON="${halt_fields[1]:-}"
  HALT_ISSUE="${halt_fields[2]:-}"

  if [ "$HALT_ACTIVE" = "true" ]; then
    case "${CASEHUB_DEPLOY_SCOPE:-}" in
      performance-p0|docs-only)
        echo "HALT active; allowed scope: $CASEHUB_DEPLOY_SCOPE"
        ;;
      *)
        if [ -n "${CASEHUB_DEPLOY_HALT_OVERRIDE_ISSUE:-}" ] && [ -n "${CASEHUB_DEPLOY_HALT_OVERRIDE_REASON:-}" ]; then
          if [ "$CASEHUB_DEPLOY_HALT_OVERRIDE_ISSUE" != "$HALT_ISSUE" ]; then
            echo "ERROR: HALT override issue mismatch: got=$CASEHUB_DEPLOY_HALT_OVERRIDE_ISSUE expected=$HALT_ISSUE" >&2
            exit 3
          fi
          echo "HALT override registered: issue=$CASEHUB_DEPLOY_HALT_OVERRIDE_ISSUE reason=$CASEHUB_DEPLOY_HALT_OVERRIDE_REASON"
        else
          echo "ERROR: Deploy HALT active: $HALT_REASON ($HALT_ISSUE)" >&2
          echo "Set CASEHUB_DEPLOY_SCOPE=performance-p0|docs-only or provide CASEHUB_DEPLOY_HALT_OVERRIDE_ISSUE + CASEHUB_DEPLOY_HALT_OVERRIDE_REASON." >&2
          exit 3
        fi
        ;;
    esac
  fi
fi

# 1. Sync code
echo "[1/5] Syncing code..."
rsync -avz --progress \
  --exclude='venv/' --exclude='node_modules/' --exclude='__pycache__/' \
  --exclude='.env' --exclude='*.db' --exclude='uploads/' --exclude='storage/' \
  --exclude='logs/' --exclude='output/' --exclude='.git/' --exclude='test-results/' \
  --exclude='playwright/' --exclude='lovable-audit/' \
  -e "ssh -i $SSH_KEY" \
  . "$HOST:$REMOTE_DIR/" 2>&1 | tail -5

# 2. Apply migrations
echo ""
echo "[2/5] Applying migrations..."
$SSH "cd $REMOTE_DIR && for f in migrations/*.sql; do echo \"  Applying \$f...\"; sudo docker compose exec -T postgres psql -U casehub -d casehub -f /dev/stdin < \$f 2>/dev/null || true; done"

# 3. Rebuild containers
echo ""
echo "[3/5] Rebuilding containers..."
$SSH "cd $REMOTE_DIR && sudo docker compose --profile full build 2>&1 | tail -5"

# 4. Restart
echo ""
echo "[4/5] Restarting containers..."
$SSH "cd $REMOTE_DIR && sudo docker compose --profile full up -d 2>&1 | tail -8"

# 5. Health check
echo ""
echo "[5/5] Health checks (waiting 25s)..."
sleep 25
IMM=$($SSH "curl -s http://localhost:8001/api/health 2>/dev/null" || echo '{"status":"FAIL"}')
LITE=$($SSH "curl -s http://localhost:8002/api/health 2>/dev/null" || echo '{"status":"FAIL"}')

echo "Immigration: $IMM"
echo "Lite: $LITE"

# Verify
if echo "$IMM" | grep -q '"healthy"' && echo "$LITE" | grep -q '"healthy"'; then
  echo ""
  echo "=== DEPLOY SUCCESS ==="
  echo "Immigration: http://${HOST#*@}:8001/casehub/login"
  echo "Lite: http://${HOST#*@}:8002/casehub/login"
else
  echo ""
  echo "=== DEPLOY FAILED ==="
  echo "Check logs: $SSH 'sudo docker compose logs --tail 20'"
  exit 1
fi
