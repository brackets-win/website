#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/.dev/logs"
mkdir -p "$LOG_DIR"

touch "$LOG_DIR/django.log" "$LOG_DIR/vite.log"
tail -f "$LOG_DIR/django.log" "$LOG_DIR/vite.log"
