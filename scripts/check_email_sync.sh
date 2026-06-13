#!/bin/bash
# Monitor de sync de emails do CaseHub
# Alerta se nao houver emails novos nas ultimas 2 horas durante horario comercial (9h-21h EST)

HOUR=$(date +%H)
if [ $HOUR -lt 9 ] || [ $HOUR -gt 21 ]; then
    exit 0  # Fora do horario, nao verificar
fi

# Checar ultimo email recebido
LAST_EMAIL=$(cd /var/www/immigrant.law/casehub && source venv/bin/activate && python3 -c "
from models import SessionLocal
from sqlalchemy import text
db = SessionLocal()
r = db.execute(text('SELECT MAX(received_at) FROM email_messages'))
row = r.fetchone()
if row and row[0]:
    from datetime import datetime, timezone
    diff = (datetime.now() - row[0]).total_seconds() / 3600
    print(f'{diff:.1f}')
else:
    print('999')
db.close()
" 2>/dev/null)

if [ -z "$LAST_EMAIL" ]; then
    echo "[EMAIL-MONITOR] ERRO: Nao conseguiu checar ultimo email" >> /var/log/casehub-monitor.log
    exit 1
fi

# Se mais de 2 horas sem email novo
THRESHOLD=2
if (( $(echo "$LAST_EMAIL > $THRESHOLD" | bc -l) )); then
    MSG="[ALERTA] CaseHub: Nenhum email novo nas ultimas ${LAST_EMAIL}h. Verificar sync IMAP!"
    echo "$(date): $MSG" >> /var/log/casehub-monitor.log
    # NOTA: Restart removido em 14/02/2026 - reiniciar casehub nao resolve problemas de IMAP
    # Apenas loggar o alerta
else
    echo "$(date): OK - Ultimo email ha ${LAST_EMAIL}h" >> /var/log/casehub-monitor.log
fi
