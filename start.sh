#!/usr/bin/env bash
set -o errexit

export PORT="${PORT:-8000}"
export PLAYWRIGHT_BROWSERS_PATH="/opt/render/project/.playwright"

echo "Starting app on port ${PORT}"
python -m playwright install chromium
python manage.py migrate --noinput
python manage.py ensure_admin_user

exec gunicorn site_audit_report.wsgi:application \
  --bind "0.0.0.0:${PORT}" \
  --workers 1 \
  --timeout 120
