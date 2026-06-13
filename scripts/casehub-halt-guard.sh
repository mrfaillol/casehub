#!/usr/bin/env bash
# Guard for PRs while docs/security/deploy-halt.json is active.

set -euo pipefail

HALT_FILE="${CASEHUB_HALT_FILE:-docs/security/deploy-halt.json}"
LABELS_CSV="${CASEHUB_PR_LABELS:-}"
BASE_REF="${CASEHUB_BASE_REF:-origin/main}"

has_label() {
    local needle="$1"
    case ",${LABELS_CSV}," in
        *",$needle,"*) return 0 ;;
        *) return 1 ;;
    esac
}

is_workflow_path() {
    case "$1" in
        .github/workflows/*.yml|.github/workflows/*.yaml) return 0 ;;
        *) return 1 ;;
    esac
}

is_deploy_path() {
    # Only paths that actually ship to production, or gate what ships, belong
    # here. Workflow changes stay gated by default so a newly named deploy
    # workflow cannot bypass an active HALT by using a reserved CI name.
    case "$1" in
        # Deploy workflows specifically (deploy-dev.yml, deploy-prod.yml).
        .github/workflows/deploy*.yml|.github/workflows/deploy*.yaml) return 0 ;;
        # Self-protect guard workflows with either GitHub Actions extension.
        .github/workflows/casehub-halt-guard.yml|.github/workflows/casehub-halt-guard.yaml) return 0 ;;
        .github/workflows/oracle-pr-scope-guard.yml|.github/workflows/oracle-pr-scope-guard.yaml) return 0 ;;
        # Unknown or newly introduced workflows are conservative: require an
        # explicit HALT label such as ci-only or halt-exception-approved.
        .github/workflows/*.yml|.github/workflows/*.yaml) return 0 ;;
        # Deploy docs/policy
        docs/protocols/casehub-gitops-deploy.md) return 0 ;;
        docs/security/deploy-halt.json) return 0 ;;
        docs/security/sha-blocklist.txt) return 0 ;;
        docs/templates/deploy-prod.yml.template) return 0 ;;
        scripts/casehub-halt-guard.sh) return 0 ;;
        scripts/deploy*.sh) return 0 ;;
        scripts/oracle_deploy.sh) return 0 ;;
        scripts/vps-bootstrap.sh) return 0 ;;
        scripts/vps-deploy.sh) return 0 ;;
        docker-compose*.yml) return 0 ;;
        Dockerfile*) return 0 ;;
        deploy/*) return 0 ;;
        nginx/*) return 0 ;;
        infra/*) return 0 ;;
        *) return 1 ;;
    esac
}

load_changed_files() {
    if [ -n "${CASEHUB_CHANGED_FILES_FILE:-}" ]; then
        cat "$CASEHUB_CHANGED_FILES_FILE"
        return
    fi

    if [ -n "${CASEHUB_CHANGED_FILES:-}" ]; then
        printf '%s\n' "$CASEHUB_CHANGED_FILES"
        return
    fi

    committed_changed="$(git diff --name-only "$BASE_REF"...HEAD)"
    if [ -n "$committed_changed" ]; then
        printf '%s\n' "$committed_changed"
        return
    fi

    git diff --name-only
}

if [ ! -f "$HALT_FILE" ]; then
    echo "HALT guard: $HALT_FILE not present; passing."
    exit 0
fi

halt_active="$(
    python3 - "$HALT_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)
print("true" if data.get("active") is True else "false")
PY
)"

if [ "$halt_active" != "true" ]; then
    echo "HALT guard: deploy halt inactive; passing."
    exit 0
fi

override_labels_csv="$(
    python3 - "$HALT_FILE" <<'PY'
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)
allowed = [str(s).strip() for s in (data.get("allowed_scope") or []) if str(s).strip()]
deploy_overrides = [s for s in allowed if s != "docs-only"]
if deploy_overrides:
    print(",".join(deploy_overrides))
PY
)"
[ -z "$override_labels_csv" ] && override_labels_csv="performance-p0,halt-exception-approved,ci-only"

has_override_label() {
    local label
    IFS=',' read -ra _labels <<< "$override_labels_csv"
    for label in "${_labels[@]}"; do
        [ -z "$label" ] && continue
        if has_label "$label"; then
            return 0
        fi
    done
    return 1
}

# Load scope_exclusions.paths globs from deploy-halt.json (newline-separated).
# Ruling 2026-05-05-perpetual-sessions-and-automerge C-12 carve-out.
exclusion_globs="$(
    python3 - "$HALT_FILE" <<'PY'
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = json.load(fh)
for p in (data.get("scope_exclusions", {}) or {}).get("paths", []) or []:
    print(p)
PY
)"

is_excluded_path() {
    local p="$1"
    local glob
    while IFS= read -r glob; do
        [ -z "$glob" ] && continue
        # shellcheck disable=SC2053
        case "$p" in
            $glob) return 0 ;;
        esac
    done <<< "$exclusion_globs"
    return 1
}

changed_files=()
while IFS= read -r path; do
    [ -n "$path" ] && changed_files+=("$path")
done < <(load_changed_files)

if [ "${#changed_files[@]}" -eq 0 ]; then
    echo "HALT guard: no changed files; passing."
    exit 0
fi

deploy_changes=()
excluded_changes=()
for path in "${changed_files[@]}"; do
    if is_workflow_path "$path" && is_deploy_path "$path"; then
        deploy_changes+=("$path")
        continue
    fi
    if is_excluded_path "$path"; then
        excluded_changes+=("$path")
        continue
    fi
    if is_deploy_path "$path"; then
        deploy_changes+=("$path")
    fi
done

if [ "${#excluded_changes[@]}" -gt 0 ]; then
    echo "HALT guard: scope_exclusions absorbed ${#excluded_changes[@]} path(s):"
    printf '  - %s\n' "${excluded_changes[@]}"
fi

if [ "${#deploy_changes[@]}" -eq 0 ]; then
    echo "HALT guard: docs-only or non-deploy change; passing under deploy freeze."
    exit 0
fi

# Manual override labels for deploy-classified paths. `docs-only` is handled by
# the no-deploy-changes branch above; it must never override a prod/deploy path.
if has_override_label; then
    echo "HALT guard: deploy/prod paths touched, but PR has an allowed HALT label."
    printf '  - %s\n' "${deploy_changes[@]}"
    exit 0
fi

echo "::error::CaseHub deploy HALT is active. Deploy/prod paths require one of: ${override_labels_csv}."
printf '  - %s\n' "${deploy_changes[@]}"
exit 1
