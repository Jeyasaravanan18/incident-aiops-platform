#!/usr/bin/env sh
set -eu

echo "Running Alembic migrations..."
alembic upgrade head

if [ "${AUTO_SEED:-false}" = "true" ]; then
    echo "AUTO_SEED=true: Seeding database with initial scenario..."
    python -m app.scripts.seed || echo "Seed skipped or already populated."
fi

echo "Starting Uvicorn on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"

