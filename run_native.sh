#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

export ESCALA_APP_DIR="$ROOT_DIR"
export ESCALA_PYTHON="${ESCALA_PYTHON:-python3}"
export ESCALA_WEB_EDITOR_PORT="${ESCALA_WEB_EDITOR_PORT:-8765}"

if [[ -d "$ROOT_DIR/backend/venv/lib" ]]; then
  VENV_SITE=$(find "$ROOT_DIR/backend/venv/lib" -maxdepth 2 -type d -name site-packages | head -n 1)
  if [[ -n "${VENV_SITE:-}" ]]; then
    export PYTHONPATH="$VENV_SITE${PYTHONPATH:+:$PYTHONPATH}"
  fi
fi

exec "$ROOT_DIR/flatpak/escala-web-editor"
