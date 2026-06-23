#!/bin/bash
# CaseHub Dev RAM Monitor
# Monitora uso de RAM dos containers Docker a cada 30s
# Alerta em 80%, ação em 95%
# Usage: ./scripts/dev-ram-monitor.sh [--once] [--log /path/to/log]

LOG_FILE="${2:-/tmp/casehub-ram-monitor.log}"
WARN_THRESHOLD=80
CRIT_THRESHOLD=95
INTERVAL=30
ONCE=false

[[ "$1" == "--once" ]] && ONCE=true

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

check_ram() {
    # Get docker stats for casehub-dev containers
    local stats
    stats=$(docker stats --no-stream --format "{{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}" 2>/dev/null | grep "casehub-dev")

    if [[ -z "$stats" ]]; then
        log "WARN: No casehub-dev containers running"
        return 1
    fi

    local total_pct=0
    local count=0
    local has_warning=false
    local has_critical=false

    while IFS=$'\t' read -r name mem_usage mem_pct; do
        # Strip % sign and spaces
        pct=$(echo "$mem_pct" | tr -d '% ')
        pct_int=${pct%.*}

        if [[ $pct_int -ge $CRIT_THRESHOLD ]]; then
            log "CRITICAL: $name at ${mem_pct} (${mem_usage})"
            has_critical=true
        elif [[ $pct_int -ge $WARN_THRESHOLD ]]; then
            log "WARNING: $name at ${mem_pct} (${mem_usage})"
            has_warning=true
        else
            log "OK: $name at ${mem_pct} (${mem_usage})"
        fi

        total_pct=$((total_pct + pct_int))
        count=$((count + 1))
    done <<< "$stats"

    # Check for orphan Chromium/Node processes (Playwright leftovers)
    local orphan_chromium
    orphan_chromium=$(pgrep -f "Chromium" 2>/dev/null | wc -l | tr -d ' ')
    local orphan_node
    orphan_node=$(pgrep -f "node.*playwright" 2>/dev/null | wc -l | tr -d ' ')

    if [[ $orphan_chromium -gt 2 ]]; then
        log "WARNING: $orphan_chromium orphan Chromium processes detected"
    fi
    if [[ $orphan_node -gt 2 ]]; then
        log "WARNING: $orphan_node orphan Playwright Node processes detected"
    fi

    # Critical action: kill non-essential containers
    if [[ "$has_critical" == true ]]; then
        log "ACTION: Restarting casehub-dev-redis to free RAM"
        docker restart casehub-dev-redis 2>/dev/null

        # Kill orphan Chromium processes older than 5 min
        if [[ $orphan_chromium -gt 0 ]]; then
            log "ACTION: Killing orphan Chromium processes"
            pkill -f "Chromium" 2>/dev/null
        fi
    fi

    # System RAM check (macOS)
    if command -v vm_stat &>/dev/null; then
        local page_size=16384
        local free_pages
        free_pages=$(vm_stat | grep "Pages free" | awk '{print $3}' | tr -d '.')
        local free_mb=$(( (free_pages * page_size) / 1048576 ))
        log "SYSTEM: ~${free_mb}MB free RAM"
    fi
}

# Main
log "=== RAM Monitor started (warn: ${WARN_THRESHOLD}%, crit: ${CRIT_THRESHOLD}%, interval: ${INTERVAL}s) ==="

if [[ "$ONCE" == true ]]; then
    check_ram
    exit 0
fi

while true; do
    check_ram
    sleep $INTERVAL
done
