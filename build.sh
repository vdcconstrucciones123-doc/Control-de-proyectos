#!/usr/bin/env bash
set -o errexit

export PLAYWRIGHT_BROWSERS_PATH="/opt/render/project/.playwright"

pip install -r requirements.txt
python -m playwright install --with-deps chromium
python manage.py collectstatic --no-input
python manage.py migrate
python manage.py ensure_admin_user
python manage.py collectstatic --no-input
python manage.py migrate
python manage.py ensure_admin_user