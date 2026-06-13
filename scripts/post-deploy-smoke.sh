#!/usr/bin/env bash
# CaseHub — smoke test pós-deploy para o alpha (casehub.legal / Mumbai)
# Uso: ./scripts/post-deploy-smoke.sh [BASE_URL]
# Default BASE_URL: https://casehub.legal
# Exit 0 = OK, Exit 1 = falhou
set -euo pipefail

BASE_URL="${1:-https://casehub.legal}"
PREFIX="${2:-/casehub}"
TIMEOUT=90
INTERVAL=5

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; }
info() { echo -e "${YELLOW}→${NC} $1"; }

info "Smoke test: $BASE_URL (timeout ${TIMEOUT}s)"
deadline=$((SECONDS + TIMEOUT))

while [ "$SECONDS" -lt "$deadline" ]; do
  landing=$(curl -sL -o /tmp/_smoke_landing.html -w '%{http_code}' "$BASE_URL/" 2>/dev/null || echo "000")
  login=$(curl -sL -o /tmp/_smoke_login.html -w '%{http_code}' "$BASE_URL$PREFIX/login" 2>/dev/null || echo "000")
  health=$(curl -sL -o /tmp/_smoke_health.json -w '%{http_code}' "$BASE_URL$PREFIX/healthz" 2>/dev/null || echo "000")

  land_ok=0; login_ok=0; health_ok=0
  [ "$landing" = "200" ] && grep -q "CaseHub" /tmp/_smoke_landing.html 2>/dev/null && land_ok=1
  [ "$login" = "200" ] && grep -q "Acesse o ambiente\|login\|email" /tmp/_smoke_login.html 2>/dev/null && login_ok=1
  [ "$health" = "200" ] && health_ok=1

  if [ $land_ok -eq 1 ] && [ $login_ok -eq 1 ] && [ $health_ok -eq 1 ]; then
    pass "landing $BASE_URL/ → $landing"
    pass "login   $BASE_URL$PREFIX/login → $login"
    pass "health  $BASE_URL$PREFIX/healthz → $health"
    echo ""
    cat /tmp/_smoke_health.json 2>/dev/null | python3 -m json.tool 2>/dev/null || cat /tmp/_smoke_health.json || true
    echo ""
    pass "Todos os checks passaram — deploy OK"
    exit 0
  fi

  info "aguardando app: landing=$landing login=$login health=$health (${SECONDS}s/${TIMEOUT}s)"
  sleep "$INTERVAL"
done

fail "Smoke test falhou após ${TIMEOUT}s"
fail "landing=$landing login=$login health=$health"
echo "--- /tmp/_smoke_health.json ---"
cat /tmp/_smoke_health.json 2>/dev/null || true
exit 1
