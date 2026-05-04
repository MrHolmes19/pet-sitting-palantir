#!/usr/bin/env bash
set -euo pipefail

LOCAL_DATABASE_URL="postgresql://palantir:palantir@localhost:54321/pet_sitting_palantir"
POSTGRES_SERVICE="postgres"
POSTGRES_USER="palantir"
POSTGRES_DB="pet_sitting_palantir"
MAX_READY_CHECKS=30

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to run local Postgres integration tests." >&2
  echo "Install Docker or enable Docker Desktop WSL integration, then retry." >&2
  exit 1
fi

if ! docker --version >/dev/null 2>&1; then
  echo "Docker is installed but is not available in this shell." >&2
  echo "Start Docker or enable Docker Desktop WSL integration, then retry." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose is required to run local Postgres integration tests." >&2
  exit 1
fi

docker compose up -d "${POSTGRES_SERVICE}"

for attempt in $(seq 1 "${MAX_READY_CHECKS}"); do
  if docker compose exec -T "${POSTGRES_SERVICE}" \
    pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
    break
  fi

  if [[ "${attempt}" == "${MAX_READY_CHECKS}" ]]; then
    echo "Postgres did not become ready after ${MAX_READY_CHECKS} checks." >&2
    exit 1
  fi

  sleep 1
done

TEST_DATABASE_URL="${TEST_DATABASE_URL:-${LOCAL_DATABASE_URL}}" \
  uv --cache-dir .uv-cache run pytest \
    tests/test_database_integration.py \
    tests/test_storage_integration.py
