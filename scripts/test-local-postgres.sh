#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/local-postgres-env.sh
source "${SCRIPT_DIR}/local-postgres-env.sh"

require_docker_compose "run local Postgres integration tests"

docker compose up -d "${POSTGRES_SERVICE}"
wait_for_local_postgres

TEST_DATABASE_URL="${TEST_DATABASE_URL:-${LOCAL_DATABASE_URL}}" \
  uv --cache-dir .uv-cache run pytest \
    tests/test_database_integration.py \
    tests/test_storage_integration.py
