#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

# shellcheck source=scripts/local-postgres-env.sh
source "${SCRIPT_DIR}/local-postgres-env.sh"

LOCAL_RESTORE_CONFIRMATION="restore local"

usage() {
  echo "Usage: scripts/restore-local-backup.sh .backups/<timestamp>" >&2
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

require_docker_compose "restore a backup into local Postgres"

echo "WARNING: this will replace only the local Docker database." >&2
echo "It will remove the local Docker Postgres volume before restoring." >&2
echo "Production is not used by this restore command." >&2
echo "Local database: ${LOCAL_DATABASE_URL}" >&2
echo "Backup: ${backup_dir}" >&2
echo "Type exactly: ${LOCAL_RESTORE_CONFIRMATION}" >&2
read -r confirmation

if [[ "${confirmation}" != "${LOCAL_RESTORE_CONFIRMATION}" ]]; then
  echo "Confirmation did not match. Aborting." >&2
  exit 1
fi

docker compose down --volumes --remove-orphans
docker compose up -d "${POSTGRES_SERVICE}"
wait_for_local_postgres

docker compose exec -T "${POSTGRES_SERVICE}" \
  psql -U "${POSTGRES_USER}" -d postgres -v ON_ERROR_STOP=1 \
  -c "drop database if exists ${POSTGRES_DB} with (force)"

docker compose exec -T "${POSTGRES_SERVICE}" \
  psql -U "${POSTGRES_USER}" -d postgres -v ON_ERROR_STOP=1 \
  -c "create database ${POSTGRES_DB} owner ${POSTGRES_USER}"

docker compose exec -T "${POSTGRES_SERVICE}" \
  psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 \
  < "${schema_file}"

{
  printf "set session_replication_role = replica;\n"
  cat "${data_file}"
  printf "\nset session_replication_role = origin;\n"
} | docker compose exec -T "${POSTGRES_SERVICE}" \
  psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1

docker compose exec -T "${POSTGRES_SERVICE}" \
  psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 \
  -c "
    select
      (select count(*) from scrape_scopes) as scrape_scopes,
      (select count(*) from scrape_runs) as scrape_runs,
      (select count(*) from listings) as listings,
      (select count(*) from alert_events) as alert_events,
      (select count(*) from alert_delivery_attempts) as alert_delivery_attempts;
  "

echo "Local database restored from ${backup_dir}." >&2
