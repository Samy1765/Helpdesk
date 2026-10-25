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
# X-Forwarded-For / -Proto are trusted only from FORWARDED_ALLOW_IPS (set it to your reverse proxy's address);
# otherwise any client could spoof the IP used by the audit log and the sign-in rate limits.
# The container always listens on 8000 (EXPOSE, HEALTHCHECK); APP_PORT only picks the host port in docker-compose.yml.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers \
  --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}"
