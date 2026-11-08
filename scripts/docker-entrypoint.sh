#!/bin/sh
# Container start.
#
# - With arguments (docker-compose `command:`, one-off `manage.py` runs): run them as given.
# - Without LITESTREAM_REPLICA_URL: start gunicorn. Run migrations as a release step (docs/deployment.md).
# - With LITESTREAM_REPLICA_URL (SQLite + Litestream, e.g. Cloud Run with max 1 instance):
#   restore the database from the replica if the local file is missing, migrate, then run gunicorn under
#   `litestream replicate -exec` (Litestream forwards SIGTERM to gunicorn and syncs a last time).
set -eu

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

SERVER="gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --access-logfile -"

if [ -z "${LITESTREAM_REPLICA_URL:-}" ]; then
  # shellcheck disable=SC2086
  exec $SERVER
fi

export DB_PATH="${DB_PATH:-/data/db.sqlite3}"
case "${DATABASE_URL:-}" in
  "") export DATABASE_URL="sqlite:///${DB_PATH}" ;;
  "sqlite:///${DB_PATH}") ;;
  *)
    echo "entrypoint: LITESTREAM_REPLICA_URL is set, so DATABASE_URL must be sqlite:///${DB_PATH} (or unset)." >&2
    exit 1
    ;;
esac
mkdir -p "$(dirname "$DB_PATH")"

echo "entrypoint: restoring $DB_PATH from the replica if the file is missing"
litestream restore -config /app/litestream.yml -if-db-not-exists -if-replica-exists "$DB_PATH"

if [ "${MIGRATE_ON_START:-true}" = "true" ]; then
  echo "entrypoint: migrate"
  python manage.py migrate --noinput
fi

echo "entrypoint: replicate + serve"
exec litestream replicate -config /app/litestream.yml -exec "$SERVER"
