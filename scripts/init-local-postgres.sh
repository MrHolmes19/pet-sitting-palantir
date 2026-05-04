#!/usr/bin/env bash
set -euo pipefail

POSTGRES_SERVICE="postgres"
POSTGRES_USER="palantir"
POSTGRES_DB="pet_sitting_palantir"
INITIAL_SCHEMA="supabase/migrations/20260503000100_initial_schema.sql"
SEED_SQL="supabase/seed.sql"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to initialize local Postgres." >&2
  exit 1
fi

docker compose up -d "${POSTGRES_SERVICE}"

existing_table="$(
  docker compose exec -T "${POSTGRES_SERVICE}" \
    psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc \
    "select to_regclass('public.scrape_scopes')"
)"

if [[ "${existing_table}" == "scrape_scopes" ]]; then
  echo "Local database schema already exists. Nothing to initialize."
  echo "To start over, run: docker compose down -v"
  exit 0
fi

docker compose exec -T "${POSTGRES_SERVICE}" \
  psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 \
  < "${INITIAL_SCHEMA}"

docker compose exec -T "${POSTGRES_SERVICE}" \
  psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 \
  < "${SEED_SQL}"

echo "Local database initialized with schema and seed data."
