"""Database schema initialization helpers."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from psycopg import Connection

MIGRATIONS_DIR = Path(__file__).parents[3] / "supabase" / "migrations"
INITIAL_SCHEMA = MIGRATIONS_DIR / "20260503000100_initial_schema.sql"
ALERT_EVENTS_MIGRATION = MIGRATIONS_DIR / "20260526000100_alert_events_and_delivery_attempts.sql"
SEED_SQL = Path(__file__).parents[3] / "supabase" / "seed.sql"


@dataclass(frozen=True)
class DatabaseInitResult:
    """Summary of a database initialization run."""

    schema_applied: bool
    seed_applied: bool

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


def initialize_database(connection: Connection) -> DatabaseInitResult:
    """Apply pending schema migrations, then seed empty scope tables."""
    _ensure_migration_history_table(connection)
    _bootstrap_pre_history_schema(connection)
    schema_applied = _apply_pending_migrations(connection)

    seed_applied = _seed_required(connection)
    if seed_applied:
        _execute_sql_file(connection, SEED_SQL)

    _commit_if_transactional(connection)

    return DatabaseInitResult(
        schema_applied=schema_applied,
        seed_applied=seed_applied,
    )


def _schema_exists(connection: Connection) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select exists (
              select 1
              from information_schema.tables
              where table_schema = current_schema()
                and table_name = 'scrape_scopes'
            ) as schema_exists
            """
        )
        return cursor.fetchone()["schema_exists"]


def _execute_sql_file(connection: Connection, path: Path) -> None:
    with connection.cursor() as cursor:
        cursor.execute(path.read_text())


def _ensure_migration_history_table(connection: Connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            create table if not exists schema_migrations (
              filename text primary key,
              applied_at timestamptz not null default now()
            )
            """
        )


def _bootstrap_pre_history_schema(connection: Connection) -> None:
    if not _schema_exists(connection) or _applied_migration_names(connection):
        return

    _record_migration(connection, INITIAL_SCHEMA)
    if _table_exists(connection, "alert_events"):
        _record_migration(connection, ALERT_EVENTS_MIGRATION)


def _apply_pending_migrations(connection: Connection) -> bool:
    applied = _applied_migration_names(connection)
    applied_new_migration = False
    for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if migration.name in applied:
            continue
        _execute_sql_file(connection, migration)
        _record_migration(connection, migration)
        applied_new_migration = True

    return applied_new_migration


def _applied_migration_names(connection: Connection) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute("select filename from schema_migrations")
        return {row["filename"] for row in cursor.fetchall()}


def _record_migration(connection: Connection, migration: Path) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            insert into schema_migrations (filename)
            values (%s)
            on conflict (filename) do nothing
            """,
            (migration.name,),
        )


def _table_exists(connection: Connection, table_name: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select exists (
              select 1
              from information_schema.tables
              where table_schema = current_schema()
                and table_name = %s
            ) as table_exists
            """,
            (table_name,),
        )
        return cursor.fetchone()["table_exists"]


def _seed_required(connection: Connection) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("select count(*) as scope_count from scrape_scopes")
        return cursor.fetchone()["scope_count"] == 0


def _commit_if_transactional(connection: Connection) -> None:
    if not connection.autocommit:
        connection.commit()
