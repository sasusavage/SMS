#!/usr/bin/env bash
# Coolify / Nixpacks startup script.
#
# Runs DB migrations on every deploy (idempotent), seeds demo data only when
# the database is empty (first deploy), then starts gunicorn bound to $PORT.
set -e

# Optional one-time clean slate: set DB_RESET=1 in Coolify env to drop the
# whole schema before migrating. Remove the var after the first clean deploy
# so you don't wipe data on every deploy.
echo "==> Checking for DB reset request..."
python db_reset.py

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
