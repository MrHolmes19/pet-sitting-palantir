from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]
BACKUP_PRODUCTION_SCRIPT = REPO_ROOT / "scripts" / "backup-production.sh"
RESTORE_LOCAL_SCRIPT = REPO_ROOT / "scripts" / "restore-local-backup.sh"
RESTORE_PRODUCTION_SCRIPT = REPO_ROOT / "scripts" / "restore-prod-backup.sh"
BACKUPS_CONTEXT = REPO_ROOT / "docs" / "agent-context" / "backups.md"
COMPOSE_FILE = REPO_ROOT / "compose.yml"
GITIGNORE = REPO_ROOT / ".gitignore"


def test_backup_script_reads_production_and_writes_logical_package() -> None:
    script = BACKUP_PRODUCTION_SCRIPT.read_text()

    assert "production-postgres-env.sh" in script
    assert "load_production_database_url" in script
    assert "default_transaction_read_only=on" in script
    assert "PRODUCTION_POSTGRES_MAJOR=\"${PRODUCTION_POSTGRES_MAJOR:-17}\"" in script
    assert (
        'POSTGRES_TOOLS_IMAGE="${POSTGRES_TOOLS_IMAGE:-postgres:${PRODUCTION_POSTGRES_MAJOR}-alpine}"'
        in script
    )
    assert "local_postgres_tools_are_compatible" in script
    assert "docker run --rm" in script
    assert "--format=custom" in script
    assert "--schema=public" in script
    assert "--schema-only" in script
    assert "--data-only" in script
    assert "--disable-triggers" in script
    assert "schema.sql" in script
    assert "data.sql" in script
    assert "manifest.json" in script


def test_local_restore_script_never_loads_production_credentials() -> None:
    script = RESTORE_LOCAL_SCRIPT.read_text()

    assert "local-postgres-env.sh" in script
    assert "production-postgres-env.sh" not in script
    assert "load_production_database_url" not in script
    assert ".env.production" not in script
    assert "docker compose down --volumes --remove-orphans" in script
    assert "set session_replication_role = replica;" in script
    assert "set session_replication_role = origin;" in script
    assert "drop database if exists ${POSTGRES_DB} with (force)" in script
    assert "restore local" in script


def test_production_restore_is_guarded_and_transactional() -> None:
    script = RESTORE_PRODUCTION_SCRIPT.read_text()

    assert "production-postgres-env.sh" in script
    assert "load_production_database_url" in script
    assert "confirm_production_access" in script
    assert "Stop scripts/run-production.sh before continuing." in script
    assert "restore production" in script
    assert "Type the backup path exactly" in script
    assert "--single-transaction" in script
    assert "ON_ERROR_STOP=1" in script
    assert "set session_replication_role = replica;" in script
    assert "set session_replication_role = origin;" in script
    assert "Production database restored" in script


def test_backup_context_documents_production_restore_as_high_risk() -> None:
    context = BACKUPS_CONTEXT.read_text()

    assert "scripts/restore-prod-backup.sh" in context
    assert "high-risk recovery operation" in context
    assert "Stop the production runner" in context


def test_backup_directory_is_gitignored() -> None:
    assert ".backups/" in GITIGNORE.read_text().splitlines()


def test_local_postgres_matches_production_major_version() -> None:
    assert "image: postgres:17-alpine" in COMPOSE_FILE.read_text()
