#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="$ROOT/.dev"

stop_service() {
  local name="$1"
  local pidfile="$STATE_DIR/${name}.pid"
  if [[ ! -f "$pidfile" ]]; then
    echo "· ${name} not running (no pid file)"
    return 0
  fi
  local pid
  pid="$(<"$pidfile")"
  if kill -0 "$pid" 2>/dev/null; then
    # Child processes (e.g. old npm wrappers) if any remain.
    pkill -P "$pid" 2>/dev/null || true
    kill "$pid" 2>/dev/null || true
    echo "✓ ${name} stopped (pid ${pid})"
  else
    echo "· ${name} was not running (stale pid ${pid})"
  fi
  rm -f "$pidfile"
}

stop_service django
stop_service vite
