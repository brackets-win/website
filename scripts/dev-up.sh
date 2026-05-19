#!/usr/bin/env bash
# Start Django + Vite detached. Survives terminal close; stop with npm run dev:down.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="$ROOT/.dev"
LOG_DIR="$STATE_DIR/logs"
mkdir -p "$LOG_DIR"

PYTHON="$ROOT/backend/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON="$(command -v python3)"
  else
    echo "error: no backend/.venv and no python3 on PATH" >&2
    exit 1
  fi
fi

VITE="$ROOT/frontend/node_modules/.bin/vite"
if [[ ! -x "$VITE" ]]; then
  echo "error: run npm install in frontend/ first" >&2
  exit 1
fi

is_running() {
  local pidfile="$1"
  [[ -f "$pidfile" ]] || return 1
  local pid
  pid="$(<"$pidfile")"
  kill -0 "$pid" 2>/dev/null
}

start_service() {
  local name="$1"
  local cmd="$2"
  local pidfile="$STATE_DIR/${name}.pid"
  local logfile="$LOG_DIR/${name}.log"

  if is_running "$pidfile"; then
    echo "✓ ${name} already running (pid $(<"$pidfile"))"
    return 0
  fi

  rm -f "$pidfile"
  # shellcheck disable=SC2091
  nohup bash -c "$cmd" >>"$logfile" 2>&1 &
  echo $! >"$pidfile"
  sleep 0.5
  if ! is_running "$pidfile"; then
    echo "error: ${name} failed to start. Last log lines:" >&2
    tail -20 "$logfile" >&2 || true
    rm -f "$pidfile"
    exit 1
  fi
  echo "✓ ${name} started (pid $(<"$pidfile"), log: ${logfile})"
}

start_service django "cd \"$ROOT/backend\" && exec \"$PYTHON\" manage.py runserver 8000"
start_service vite "cd \"$ROOT/frontend\" && exec \"$VITE\""

echo ""
echo "Frontend: http://localhost:3000/"
echo "API:      http://localhost:8000/"
echo "Logs:     npm run dev:logs"
echo "Stop:     npm run dev:down"
