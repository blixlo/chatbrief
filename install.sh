#!/bin/sh
# Install ChatBrief dependencies for the chosen interpreter.
# Tries: "$PYTHON" -m pip install --user -r requirements.txt
# Falls back to a local .venv when pip refuses (PEP 668 externally-managed).
# A venv is an option, not a requirement. Usage:
#   ./install.sh           # runtime deps (requirements.txt)
#   ./install.sh --dev     # plus pytest (requirements-dev.txt)
#   PYTHON=python3 ./install.sh
set -eu

cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
if [ "${1:-}" = "--dev" ]; then
  REQ="$PWD/requirements-dev.txt"
else
  REQ="$PWD/requirements.txt"
fi

if ! PY=$("$PYTHON" -c 'import sys; print(sys.executable)'); then
  echo "Could not run PYTHON='$PYTHON'. Install Python 3 or set PYTHON to one." >&2
  exit 1
fi

log() { printf '%s
' "$*"; }

install_venv() {
  log "pip --user was refused (this Python is externally managed, PEP 668). Creating a local .venv instead."
  if [ ! -x .venv/bin/python ]; then
    "$PY" -m venv .venv
  fi
  .venv/bin/python -m pip install -r "$REQ"
  log "Installed into .venv. Use this Python for every command:"
  log "  $PWD/.venv/bin/python -m tg_recap ..."
}

log_file=$(mktemp)
trap 'rm -f "$log_file"' EXIT

if "$PY" -m pip install --user -r "$REQ" >"$log_file" 2>&1; then
  cat "$log_file"
  log "Installed for $PY. Use this Python for every command:"
  log "  $PY -m tg_recap ..."
else
  status=$?
  cat "$log_file"
  if grep -qiE 'externally-managed|EXTERNALLY-MANAGED' "$log_file"; then
    install_venv
  else
    log "Install failed (exit $status). If this Python is externally managed, run:"
    log "  $PY -m venv .venv && .venv/bin/python -m pip install -r $REQ"
    exit "$status"
  fi
fi
