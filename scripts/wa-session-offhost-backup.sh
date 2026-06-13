#!/usr/bin/env bash
# wa-session-offhost-backup.sh — backup OFF-HOST do volume da sessao do WhatsApp.
#
# POR QUE: os backups internos do bot (_bak-...__lastgood / __prewipe) vivem DENTRO
# do volume Docker `casehub_whatsapp_session`. Se o volume for destruido
# (`docker compose down -v`, `docker volume rm`, prune), eles vao junto. Este script
# copia o volume para FORA do Docker (/root/wa-session-backups), sobrevivendo ate a
# isso — a ultima camada de defesa contra perda total do pareamento.
#
# SEGURO: read-only sobre os dados (tar nao modifica nada). Idempotente. Mantem os
# ultimos N snapshots. REVERSIVEL: `crontab -e` removendo a linha + apagar este arquivo.
#
# Instalacao (Mumbai), cron diario 04:00 UTC:
#   0 4 * * * /usr/local/bin/wa-session-offhost-backup.sh >> /root/wa-session-backups/backup.log 2>&1
#
# Restauracao (manual, supervisionada): parar o bot, extrair o .tgz desejado de volta
# para /var/lib/docker/volumes/casehub_whatsapp_session/_data, subir o bot.
set -euo pipefail

VOLUME="${WA_VOLUME:-casehub_whatsapp_session}"
SRC="${WA_SRC:-/var/lib/docker/volumes/${VOLUME}/_data}"
DEST="${WA_BACKUP_DIR:-/root/wa-session-backups}"
KEEP="${WA_BACKUP_KEEP:-14}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
now() { date -u +%FT%TZ; }

if [ ! -d "$SRC" ]; then
  echo "[$(now)] SKIP: volume nao encontrado em $SRC"
  exit 0
fi

mkdir -p "$DEST"
OUT="${DEST}/wa-session-${TS}.tgz"

# Snapshot read-only do volume inteiro (todas as orgs + backups internos do bot).
# tar pode retornar !=0 se um arquivo mudar durante a leitura (LevelDB vivo) — isso
# nao e fatal: o snapshot diario ainda e util e o proximo corrige.
if tar czf "$OUT" -C "$SRC" . 2>/dev/null; then
  echo "[$(now)] OK: $OUT ($(du -h "$OUT" | cut -f1))"
else
  echo "[$(now)] WARN: tar com aviso (arquivo mudou durante snapshot); $OUT pode estar parcial"
fi

# Retencao: mantem os $KEEP mais novos, apaga o resto.
mapfile -t all < <(ls -1t "${DEST}"/wa-session-*.tgz 2>/dev/null || true)
if [ "${#all[@]}" -gt "$KEEP" ]; then
  for old in "${all[@]:$KEEP}"; do
    rm -f "$old" && echo "[$(now)] prune: $old"
  done
fi
exit 0
