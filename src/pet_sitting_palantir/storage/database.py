"""Database connection helpers."""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from pet_sitting_palantir.config import load_settings


def database_url_from_env() -> str | None:
    """Return the configured application database URL, if present."""
    return load_settings().database_url


def connect_database(database_url: str | None = None) -> Connection:
    """Open a psycopg connection with dict row results."""
    resolved_url = database_url or database_url_from_env()
    if not resolved_url:
        raise ValueError("DATABASE_URL is required to connect to Postgres")

    return psycopg.connect(resolved_url, row_factory=dict_row)


@contextmanager
def database_connection(database_url: str | None = None) -> Iterator[Connection]:
    """Context manager that opens and closes a database connection."""
    with connect_database(database_url) as connection:
        yield connection
