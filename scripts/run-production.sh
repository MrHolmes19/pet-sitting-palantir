#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

# shellcheck source=scripts/production-postgres-env.sh
source "${SCRIPT_DIR}/production-postgres-env.sh"
load_production_database_url

echo "Applying pending production database migrations." >&2
uv --cache-dir .uv-cache run python -m pet_sitting_palantir --init-db --pretty

echo "Starting the production home runner. Press Ctrl+C to stop it." >&2
exec uv --cache-dir .uv-cache run python -m pet_sitting_palantir \
  --run-continuously \
  --max-pages all
