#!/usr/bin/env bash
# Coolify / Nixpacks startup script.
#
# Runs DB migrations on every deploy (idempotent), seeds demo data only when
# the database is empty (first deploy), then starts gunicorn bound to $PORT.
set -e

echo "==> Running database migrations..."
python -m flask --app app db upgrade

echo "==> Seeding demo data if database is empty..."
python seed_if_empty.py

echo "==> Starting gunicorn on 0.0.0.0:${PORT:-8000}..."
exec gunicorn "app:app" \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-3}" \
  --timeout 60 \
  --access-logfile - \
  --error-logfile -
