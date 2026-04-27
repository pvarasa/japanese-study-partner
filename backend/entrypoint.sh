#!/bin/sh
set -e

if [ -n "$DATABASE_URL" ]; then
    echo "Running Alembic migrations..."
    uv run alembic upgrade head
fi

exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
