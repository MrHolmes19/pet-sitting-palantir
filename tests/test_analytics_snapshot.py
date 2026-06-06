"""Tests for production analytics snapshot refresh."""

from dataclasses import asdict

import duckdb

from pet_sitting_palantir.analytics.snapshot import (
    database_url_from_env_file,
    refresh_production_snapshot,
)
from pet_sitting_palantir.analytics.synthetic import (
    DEFAULT_SEED,
    LISTING_COLUMNS,
    generate_synthetic_listings,
)


def test_refresh_production_snapshot_writes_duckdb_file(tmp_path) -> None:
    output_path = tmp_path / "pet_sitting.duckdb"
    rows = [
        {column: asdict(listing)[column] for column in LISTING_COLUMNS}
        for listing in generate_synthetic_listings(listing_count=3, seed=DEFAULT_SEED)
    ]

    result = refresh_production_snapshot(
        output_path=output_path,
        connect=lambda database_url: FakeConnection(rows),
    )

    assert result.output_path == output_path
    assert result.listing_count == 3

    with duckdb.connect(str(output_path), read_only=True) as connection:
        listing_count = connection.execute("select count(*) from listings").fetchone()[0]
        source = connection.execute("""
            select value
            from analytics_metadata
            where key = 'source'
        """).fetchone()[0]

    assert listing_count == 3
    assert source == "production"


def test_database_url_from_env_file_reads_explicit_file(tmp_path) -> None:
    env_file = tmp_path / ".env.production"
    env_file.write_text("DATABASE_URL=postgresql://example.test/prod\n", encoding="utf-8")

    assert database_url_from_env_file(env_file) == "postgresql://example.test/prod"


class FakeConnection:
    """Minimal fake psycopg connection for snapshot tests."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str) -> FakeCursor:
        assert "from listings" in query
        return FakeCursor(self.rows)


class FakeCursor:
    """Minimal fake psycopg cursor for snapshot tests."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows
