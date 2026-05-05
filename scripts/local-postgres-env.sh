#!/usr/bin/env bash

LOCAL_DATABASE_URL="postgresql://palantir:palantir@localhost:54321/pet_sitting_palantir"
POSTGRES_SERVICE="postgres"
POSTGRES_USER="palantir"
POSTGRES_DB="pet_sitting_palantir"
MAX_READY_CHECKS=30

require_docker_compose() {
  local purpose="${1:-use local Postgres}"

  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required to ${purpose}." >&2
    echo "Install Docker or enable Docker Desktop WSL integration, then retry." >&2
    exit 1
  fi

  if ! docker --version >/dev/null 2>&1; then
    echo "Docker is installed but is not available in this shell." >&2
    echo "Start Docker or enable Docker Desktop WSL integration, then retry." >&2
    exit 1
  fi

  if ! docker info >/dev/null 2>&1; then
    echo "Docker is installed but this shell cannot access the Docker engine." >&2
    echo "Start Docker or refresh Docker Desktop WSL integration, then retry." >&2
    exit 1
  fi

  if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose is required to ${purpose}." >&2
    exit 1
  fi
}

wait_for_local_postgres() {
  for attempt in $(seq 1 "${MAX_READY_CHECKS}"); do
    if docker compose exec -T "${POSTGRES_SERVICE}" \
      pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
      return 0
    fi

    if [[ "${attempt}" == "${MAX_READY_CHECKS}" ]]; then
      echo "Postgres did not become ready after ${MAX_READY_CHECKS} checks." >&2
      exit 1
    fi

    sleep 1
  done
}
