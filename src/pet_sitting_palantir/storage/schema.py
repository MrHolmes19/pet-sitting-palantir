"""Database schema initialization helpers."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from psycopg import Connection

INITIAL_SCHEMA = Path(__file__).parents[3] / "supabase" / "migrations" / (
    "20260503000100_initial_schema.sql"
)
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
    """Apply the initial schema if missing, then seed empty scope tables."""
    schema_exists = _schema_exists(connection)
    if not schema_exists:
        _execute_sql_file(connection, INITIAL_SCHEMA)

    seed_applied = _seed_required(connection)
    if seed_applied:
        _execute_sql_file(connection, SEED_SQL)

    _commit_if_transactional(connection)

    return DatabaseInitResult(
        schema_applied=not schema_exists,
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


def _seed_required(connection: Connection) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("select count(*) as scope_count from scrape_scopes")
        return cursor.fetchone()["scope_count"] == 0


def _commit_if_transactional(connection: Connection) -> None:
    if not connection.autocommit:
        connection.commit()
