#!/bin/bash
set -euo pipefail

# Migrations run in fly.toml release_command; keep as fallback for local Docker runs.
python3 manage.py migrate --noinput

exec gunicorn --bind :8000 --workers 2 --timeout 120 website.wsgi
