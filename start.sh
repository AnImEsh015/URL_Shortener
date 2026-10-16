#!/usr/bin/env bash
set -e

# 1. Run database migrations to apply latest schema changes
echo "==> Running database migrations..."
alembic upgrade head

# 2. Start Celery worker in the background with single concurrency to fit 512MB RAM
echo "==> Starting Celery background worker (--concurrency=1)..."
celery -A app.worker.celery_app worker --loglevel=info --concurrency=1 &

# 3. Start Uvicorn web server on 0.0.0.0:$PORT with a single worker
PORT="${PORT:-8000}"
echo "==> Starting Uvicorn on 0.0.0.0:${PORT} with 1 worker..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --workers 1
