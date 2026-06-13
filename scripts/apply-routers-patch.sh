#!/bin/bash
# scripts/apply-routers-patch.sh - Wire routes/improvement_tasks into core/app_factory.py
#
# Idempotent. Run once locally on each casehub host (Hosting Provider prod, Oracle dev).
#
# Authority: trabalho-workspace ruling 2026-05-06-cmd-control-center-activation
#
# Pre-requisites: routes/improvement_tasks.py, services/improvement_task_service.py,
# models/improvement_task.py, and the migration must already be in this repo.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_FACTORY="$REPO_ROOT/core/app_factory.py"
ROUTE_FILE="$REPO_ROOT/routes/improvement_tasks.py"
MODEL_FILE="$REPO_ROOT/models/improvement_task.py"
MIGRATION_FILE="$REPO_ROOT/migrations/2026-05-06_improvement_tasks.sql"

[ -f "$APP_FACTORY" ] || { echo "ERROR: $APP_FACTORY not found" >&2; exit 2; }
[ -f "$ROUTE_FILE" ] || { echo "ERROR: $ROUTE_FILE not found" >&2; exit 2; }
[ -f "$MODEL_FILE" ] || { echo "ERROR: $MODEL_FILE not found" >&2; exit 2; }
[ -f "$MIGRATION_FILE" ] || { echo "ERROR: $MIGRATION_FILE not found" >&2; exit 2; }

# Idempotency: bail if already wired
if grep -q '"improvement_tasks"' "$APP_FACTORY"; then
    echo "Already wired (improvement_tasks already in CORE_ROUTERS). Nothing to do."
    exit 0
fi

backup="$APP_FACTORY.pre-cmd-activation.$(date +%Y%m%d-%H%M%S).bak"
cp "$APP_FACTORY" "$backup"
echo "Backup saved: $backup"

python3 - "$APP_FACTORY" <<'PYEOF'
import sys, re, pathlib
p = pathlib.Path(sys.argv[1])
text = p.read_text()

# Locate the END of the CORE_ROUTERS list using regex tolerant of whitespace,
# trailing comma, and any router being last. Pattern: find `CORE_ROUTERS = [`,
# then locate its matching `]` (single-line or multi-line).
core_routers_open = re.search(r"CORE_ROUTERS\s*=\s*\[", text)
if not core_routers_open:
    print("ERROR: CORE_ROUTERS list opening not found", file=sys.stderr)
    sys.exit(1)

# Walk forward from the opening bracket counting nesting to find matching close.
start = core_routers_open.end()  # position right after `[`
depth = 1
i = start
while i < len(text) and depth > 0:
    c = text[i]
    if c == '[':
        depth += 1
    elif c == ']':
        depth -= 1
        if depth == 0:
            close_idx = i
            break
    i += 1
else:
    print("ERROR: matching close bracket for CORE_ROUTERS not found", file=sys.stderr)
    sys.exit(1)

# Find indentation of the line that contains the closing `]`
line_start = text.rfind('\n', 0, close_idx) + 1
indent = ""
for ch in text[line_start:close_idx]:
    if ch in ' \t':
        indent += ch
    else:
        break

# Build insertion: a comma after whatever the previous element was (if missing),
# then our entry, then close bracket on its own line.
insert = (
    f'{indent}    # Cmd-vingren control center receiver (ruling 2026-05-06-cmd-control-center-activation).\n'
    f'{indent}    "improvement_tasks",\n'
    f'{indent}'
)

# If the char immediately before close_idx (skipping whitespace) is not a comma,
# add one to keep the list trailing-comma-friendly.
j = close_idx - 1
while j > start and text[j] in ' \t\n':
    j -= 1
if text[j] != ',':
    insert = ',\n' + insert  # prepend comma if previous element lacked trailing comma

text = text[:close_idx] + insert + text[close_idx:]

# Final sanity: parse must succeed
import ast
try:
    ast.parse(text)
except SyntaxError as e:
    print(f"ERROR: AST validation failed after edit: {e}", file=sys.stderr)
    sys.exit(1)

p.write_text(text)
print(f"OK: added 'improvement_tasks' to CORE_ROUTERS in {p}")
PYEOF

# Validate Python syntax (belt-and-suspenders; the python script above already does ast.parse)
if python3 -c "import ast; ast.parse(open('$APP_FACTORY').read())" 2>/dev/null; then
    echo "OK: app_factory.py syntax check passed"
else
    echo "ERROR: app_factory.py syntax check FAILED. Restoring from backup." >&2
    mv "$backup" "$APP_FACTORY"
    exit 1
fi

# Apply SQL migration (production)
if command -v psql >/dev/null 2>&1 && [ -n "${DATABASE_URL:-}" ]; then
    echo "Applying SQL migration via psql..."
    psql "$DATABASE_URL" -f "$MIGRATION_FILE" || echo "WARN: migration apply failed (may already exist)"
else
    echo "INFO: psql or DATABASE_URL not available; skip migration apply (do it manually with: psql \$DATABASE_URL -f $MIGRATION_FILE)"
fi

echo ""
echo "Patch applied successfully."
echo "Next steps:"
echo "  1. Set CASEHUB_IMPROVEMENT_HMAC_KEY env var (32+ bytes hex)"
echo "     Example: export CASEHUB_IMPROVEMENT_HMAC_KEY=\$(openssl rand -hex 32)"
echo "  2. Restart the casehub service (PM2 / docker-compose / systemctl)"
echo "  3. Smoke test:"
echo "     curl -X POST https://sampletenant.casehub.legal/casehub/api/v1/improvement-tasks \\\\"
echo "          -H 'Content-Type: application/json' \\\\"
echo "          -H \"X-CMD-Ingest-Signature: \$(echo -n '{...}' | openssl dgst -sha256 -hmac \"\$CASEHUB_IMPROVEMENT_HMAC_KEY\" | awk '{print \$NF}')\" \\\\"
echo "          -d '{\"envelope_ref\":\"smoke-001\",\"kind\":\"ui-polish\",\"title\":\"smoke test\"}'"
