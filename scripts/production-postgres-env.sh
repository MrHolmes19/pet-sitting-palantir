#!/usr/bin/env bash

PRODUCTION_ENV_FILE=".env.production"
PRODUCTION_CONFIRMATION="I understand"

load_production_database_url() {
  if [[ ! -f "${PRODUCTION_ENV_FILE}" ]]; then
    echo "Missing ${PRODUCTION_ENV_FILE}." >&2
    echo "Copy .env.production.example to ${PRODUCTION_ENV_FILE} and set DATABASE_URL." >&2
    exit 1
  fi

  set -a
  # shellcheck source=/dev/null
  source "${PRODUCTION_ENV_FILE}"
  set +a

  if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "DATABASE_URL is missing in ${PRODUCTION_ENV_FILE}." >&2
    exit 1
  fi
}

confirm_production_access() {
  local purpose="${1:-connect to production}"

  echo "WARNING: this will ${purpose} using ${PRODUCTION_ENV_FILE}." >&2
  echo "This is the production Supabase/Postgres database." >&2
  echo "Type exactly: ${PRODUCTION_CONFIRMATION}" >&2
  read -r confirmation

  if [[ "${confirmation}" != "${PRODUCTION_CONFIRMATION}" ]]; then
    echo "Confirmation did not match. Aborting." >&2
    exit 1
  fi
}
