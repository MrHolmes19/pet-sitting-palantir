"""Tests for synthetic analytics data generation."""

import duckdb

from pet_sitting_palantir.analytics.synthetic import (
    DEFAULT_SEED,
    generate_synthetic_listings,
    write_demo_database,
)


def test_generate_synthetic_listings_is_deterministic() -> None:
    first_run = generate_synthetic_listings(listing_count=10, seed=DEFAULT_SEED)
    second_run = generate_synthetic_listings(listing_count=10, seed=DEFAULT_SEED)

    assert first_run == second_run
    assert len({listing.external_id for listing in first_run}) == 10


def test_write_demo_database_creates_expected_tables(tmp_path) -> None:
    output_path = tmp_path / "demo.duckdb"

    result = write_demo_database(output_path=output_path, listing_count=300, seed=DEFAULT_SEED)

    assert result.output_path == output_path
    assert result.listing_count == 300
    assert output_path.exists()

    with duckdb.connect(str(output_path), read_only=True) as connection:
        listing_count = connection.execute("select count(*) from listings").fetchone()[0]
        auckland_central_count = connection.execute("""
            select count(*)
            from listings
            where region = 'Auckland'
              and subregion = 'Auckland - Central'
        """).fetchone()[0]
        long_sit_count = connection.execute("""
            select count(*)
            from listings
            where duration_days >= 31
        """).fetchone()[0]
        source = connection.execute("""
            select value
            from analytics_metadata
            where key = 'source'
        """).fetchone()[0]

    assert listing_count == 300
    assert auckland_central_count > 0
    assert long_sit_count > 0
    assert source == "synthetic"

