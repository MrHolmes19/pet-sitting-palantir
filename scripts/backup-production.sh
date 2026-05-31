#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

# shellcheck source=scripts/production-postgres-env.sh
source "${SCRIPT_DIR}/production-postgres-env.sh"

BACKUP_ROOT="${BACKUP_ROOT:-.backups}"
BACKUP_FORMAT_VERSION="1"
PRODUCTION_POSTGRES_MAJOR="${PRODUCTION_POSTGRES_MAJOR:-17}"
POSTGRES_TOOLS_IMAGE="${POSTGRES_TOOLS_IMAGE:-postgres:${PRODUCTION_POSTGRES_MAJOR}-alpine}"
USE_DOCKER_POSTGRES_TOOLS=0

major_version() {
  local version_output="$1"

  echo "${version_output}" | sed -E 's/.* ([0-9]+)(\.[0-9]+)?.*/\1/'
}

command_major_version() {
  local command_name="$1"

  major_version "$("${command_name}" --version)"
}

local_postgres_tools_are_compatible() {
  if ! command -v pg_dump >/dev/null 2>&1; then
    return 1
  fi

  if ! command -v pg_restore >/dev/null 2>&1; then
    return 1
  fi

  [[ "$(command_major_version pg_dump)" -ge "${PRODUCTION_POSTGRES_MAJOR}" ]] &&
    [[ "$(command_major_version pg_restore)" -ge "${PRODUCTION_POSTGRES_MAJOR}" ]]
}

require_docker_for_postgres_tools() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "Local PostgreSQL client tools are older than production PostgreSQL ${PRODUCTION_POSTGRES_MAJOR}." >&2
    echo "Install PostgreSQL ${PRODUCTION_POSTGRES_MAJOR} client tools or Docker, then retry." >&2
    exit 1
  fi

  if ! docker info >/dev/null 2>&1; then
    echo "Local PostgreSQL client tools are older than production PostgreSQL ${PRODUCTION_POSTGRES_MAJOR}." >&2
    echo "Docker is installed but unavailable. Start Docker, then retry." >&2
    exit 1
  fi
}

select_postgres_tools() {
  if local_postgres_tools_are_compatible; then
    return 0
  fi

  require_docker_for_postgres_tools
  USE_DOCKER_POSTGRES_TOOLS=1
  echo "Using ${POSTGRES_TOOLS_IMAGE} for PostgreSQL ${PRODUCTION_POSTGRES_MAJOR} backup tools." >&2
}

run_pg_dump() {
  local target_file="$1"
  local target_dir
  local target_name

  if [[ "${USE_DOCKER_POSTGRES_TOOLS}" == "1" ]]; then
    target_dir="$(cd "$(dirname "${target_file}")" && pwd)"
    target_name="$(basename "${target_file}")"
    export DATABASE_URL

    docker run --rm \
      -e DATABASE_URL \
      -e "PGOPTIONS=${PGOPTIONS:-} -c default_transaction_read_only=on" \
      -e "TARGET_NAME=${target_name}" \
      -v "${target_dir}:/backup" \
      "${POSTGRES_TOOLS_IMAGE}" \
      sh -c '
        pg_dump \
          --format=custom \
          --schema=public \
          --no-owner \
          --no-privileges \
          --file="/backup/${TARGET_NAME}" \
          "${DATABASE_URL}"
      '
    return 0
  fi

  PGOPTIONS="${PGOPTIONS:-} -c default_transaction_read_only=on" \
    pg_dump \
      --format=custom \
      --schema=public \
      --no-owner \
      --no-privileges \
      --file="${target_file}" \
      "${DATABASE_URL}"
}

run_pg_restore() {
  local output_file="$1"
  local archive_path="$2"
  local output_dir
  local output_name
  local archive_name

  shift 2

  if [[ "${USE_DOCKER_POSTGRES_TOOLS}" == "1" ]]; then
    output_dir="$(cd "$(dirname "${output_file}")" && pwd)"
    output_name="$(basename "${output_file}")"
    archive_name="$(basename "${archive_path}")"

    docker run --rm \
      -v "${output_dir}:/backup" \
      "${POSTGRES_TOOLS_IMAGE}" \
      pg_restore \
        "$@" \
        --no-owner \
        --no-privileges \
        --file="/backup/${output_name}" \
        "/backup/${archive_name}"
    return 0
  fi

  pg_restore \
    "$@" \
    --no-owner \
    --no-privileges \
    --file="${output_file}" \
    "${archive_path}"
}

load_production_database_url
select_postgres_tools

timestamp="$(date -u +%Y-%m-%dT%H%M%SZ)"
backup_dir="${BACKUP_ROOT}/${timestamp}"
archive_file="${backup_dir}/snapshot.dump"
schema_file="${backup_dir}/schema.sql"
data_file="${backup_dir}/data.sql"
manifest_file="${backup_dir}/manifest.json"

mkdir -p "${BACKUP_ROOT}"
if [[ -e "${backup_dir}" ]]; then
  echo "Backup directory already exists: ${backup_dir}" >&2
  exit 1
fi
mkdir "${backup_dir}"

cleanup_archive() {
  rm -f "${archive_file}"
}
trap cleanup_archive EXIT

echo "Creating read-only production backup from ${PRODUCTION_ENV_FILE}." >&2
run_pg_dump "${archive_file}"

run_pg_restore \
  "${schema_file}" \
  "${archive_file}" \
  --schema-only \
  --clean \
  --if-exists

run_pg_restore \
  "${data_file}" \
  "${archive_file}" \
  --data-only \
  --disable-triggers

cat >"${manifest_file}" <<EOF
{
  "backup_format_version": "${BACKUP_FORMAT_VERSION}",
  "created_at_utc": "${timestamp}",
  "source": "production",
  "database_schema": "public",
  "files": {
    "schema": "schema.sql",
    "data": "data.sql"
  }
}
EOF

rm -f "${archive_file}"
trap - EXIT

echo "Backup written to ${backup_dir}" >&2
