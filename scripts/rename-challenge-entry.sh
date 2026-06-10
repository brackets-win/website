#!/usr/bin/env bash
# Rename a bracket challenge entry by join code and current display name.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/backend/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "error: backend/.venv not found — create it first, then re-run." >&2
  exit 1
fi

exec "$PYTHON" "$ROOT/backend/manage.py" rename_challenge_entry "$@"
