#!/bin/bash
# ============================================================================
# CaseHub - Git History Scrub Script
# Remove sensitive files (credentials, tokens, .env) from ALL git commits
#
# IMPORTANT: Run this AFTER backing up the repo!
#   cp -r .git .git-backup
#
# Usage: bash scripts/scrub-git-history.sh
# ============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}=== CaseHub Git History Scrub ===${NC}"
echo ""

# Check we're in the repo root
if [ ! -f "app.py" ] || [ ! -d ".git" ]; then
    echo -e "${RED}ERROR: Run this script from the casehub root directory${NC}"
    exit 1
fi

# Check git-filter-repo is available
if ! python3 -c "import git_filter_repo" 2>/dev/null; then
    echo -e "${RED}ERROR: git-filter-repo not installed. Run: pip3 install git-filter-repo${NC}"
    exit 1
fi

# Confirm backup
echo -e "${YELLOW}WARNING: This will rewrite ALL git history.${NC}"
echo "Make sure you have a backup of .git before proceeding."
read -p "Have you backed up? (y/N): " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "Aborting. Run: cp -r .git .git-backup"
    exit 1
fi

echo ""
echo -e "${GREEN}Scrubbing sensitive files from git history...${NC}"

# Run git-filter-repo to remove sensitive paths
python3 -m git_filter_repo \
    --invert-paths \
    --path .env \
    --path credentials/ \
    --path google_drive_credentials.json \
    --path pentest.py \
    --path services/document-tools/google_calendar_credentials.json \
    --path-glob '*.pickle' \
    --path-glob '*.p12' \
    --path-glob '*.pem' \
    --path-glob '*token*.json' \
    --path-glob '*secret*.json' \
    --force

echo ""
echo -e "${GREEN}Done! Sensitive files removed from all commits.${NC}"
echo ""
echo -e "${YELLOW}Next steps for Equipe CaseHub:${NC}"
echo "  1. Verify with: git log --all --diff-filter=A --name-only --format='%H' | grep -E '\\.env|credentials|token|secret|pentest'"
echo "  2. If pushing to remote: git push --force-with-lease"
echo "  3. Rotate ALL credentials (Stripe, Google OAuth, DB password, SECRET_KEY, ENCRYPTION_KEY)"
echo "  4. Delete backup: rm -rf .git-backup"
