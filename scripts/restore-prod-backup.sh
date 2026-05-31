#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

# shellcheck source=scripts/production-postgres-env.sh
source "${SCRIPT_DIR}/production-postgres-env.sh"

PRODUCTION_RESTORE_CONFIRMATION="restore production"

usage() {
  echo "Usage: scripts/restore-prod-backup.sh .backups/<timestamp>" >&2
}

if [[ "$#" -ne 1 ]]; then
  usage
  exit 1
fi

backup_dir="${1%/}"
schema_file="${backup_dir}/schema.sql"
data_file="${backup_dir}/data.sql"
manifest_file="${backup_dir}/manifest.json"

if [[ ! -d "${backup_dir}" ]]; then
  echo "Backup directory does not exist: ${backup_dir}" >&2
  exit 1
fi

for required_file in "${schema_file}" "${data_file}" "${manifest_file}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "Backup is missing required file: ${required_file}" >&2
    exit 1
  fi
done

if ! command -v psql >/dev/null 2>&1; then
  echo "psql is required to restore production." >&2
  echo "Install PostgreSQL client tools, then retry." >&2
  exit 1
fi

load_production_database_url

echo "DANGER: this will replace the production Supabase/Postgres public schema." >&2
echo "Stop scripts/run-production.sh before continuing." >&2
echo "Backup: ${backup_dir}" >&2
echo "The restore is executed as one transaction; if any SQL fails, it rolls back." >&2
confirm_production_access "restore production from ${backup_dir}"

echo "Type exactly: ${PRODUCTION_RESTORE_CONFIRMATION}" >&2
read -r restore_confirmation

if [[ "${restore_confirmation}" != "${PRODUCTION_RESTORE_CONFIRMATION}" ]]; then
  echo "Confirmation did not match. Aborting." >&2
  exit 1
fi

echo "Type the backup path exactly: ${backup_dir}" >&2
read -r backup_confirmation

if [[ "${backup_confirmation}" != "${backup_dir}" ]]; then
  echo "Backup path confirmation did not match. Aborting." >&2
  exit 1
fi

{
  cat "${schema_file}"
  printf "\nset session_replication_role = replica;\n"
  cat "${data_file}"
  printf "\nset session_replication_role = origin;\n"
} | psql "${DATABASE_URL}" --single-transaction -v ON_ERROR_STOP=1

psql "${DATABASE_URL}" -v ON_ERROR_STOP=1 \
  -c "
    select
      (select count(*) from scrape_scopes) as scrape_scopes,
      (select count(*) from scrape_runs) as scrape_runs,
      (select count(*) from listings) as listings,
      (select count(*) from alert_events) as alert_events,
      (select count(*) from alert_delivery_attempts) as alert_delivery_attempts;
  "

echo "Production database restored from ${backup_dir}." >&2
