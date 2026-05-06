"""Database connection helpers."""

from collections.abc import Iterator
from contextlib import contextmanager
from os import environ

from pet_sitting_palantir.config import load_settings

_env_database_url = environ.pop("DATABASE_URL", None)
try:
    import psycopg
    from psycopg import Connection
    from psycopg.rows import dict_row
finally:
    if _env_database_url is not None:
        environ["DATABASE_URL"] = _env_database_url


def database_url_from_env() -> str | None:
    """Return the configured application database URL, if present."""
    return load_settings().database_url


def connect_database(database_url: str | None = None) -> Connection:
    """Open a psycopg connection with dict row results."""
    resolved_url = database_url or database_url_from_env()
    if not resolved_url:
        raise ValueError("DATABASE_URL is required to connect to Postgres")

    return _connect_with_resolved_url(resolved_url)


@contextmanager
def database_connection(database_url: str | None = None) -> Iterator[Connection]:
    """Context manager that opens and closes a database connection."""
    with connect_database(database_url) as connection:
        yield connection


def _connect_with_resolved_url(database_url: str) -> Connection:
    env_database_url = environ.pop("DATABASE_URL", None)
    try:
        return psycopg.connect(database_url, row_factory=dict_row, prepare_threshold=None)
    finally:
        if env_database_url is not None:
            environ["DATABASE_URL"] = env_database_url
