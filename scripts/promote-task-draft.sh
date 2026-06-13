#!/bin/bash
# promote-task-draft.sh - Promote a reviewed task draft into the consumable queue.
#
# Ruling: 2026-05-07-task-draft-autopilot.
#
# This script is deterministic: no LLM calls, no network calls, no secret output.
# It validates a YAML draft staged in tasks/queue/_drafts/, converts it to
# tasks/queue/<id>.yaml, signs it with CASEHUB_OPS_HMAC_KEY, and removes the
# draft file so supervisors consume only the promoted queue entry.

set -euo pipefail

usage() {
    echo "usage: $0 tasks/queue/_drafts/<draft>.yaml" >&2
}

DRAFT="${1:-}"
[ -n "$DRAFT" ] || { usage; exit 2; }
[ -f "$DRAFT" ] || { echo "ERROR: draft does not exist: $DRAFT" >&2; exit 2; }

case "$DRAFT" in
    tasks/queue/_drafts/*.yaml) ;;
    */tasks/queue/_drafts/*.yaml) ;;
    *) echo "ERROR: draft must be in tasks/queue/_drafts/*.yaml" >&2; exit 2 ;;
esac

WORKSPACE="${WORKSPACE_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
cd "$WORKSPACE"

if [ -z "${CASEHUB_OPS_HMAC_KEY:-}" ]; then
    KEY_FILE="${CASEHUB_SECRETS_DIR:-$HOME/.config/casehub/secrets}/hmac-key"
    if [ -f "$KEY_FILE" ]; then
        CASEHUB_OPS_HMAC_KEY="$(cat "$KEY_FILE")"
    else
        echo "ERROR: CASEHUB_OPS_HMAC_KEY is unset and $KEY_FILE does not exist" >&2
        exit 3
    fi
fi

fail() { echo "REJECT: $1" >&2; exit 1; }

yaml_get() {
    (grep "^$1:" "$DRAFT" || true) | head -1 | sed "s/^$1:[[:space:]]*//" | sed 's/^"//; s/"$//'
}

yaml_get_list() {
    awk -v key="$1:" '
        $0 == key || $0 ~ "^"key"$" {in_list=1; next}
        in_list && /^- / {print substr($0, 3); next}
        in_list && /^  - / {print substr($0, 5); next}
        in_list && /^[^ ]/ {in_list=0}
    ' "$DRAFT" | sed 's/^"//; s/"$//'
}

contains_placeholder() {
    local value="$1"
    [ -z "$value" ] && return 0
    echo "$value" | grep -qiE '(TO_BE_FILLED|PENDING|TBD|TODO|_a preencher_|^null$)'
}

ID="$(yaml_get id)"
TASK_TYPE="$(yaml_get task_type)"
REPO="$(yaml_get repo)"
SPEC_PATH="$(yaml_get spec_path)"
RULING_REF="$(yaml_get ruling_ref)"
NEW_BRANCH="$(yaml_get new_branch)"
LEDGER_SHA="$(yaml_get ledger_commit_sha)"

[ -n "$ID" ] || fail "missing id"
echo "$ID" | grep -qE '^[a-zA-Z0-9][a-zA-Z0-9_-]{2,120}$' || fail "invalid id: $ID"
[ -n "$TASK_TYPE" ] || fail "missing task_type"
case "$TASK_TYPE" in
    engineering|ops-readonly|template-refactor) ;;
    *) fail "invalid task_type: $TASK_TYPE" ;;
esac

[ -n "$RULING_REF" ] || fail "ruling_ref is required"
contains_placeholder "$RULING_REF" && fail "ruling_ref placeholder"

if contains_placeholder "$LEDGER_SHA"; then
    LEDGER_SHA="$(git rev-parse HEAD)"
fi
echo "$LEDGER_SHA" | grep -qE '^[0-9a-f]{40}$' || fail "invalid ledger_commit_sha: $LEDGER_SHA"

if LC_ALL=C grep -E -i -q '(AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|AIzaSy[A-Za-z0-9_-]{33})' "$DRAFT"; then
    fail "draft contains a secret-like pattern"
fi
if LC_ALL=C grep -E -i -q '(ignore previous instructions|<\|im_start\||system:|assistant:)' "$DRAFT"; then
    fail "draft contains a prompt-injection pattern"
fi
if grep -v '^ledger_commit_sha:' "$DRAFT" | grep -v '^hmac_signature:' | LC_ALL=C grep -E -i -q '(TO_BE_FILLED|PENDING_SIGN|TBD|TODO|_a preencher_)'; then
    fail "draft still contains a placeholder"
fi

check_path_list_safe() {
    local list_name="$1"
    local values
    values="$(yaml_get_list "$list_name")"
    [ -z "$values" ] && return 0
    while IFS= read -r path; do
        [ -z "$path" ] && continue
        case "$path" in
            .env|.env.*|*/.env|*/.env.*|credentials/*|*/credentials/*|secrets/*|*/secrets/*|*.pem|*.key|*.p12|*.pfx|*.crt|.github/workflows/*|*/.github/workflows/*|*id_rsa*|*id_ed25519*|*authorized_keys*|*.ssh/*|*/.ssh/*)
                fail "$list_name contains forbidden path: $path"
                ;;
        esac
    done <<< "$values"
}

check_path_list_safe allowed_paths

case "$TASK_TYPE" in
    engineering)
        [ -n "$REPO" ] || fail "missing repo"
        case "$REPO" in casehub|casehub-whitelabel|trabalho-workspace) ;; *) fail "repo is not allowlisted: $REPO" ;; esac
        [ -n "$SPEC_PATH" ] || fail "missing spec_path"
        case "$SPEC_PATH" in docs/handoff/tasks/*.md) ;; *) fail "spec_path must be in docs/handoff/tasks/*.md" ;; esac
        [ -f "$SPEC_PATH" ] || fail "spec_path does not exist: $SPEC_PATH"
        if LC_ALL=C grep -E -i -q '(AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|AIzaSy[A-Za-z0-9_-]{33})' "$SPEC_PATH"; then
            fail "spec_path contains a secret-like pattern"
        fi
        if LC_ALL=C grep -E -i -q '(ignore previous instructions|<\|im_start\||system:|assistant:)' "$SPEC_PATH"; then
            fail "spec_path contains a prompt-injection pattern"
        fi
        OPS="$(yaml_get_list allowed_operations)"
        [ -n "$OPS" ] || fail "missing allowed_operations"
        only_github_ops=1
        while IFS= read -r op; do
            [ -z "$op" ] && continue
            case "$op" in
                issue-create|pr-create) ;;
                commit|push) only_github_ops=0 ;;
                *) fail "invalid allowed_operation: $op" ;;
            esac
        done <<< "$OPS"
        PATHS="$(yaml_get_list allowed_paths)"
        if [ "$only_github_ops" -eq 0 ] && [ -z "$PATHS" ]; then
            fail "allowed_paths is empty with commit/push operations"
        fi
        if [ -n "$NEW_BRANCH" ]; then
            echo "$NEW_BRANCH" | grep -qE '^((chore|fix|docs)/[a-z0-9-]+|agent/(army-claude|codex-wing|gemini-wing)/[a-z0-9_-]+)$' || fail "invalid new_branch: $NEW_BRANCH"
        fi
        ;;
    ops-readonly)
        [ -n "$(yaml_get ssh_host)" ] || fail "missing ssh_host"
        ;;
    template-refactor)
        [ -n "$(yaml_get template_path)" ] || fail "missing template_path"
        [ -n "$SPEC_PATH" ] || fail "missing spec_path"
        ;;
esac

MAX_TURNS="$(grep 'max_turns' "$DRAFT" | head -1 | sed 's/.*max_turns:[[:space:]]*\([0-9]*\).*/\1/')"
MAX_COST="$(grep 'max_cost_usd' "$DRAFT" | head -1 | sed 's/.*max_cost_usd:[[:space:]]*\([0-9]*\).*/\1/')"
TIMEOUT_MIN="$(grep 'timeout_minutes' "$DRAFT" | head -1 | sed 's/.*timeout_minutes:[[:space:]]*\([0-9]*\).*/\1/')"
[ -n "$MAX_TURNS" ] || fail "missing budget.max_turns"
[ -n "$MAX_COST" ] || fail "missing budget.max_cost_usd"
[ -n "$TIMEOUT_MIN" ] || fail "missing budget.timeout_minutes"
[ "$MAX_TURNS" -le 30 ] || fail "max_turns=$MAX_TURNS > 30"
[ "$MAX_COST" -le 5 ] || fail "max_cost_usd=$MAX_COST > 5"
[ "$TIMEOUT_MIN" -le 60 ] || fail "timeout_minutes=$TIMEOUT_MIN > 60"

DEST="tasks/queue/${ID}.yaml"
[ ! -e "$DEST" ] || fail "destination already exists: $DEST"
TMP_PARENT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
mkdir -p "$TMP_PARENT"
TMP="$(mktemp "${TMP_PARENT%/}/promote-task.XXXXXX")"

awk -v ledger="$LEDGER_SHA" '
    BEGIN {status_done=0; ledger_done=0}
    /^hmac:/ {next}
    /^hmac_signature:/ {next}
    /^status:/ {print "status: queued"; status_done=1; next}
    /^ledger_commit_sha:/ {print "ledger_commit_sha: " ledger; ledger_done=1; next}
    {print}
    END {
        if (!status_done) print "status: queued"
        if (!ledger_done) print "ledger_commit_sha: " ledger
    }
' "$DRAFT" > "$TMP"

BODY="$(cat "$TMP")"
HMAC="$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$CASEHUB_OPS_HMAC_KEY" | awk '{print $NF}')"
{
    printf '%s\n' "$BODY"
    printf 'hmac: %s\n' "$HMAC"
} > "$DEST"
rm -f "$TMP"
rm -f "$DRAFT"

echo "promoted $DRAFT -> $DEST"
