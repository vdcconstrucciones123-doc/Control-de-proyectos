#!/usr/bin/env bash
set -o errexit

export PLAYWRIGHT_BROWSERS_PATH="/opt/render/project/.playwright"
python -m playwright install chromium
exec gunicorn site_audit_report.wsgi:application
