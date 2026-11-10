#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PORT=${ESCALA_WEB_EDITOR_PORT:-8765}
URL="http://127.0.0.1:${PORT}"

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
  printf "%b%s%b\n" "$BLUE" "$1" "$NC"
}

ok() {
  printf "%b%s%b\n" "$GREEN" "$1" "$NC"
}

warn() {
  printf "%b%s%b\n" "$YELLOW" "$1" "$NC"
}

open_url() {
  if [[ "${ESCALA_OPEN_BROWSER:-1}" == "0" ]]; then
    return
  fi

  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 &
  elif command -v gio >/dev/null 2>&1; then
    gio open "$URL" >/dev/null 2>&1 &
  else
    warn "Abra manualmente: $URL"
  fi
}

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

log "Preparando backend Python..."
cd "$ROOT_DIR/backend"
if [[ ! -d venv ]]; then
  python3 -m venv venv
fi
./venv/bin/python -m pip install -q -r requirements.txt

log "Preparando frontend React..."
cd "$ROOT_DIR/frontend"
if [[ ! -d node_modules ]]; then
  npm install --silent
fi
npm run build

log "Iniciando Escala Web local em $URL"
cd "$ROOT_DIR"
export HOST=127.0.0.1
export PORT="$PORT"
export ESCALA_WEB_EDITOR_PORT="$PORT"
export UVICORN_RELOAD=0
export FRONTEND_DIST="$ROOT_DIR/frontend/dist"

"$ROOT_DIR/backend/venv/bin/python" -m backend.main &
BACKEND_PID=$!

sleep 1
open_url

ok "Rodando em $URL"
warn "Para Google Agenda local, cadastre este redirect URI no Google Cloud:"
warn "$URL/api/google/callback"
warn "Ctrl+C encerra a versao local."

wait "$BACKEND_PID"
