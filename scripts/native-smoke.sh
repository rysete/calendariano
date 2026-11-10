#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}
SAMPLE_FILE=${SAMPLE_FILE:-"/home/ryse/gemini/escala-google-calendar/ESCALA CCT CAMPINAS IMPORTAÇÃO - 2026.xlsx"}
CSV_FILE=${CSV_FILE:-"/tmp/escala-native-smoke.csv"}
ICS_FILE=${ICS_FILE:-"/tmp/escala-native-smoke.ics"}

if [[ -d "$ROOT_DIR/backend/venv/lib" ]]; then
  VENV_SITE=$(find "$ROOT_DIR/backend/venv/lib" -maxdepth 2 -type d -name site-packages | head -n 1)
  if [[ -n "${VENV_SITE:-}" ]]; then
    export PYTHONPATH="$VENV_SITE${PYTHONPATH:+:$PYTHONPATH}"
  fi
fi

if [[ ! -f "$SAMPLE_FILE" ]]; then
  echo "sample file not found: $SAMPLE_FILE" >&2
  exit 2
fi

cd "$ROOT_DIR"
rm -f "$CSV_FILE" "$ICS_FILE"

PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}" CSV_FILE="$CSV_FILE" ICS_FILE="$ICS_FILE" "$PYTHON_BIN" - "$SAMPLE_FILE" <<'PY'
import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk  # noqa: F401
from gi.repository import Adw  # noqa: F401

from native.state import state

sample = sys.argv[1]
result = state.load_file(sample, col_nome=0)
snapshot = state.snapshot()

assert result["months"], "no months loaded"
assert snapshot["employees"], "no employees loaded"
assert snapshot["escala"], "no escala selected"

days = snapshot["escala"]["escala"]
assert days, "selected employee has no days"
state.update_day(0, status="TRABALHO", start_time="08:00", end_time="17:00")

csv_content = state.export_csv()
ics_content = state.export_ics()

assert "Subject,Start Date" in csv_content, "csv header missing"
assert b"BEGIN:VCALENDAR" in ics_content, "ics calendar missing"

with open(os.environ["CSV_FILE"], "w", encoding="utf-8", newline="") as handle:
    handle.write(csv_content)
with open(os.environ["ICS_FILE"], "wb") as handle:
    handle.write(ics_content)

print(f"months={len(result['months'])}")
print(f"employees={len(snapshot['employees'])}")
print(f"days={len(days)}")
print(f"csv_bytes={len(csv_content.encode('utf-8'))}")
print(f"ics_bytes={len(ics_content)}")
PY

test -s "$CSV_FILE"
test -s "$ICS_FILE"
