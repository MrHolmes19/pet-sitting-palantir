#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

HOST="${ANALYTICS_DASHBOARD_HOST:-127.0.0.1}"
PORT="${ANALYTICS_DASHBOARD_PORT:-8502}"

echo "Starting analytics dashboard at http://${HOST}:${PORT}" >&2
echo "Press Ctrl+C to stop it." >&2

exec uv --cache-dir .uv-cache run streamlit run analytics/dashboard.py \
  --server.headless=true \
  --browser.gatherUsageStats=false \
  --server.address="${HOST}" \
  --server.port="${PORT}"
