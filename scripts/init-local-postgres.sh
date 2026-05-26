#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/local-postgres-env.sh
source "${SCRIPT_DIR}/local-postgres-env.sh"

SEED_SQL="supabase/seed.sql"

require_docker_compose "initialize local Postgres"

docker compose up -d "${POSTGRES_SERVICE}"
wait_for_local_postgres

DATABASE_URL="${LOCAL_DATABASE_URL}" \
  uv --cache-dir .uv-cache run python -m pet_sitting_palantir --init-db

docker compose exec -T "${POSTGRES_SERVICE}" \
  psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 \
  < "${SEED_SQL}"

echo "Local database is initialized with current seed data."
