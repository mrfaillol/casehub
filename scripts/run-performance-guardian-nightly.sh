#!/usr/bin/env bash
set -euo pipefail

# Runs the full CaseHub Performance Guardian lane on Oracle dev when SSH
# configuration is available. Missing secrets are a clean no-op for PRs/forks.

: "${CASEHUB_PERF_BASE_URL:=https://dev.vingren.me}"
: "${CASEHUB_PERF_PROFILE:=readme-min-current}"
: "${CASEHUB_PERF_ISSUE:=359}"

missing=()
for name in ORACLE_HOST ORACLE_USER ORACLE_SSH_KEY ORACLE_KNOWN_HOSTS; do
  if [[ -z "${!name:-}" ]]; then
    missing+=("$name")
  fi
done

if (( ${#missing[@]} > 0 )); then
  printf 'SKIP: missing Oracle SSH env: %s\n' "${missing[*]}"
  exit 0
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
key="$tmpdir/oracle_key"
known_hosts="$tmpdir/known_hosts"
printf '%s\n' "$ORACLE_SSH_KEY" > "$key"
printf '%s\n' "$ORACLE_KNOWN_HOSTS" > "$known_hosts"
chmod 600 "$key"
chmod 644 "$known_hosts"

ssh_opts=(
  -i "$key"
  -o StrictHostKeyChecking=yes
  -o UserKnownHostsFile="$known_hosts"
)

remote_dir="${CASEHUB_PERF_REMOTE_DIR:-/home/ubuntu/casehub}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
remote_report="/tmp/casehub-performance-guardian-${stamp}.json"
remote_md="/tmp/casehub-performance-guardian-${stamp}.md"

ssh "${ssh_opts[@]}" "${ORACLE_USER}@${ORACLE_HOST}" \
  "cd '$remote_dir' && python3 scripts/perf_guardian.py seed --target dev --profile '$CASEHUB_PERF_PROFILE' --reset"

ssh "${ssh_opts[@]}" "${ORACLE_USER}@${ORACLE_HOST}" \
  "cd '$remote_dir' && python3 scripts/perf_guardian.py benchmark --base-url '$CASEHUB_PERF_BASE_URL' --environment oracle-dev --profile '$CASEHUB_PERF_PROFILE' --output '$remote_report' >/dev/null && python3 scripts/perf_guardian.py markdown '$remote_report' --output '$remote_md' >/dev/null"

scp "${ssh_opts[@]}" "${ORACLE_USER}@${ORACLE_HOST}:$remote_report" "$tmpdir/report.json"
scp "${ssh_opts[@]}" "${ORACLE_USER}@${ORACLE_HOST}:$remote_md" "$tmpdir/report.md"

cat "$tmpdir/report.md"

if command -v gh >/dev/null 2>&1 && [[ -n "${GITHUB_TOKEN:-}" ]]; then
  gh issue comment "$CASEHUB_PERF_ISSUE" \
    --repo mrfaillol/casehub-prod \
    --body-file "$tmpdir/report.md"
fi
