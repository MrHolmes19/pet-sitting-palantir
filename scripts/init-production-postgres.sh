#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/production-postgres-env.sh
source "${SCRIPT_DIR}/production-postgres-env.sh"

load_production_database_url
confirm_production_access "initialize or update production schema and seed data"

uv --cache-dir .uv-cache run python -m pet_sitting_palantir --init-db --pretty
