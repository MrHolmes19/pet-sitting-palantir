#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/local-postgres-env.sh
source "${SCRIPT_DIR}/local-postgres-env.sh"

INITIAL_SCHEMA="supabase/migrations/20260503000100_initial_schema.sql"
SEED_SQL="supabase/seed.sql"

require_docker_compose "initialize local Postgres"

docker compose up -d "${POSTGRES_SERVICE}"
wait_for_local_postgres

existing_table="$(
  docker compose exec -T "${POSTGRES_SERVICE}" \
    psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc \
    "select to_regclass('public.scrape_scopes')"
)"

if [[ "${existing_table}" == "scrape_scopes" ]]; then
  echo "Local database schema already exists. Applying seed data."
else
  docker compose exec -T "${POSTGRES_SERVICE}" \
    psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 \
    < "${INITIAL_SCHEMA}"
fi

docker compose exec -T "${POSTGRES_SERVICE}" \
  psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 \
  < "${SEED_SQL}"

echo "Local database is initialized with current seed data."
