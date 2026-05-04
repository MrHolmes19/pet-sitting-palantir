"""Storage functions for scrape scopes."""

from collections.abc import Mapping
from typing import Any

from psycopg import Connection

from pet_sitting_palantir.storage.models import ScrapeScope


def read_enabled_scrape_scopes(connection: Connection) -> list[ScrapeScope]:
    """Read all enabled scrape scopes in stable order."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select
              id,
              name,
              enabled,
              interval_minutes,
              missing_threshold_runs,
              site_filter,
              last_attempt_at,
              last_success_at
            from scrape_scopes
            where enabled = true
            order by name
            """
        )
        return [_scope_from_row(row) for row in cursor.fetchall()]


def read_enabled_scrape_scope(
    connection: Connection,
    *,
    name: str,
) -> ScrapeScope | None:
    """Read one enabled scrape scope by name."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select
              id,
              name,
              enabled,
              interval_minutes,
              missing_threshold_runs,
              site_filter,
              last_attempt_at,
              last_success_at
            from scrape_scopes
            where enabled = true
              and name = %s
            """,
            (name,),
        )
        row = cursor.fetchone()
        return _scope_from_row(row) if row else None


def _scope_from_row(row: Mapping[str, Any]) -> ScrapeScope:
    return ScrapeScope(
        id=row["id"],
        name=row["name"],
        enabled=row["enabled"],
        interval_minutes=row["interval_minutes"],
        missing_threshold_runs=row["missing_threshold_runs"],
        site_filter=row["site_filter"],
        last_attempt_at=row["last_attempt_at"],
        last_success_at=row["last_success_at"],
    )
