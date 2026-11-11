FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# pg_dump for platform backups (System → Backups), from PostgreSQL's own repository so it matches the
# database server's major version (docker-compose.yml: postgres:16) and its dumps restore cleanly.
ARG PG_MAJOR=16
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $VERSION_CODENAME-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-$PG_MAJOR \
    && apt-get upgrade -y \
    && apt-get purge -y curl && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip setuptools && pip install -r requirements.txt

COPY . .
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data/media /data/backups /app/staticfiles \
    && chown -R app:app /data /app \
    && chmod +x /app/entrypoint.sh

USER app
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
# Two processes, one per vCPU (one Python process uses a single core); WebSockets work across them
# through the Redis channel layer. WEB_WORKERS overrides the count.
CMD ["sh", "-c", "exec uvicorn myproject.asgi:application --log-config myproject/uvicorn-logging.json --host 0.0.0.0 --port 8000 --workers ${WEB_WORKERS:-2} --no-server-header --timeout-graceful-shutdown 20"]
