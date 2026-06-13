#!/bin/bash
# ILC Tools Monitor v4 - Layout limpo

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'
BOLD='\033[1m'
DIM='\033[2m'

APP_DIR="${APP_BASE_PATH:-/opt/casehub}/ilc-tools"

draw_dashboard() {
    clear
    
    # PM2 Status
    PM2_JSON=$(pm2 jlist 2>/dev/null)
    PM2_STATUS=$(echo "$PM2_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); app=[x for x in d if x['name']=='ilc-tools']; print(app[0]['pm2_env']['status'] if app else 'stopped')" 2>/dev/null || echo "?")
    PM2_MEM=$(echo "$PM2_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); app=[x for x in d if x['name']=='ilc-tools']; print(f\"{app[0]['monit']['memory']//1024//1024}MB\" if app else '?')" 2>/dev/null || echo "?")
    PM2_CPU=$(echo "$PM2_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); app=[x for x in d if x['name']=='ilc-tools']; print(f\"{app[0]['monit']['cpu']}%\" if app else '?')" 2>/dev/null || echo "?")
    
    [ "$PM2_STATUS" == "online" ] && STATUS_ICON="${GREEN}● ONLINE${NC}" || STATUS_ICON="${RED}● OFFLINE${NC}"
    
    # Activity
    # Activity - using external Python script
    ACTIVITY=$(python3 "$APP_DIR/scripts/get_active_users.py" 2>/dev/null)

    
    if [ -n "$ACTIVITY" ]; then ACTIVE_COUNT=$(echo "$ACTIVITY" | wc -l | tr -d " "); else ACTIVE_COUNT=0; fi
    
    # Errors from file
    ERROR_COUNT=$(cat "$APP_DIR/data/errors.json" 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
    
    # Recent logs
    TODAY=$(date +%Y%m%d)
    LOG_FILE="$APP_DIR/logs/ilc_${TODAY}.log"
    
    # Header
    echo ""
    echo -e "  ${CYAN}${BOLD}ILC TOOLS MONITOR${NC} v4                        ${DIM}[Ctrl+C exit]${NC}"
    echo -e "  ${DIM}─────────────────────────────────────────────────────────────${NC}"
    echo ""
    
    # PM2 Status
    echo -e "  ${BOLD}PM2:${NC} $STATUS_ICON   ${DIM}Memory:${NC} $PM2_MEM   ${DIM}CPU:${NC} $PM2_CPU"
    echo ""
    
    # Active Users
    echo -e "  ${BOLD}👥 USUÁRIOS ATIVOS:${NC} ${GREEN}$ACTIVE_COUNT${NC}"
    if [ -n "$ACTIVITY" ] && [ "$ACTIVE_COUNT" -gt 0 ]; then
        echo "$ACTIVITY" | while IFS='|' read -r email page time_ago; do
            echo -e "     ${MAGENTA}$email${NC}  ${CYAN}$page${NC}  ${YELLOW}$time_ago${NC}"
        done
    else
        echo -e "     ${DIM}(aguardando atividade...)${NC}"
    fi
    echo ""
    
    # Recent Logs
    echo -e "  ${BOLD}📜 LOGS RECENTES:${NC}"
    tail -20 "$LOG_FILE" 2>/dev/null | grep -v 'GET /api/auth/me\|static\|favicon\|heartbeat' | tail -5 | while IFS= read -r line; do
        # Extract time and message
        time_part=$(echo "$line" | grep -oE '[0-9]{2}:[0-9]{2}:[0-9]{2}' | head -1)
        msg=$(echo "$line" | sed 's/.*INFO - //' | sed 's/.*ERROR - //' | sed 's/.*WARNING - //')
        msg_short="${msg:0:70}"
        
        if echo "$line" | grep -qi "error\|fail"; then
            echo -e "     ${RED}[$time_part] $msg_short${NC}"
        elif echo "$line" | grep -qi "generated\|success\|created"; then
            echo -e "     ${GREEN}[$time_part] $msg_short${NC}"
        else
            echo -e "     ${DIM}[$time_part] $msg_short${NC}"
        fi
    done
    echo ""
    
    # Errors
    if [ "$ERROR_COUNT" -gt 0 ] 2>/dev/null; then
        echo -e "  ${RED}${BOLD}⚠️  ERROS PENDENTES: $ERROR_COUNT${NC}"
        cat "$APP_DIR/data/errors.json" 2>/dev/null | python3 -c "
import sys, json
try:
    errors = json.load(sys.stdin)
    for i, e in enumerate(errors[:3]):
        ts = e.get('timestamp', '')[-8:-3]
        msg = e.get('message', '')[:50]
        print(f'     [{i}] {ts} {msg}')
except:
    pass
" 2>/dev/null
    else
        echo -e "  ${GREEN}✅ Sem erros pendentes${NC}"
    fi
    
    echo ""
    echo -e "  ${DIM}─────────────────────────────────────────────────────────────${NC}"
    echo -e "  ${CYAN}Atualizado: $(date '+%H:%M:%S')${NC}  |  Refresh: 3s"
}

trap 'echo -e "\n${GREEN}Monitor encerrado.${NC}"; exit 0' INT

while true; do
    draw_dashboard
    sleep 3
done
