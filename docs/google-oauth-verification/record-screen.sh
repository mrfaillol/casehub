#!/usr/bin/env bash
# Gravacao de tela para o video de verificacao OAuth do CaseHub.
# Uso:  ./record-screen.sh           (tela inteira, sem audio)
#       ./record-screen.sh --audio   (tela inteira + microfone)
#       ./record-screen.sh --list    (lista dispositivos avfoundation e sai)
# Parar: Ctrl+C  (o arquivo .mp4/.mov fica em ./takes/)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="$DIR/takes"
mkdir -p "$OUT_DIR"
TS="$(date +%Y%m%d-%H%M%S)"

if [[ "${1:-}" == "--list" ]]; then
  if command -v ffmpeg >/dev/null 2>&1; then
    ffmpeg -f avfoundation -list_devices true -i "" 2>&1 | sed -n '/AVFoundation/,$p'
  else
    echo "ffmpeg nao instalado. Instale com: brew install ffmpeg"
  fi
  exit 0
fi

WANT_AUDIO=0
[[ "${1:-}" == "--audio" ]] && WANT_AUDIO=1

if command -v ffmpeg >/dev/null 2>&1; then
  # avfoundation: "<video>:<audio>". Tela principal costuma ser indice 1
  # ("Capture screen 0"); microfone costuma ser indice 0. Rode --list p/ confirmar.
  SCREEN_INDEX="${CASEHUB_SCREEN_INDEX:-1}"
  MIC_INDEX="${CASEHUB_MIC_INDEX:-0}"
  OUT="$OUT_DIR/casehub-oauth-$TS.mp4"
  if [[ "$WANT_AUDIO" == "1" ]]; then INPUT="${SCREEN_INDEX}:${MIC_INDEX}"; else INPUT="${SCREEN_INDEX}:none"; fi
  echo "Gravando (ffmpeg/avfoundation) -> $OUT"
  echo "Tela=$SCREEN_INDEX  Audio=$([[ $WANT_AUDIO == 1 ]] && echo $MIC_INDEX || echo nenhum)"
  echo "Pare com Ctrl+C. (Tela errada? defina CASEHUB_SCREEN_INDEX e rode --list)"
  # 30fps, downscale p/ <=1920 largura par, H.264 yuv420p compat maxima, faststart.
  exec ffmpeg -hide_banner \
    -f avfoundation -framerate 30 -capture_cursor 1 -i "$INPUT" \
    -vf "scale='min(1920,iw)':-2:flags=lanczos" \
    -c:v libx264 -preset veryfast -crf 20 -pix_fmt yuv420p \
    $([[ $WANT_AUDIO == 1 ]] && echo "-c:a aac -b:a 128k") \
    -movflags +faststart \
    "$OUT"
else
  # Fallback nativo macOS (sem instalar nada). Grava tela inteira em .mov. Ctrl+C para parar.
  OUT="$OUT_DIR/casehub-oauth-$TS.mov"
  echo "ffmpeg ausente — usando screencapture nativo -> $OUT"
  echo "Pare com Ctrl+C. Para audio, prefira instalar ffmpeg (brew install ffmpeg)."
  exec screencapture -v -C "$OUT"
fi
