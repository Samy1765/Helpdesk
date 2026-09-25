#!/bin/sh
# Precision AI container entrypoint: migrate, optionally seed demo data, then serve.
set -e

echo "Waiting for the database and applying migrations..."
i=0
until alembic upgrade head; do
  i=$((i + 1))
  if [ "$i" -ge 30 ]; then echo "Database not reachable after 30 attempts" >&2; exit 1; fi
  sleep 2
done

if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  echo "Seeding demo data (idempotent)..."
  python -m app.database.seed
else
  echo "Bootstrapping reference data (roles, teams, categories, IT knowledge base)..."
  python -m app.scripts.bootstrap
fi

# One worker: the FAISS index lives in-process. Scale out by swapping the VectorStore for pgvector.
exec uvicorn app.main:app --host 0.0.0.0 --port "${APP_PORT:-8000}" --workers 1 --proxy-headers --forwarded-allow-ips="*"
