"""Refresh local analytics snapshots from production data sources."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from dotenv import dotenv_values
from psycopg import Connection

from pet_sitting_palantir.analytics.synthetic import CREATE_LISTINGS_SQL, LISTING_COLUMNS
from pet_sitting_palantir.storage.database import connect_database

DEFAULT_PRODUCTION_SNAPSHOT_PATH = Path(".analytics/pet_sitting.duckdb")
DEFAULT_PRODUCTION_ENV_FILE = Path(".env.production")

ConnectDatabase = Callable[[str | None], Connection]


@dataclass(frozen=True)
class ProductionRefreshResult:
    """Summary of a refreshed production analytics snapshot."""

    output_path: Path
    listing_count: int
    refreshed_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "output_path": str(self.output_path),
            "listing_count": self.listing_count,
            "refreshed_at": self.refreshed_at,
        }


def refresh_production_snapshot(
    *,
    output_path: Path = DEFAULT_PRODUCTION_SNAPSHOT_PATH,
    database_url: str | None = None,
    connect: ConnectDatabase = connect_database,
) -> ProductionRefreshResult:
    """Refresh a local DuckDB analytics snapshot from production PostgreSQL."""
    listings = _read_production_listings(database_url=database_url, connect=connect)
    _write_snapshot_database(output_path=output_path, listings=listings, source="production")

    return ProductionRefreshResult(
        output_path=output_path,
        listing_count=len(listings),
        refreshed_at=datetime.now(UTC),
    )


def database_url_from_env_file(env_file: Path = DEFAULT_PRODUCTION_ENV_FILE) -> str:
    """Read a database URL from an explicit env file without loading repo .env."""
    if not env_file.exists():
        raise FileNotFoundError(
            f"Missing {env_file}. Copy .env.production.example and set DATABASE_URL."
        )

    database_url = dotenv_values(env_file).get("DATABASE_URL")
    if not database_url:
        raise ValueError(f"DATABASE_URL is missing in {env_file}")
    return database_url


def _read_production_listings(
    *,
    database_url: str | None,
    connect: ConnectDatabase,
) -> pd.DataFrame:
    columns_sql = ", ".join(LISTING_COLUMNS)
    with connect(database_url) as connection:
        rows = connection.execute(f"""
            select {columns_sql}
            from listings
            order by id
        """).fetchall()

    return pd.DataFrame(rows, columns=LISTING_COLUMNS)


def _write_snapshot_database(*, output_path: Path, listings: pd.DataFrame, source: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    frame = listings.reindex(columns=LISTING_COLUMNS)
    with duckdb.connect(str(output_path)) as connection:
        connection.execute(CREATE_LISTINGS_SQL)
        connection.register("snapshot_listings", frame)
        connection.execute(f"""
            insert into listings ({", ".join(LISTING_COLUMNS)})
            select {", ".join(LISTING_COLUMNS)}
            from snapshot_listings
        """)
        connection.execute("""
            create table analytics_metadata (
              key text primary key,
              value text
            )
        """)
        connection.executemany(
            "insert into analytics_metadata values (?, ?)",
            [
                ("source", source),
                ("listing_count", str(len(frame))),
                ("refreshed_at", datetime.now(UTC).isoformat()),
            ],
        )
