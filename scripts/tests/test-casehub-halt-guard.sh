#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GUARD="$ROOT_DIR/scripts/casehub-halt-guard.sh"

run_guard() {
    (
        cd "$ROOT_DIR"
        CASEHUB_CHANGED_FILES="$1" CASEHUB_PR_LABELS="${2:-}" bash "$GUARD"
    )
}

expect_pass() {
    local name="$1"
    shift
    if ! output="$(run_guard "$@" 2>&1)"; then
        printf 'FAIL expected pass: %s\n%s\n' "$name" "$output" >&2
        exit 1
    fi
    printf 'ok pass: %s\n' "$name"
}

expect_fail() {
    local name="$1"
    shift
    if output="$(run_guard "$@" 2>&1)"; then
        printf 'FAIL expected fail: %s\n%s\n' "$name" "$output" >&2
        exit 1
    fi
    printf 'ok fail: %s\n' "$name"
}

expect_pass "non-deploy docs path passes without label" "docs/runbooks/readme.md" ""
expect_fail "docs-only does not override deploy workflow" ".github/workflows/deploy-prod.yml" "docs-only"
expect_fail "unknown workflow is gated during halt" ".github/workflows/auto-merge.yml" ""
expect_fail "guard workflow yaml extension is gated during halt" ".github/workflows/casehub-halt-guard.yaml" ""
expect_pass "ci-only can override workflow-only CI changes" ".github/workflows/auto-merge.yml" "ci-only"
expect_pass "halt-exception-approved can override guard changes" "scripts/casehub-halt-guard.sh" "halt-exception-approved"
