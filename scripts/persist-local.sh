#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/local-postgres-env.sh
source "${SCRIPT_DIR}/local-postgres-env.sh"

SCOPE="${1:-auckland_central}"
MAX_PAGES="${2:-all}"

if [[ "${MAX_PAGES}" != "all" ]]; then
  echo "Persisted local scrapes require max pages 'all' for complete lifecycle coverage." >&2
  exit 2
fi

DATABASE_URL="${LOCAL_DATABASE_URL}" \
  uv --cache-dir .uv-cache run python -m pet_sitting_palantir \
    --scope "${SCOPE}" \
    --max-pages "${MAX_PAGES}" \
    --persist \
    --pretty
