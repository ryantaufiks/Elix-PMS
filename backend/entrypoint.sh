#!/bin/sh
set -e

# Wait for PostgreSQL before doing anything that touches the database.
python - <<'PY'
import os, sys, time
import psycopg
import environ

url = environ.Env.db_url_config(os.environ["DATABASE_URL"])
for attempt in range(30):
    try:
        psycopg.connect(
            dbname=url["NAME"], user=url["USER"], password=url["PASSWORD"],
            host=url["HOST"], port=url["PORT"] or 5432, connect_timeout=3,
        ).close()
        break
    except psycopg.OperationalError:
        print("Waiting for database...", flush=True)
        time.sleep(2)
else:
    sys.exit("Database is not reachable")
PY

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    python manage.py migrate --noinput
fi

if [ "${DJANGO_COLLECTSTATIC:-0}" = "1" ]; then
    python manage.py collectstatic --noinput
fi

exec "$@"
