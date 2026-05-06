#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/production-postgres-env.sh
source "${SCRIPT_DIR}/production-postgres-env.sh"

load_production_database_url
confirm_production_access "open an interactive psql session"

psql "${DATABASE_URL}"
