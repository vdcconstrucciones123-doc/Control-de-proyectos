#!/usr/bin/env bash
set -o errexit

# WeasyPrint system dependencies (pre-installed on Render Ubuntu, included for safety)
apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf2.0-0 2>/dev/null || true

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
python manage.py ensure_admin_user