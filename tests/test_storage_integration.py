import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg import sql
from psycopg.rows import dict_row

from pet_sitting_palantir.domain.models import Listing
from pet_sitting_palantir.storage import (
    ScrapeRunCounts,
    close_scrape_run,
    create_scrape_run,
    read_enabled_scrape_scopes,
    upsert_listing,
    upsert_listings,
)

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None

MIGRATIONS_DIR = Path(__file__).parents[1] / "supabase" / "migrations"
SEED_FILE = Path(__file__).parents[1] / "supabase" / "seed.sql"


def _database_url() -> str | None:
    return os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")


@pytest.fixture
def postgres_connection() -> Iterator:
    if psycopg is None:
        pytest.skip("psycopg is not installed")

    database_url = _database_url()
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL or DATABASE_URL to run this integration test")

    schema_name = f"test_schema_{uuid4().hex}"
    migration_sql = "\n".join(path.read_text() for path in sorted(MIGRATIONS_DIR.glob("*.sql")))
    seed_sql = SEED_FILE.read_text()

    with psycopg.connect(database_url, autocommit=True, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("create schema {}").format(sql.Identifier(schema_name)))
            cursor.execute(
                sql.SQL("set search_path to {}, public").format(sql.Identifier(schema_name))
            )
            cursor.execute(migration_sql)
            cursor.execute(seed_sql)

        try:
            yield connection
        finally:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("drop schema {} cascade").format(sql.Identifier(schema_name))
                )


@pytest.mark.integration
def test_reads_enabled_scrape_scopes(postgres_connection) -> None:
    scopes = read_enabled_scrape_scopes(postgres_connection)

    assert [scope.name for scope in scopes] == [
        "all_nz",
        "auckland_central",
        "auckland_region",
        "north_island",
    ]
    assert scopes[1].site_filter == {
        "state": "north-island",
        "region": "auckland",
        "subregion": "auckland-central",
    }


@pytest.mark.integration
def test_creates_and_closes_successful_scrape_run(postgres_connection) -> None:
    scope = next(
        scope
        for scope in read_enabled_scrape_scopes(postgres_connection)
        if scope.name == "auckland_central"
    )

    run_id = create_scrape_run(
        postgres_connection,
        scope_id=scope.id,
        scope_name=scope.name,
        search_url="https://example.test/search",
    )
    close_scrape_run(
        postgres_connection,
        run_id=run_id,
        status="success",
        counts=ScrapeRunCounts(
            pages_fetched=2,
            listings_seen=3,
            new_listings=1,
            changed_listings=1,
        ),
    )

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select
              scrape_runs.status,
              scrape_runs.finished_at,
              scrape_runs.pages_fetched,
              scrape_runs.listings_seen,
              scrape_runs.new_listings,
              scrape_runs.changed_listings,
              scrape_scopes.last_attempt_at,
              scrape_scopes.last_success_at
            from scrape_runs
            join scrape_scopes on scrape_scopes.id = scrape_runs.scope_id
            where scrape_runs.id = %s
            """,
            (run_id,),
        )
        row = cursor.fetchone()

    assert row["status"] == "success"
    assert row["finished_at"] is not None
    assert row["pages_fetched"] == 2
    assert row["listings_seen"] == 3
    assert row["new_listings"] == 1
    assert row["changed_listings"] == 1
    assert row["last_attempt_at"] is not None
    assert row["last_success_at"] is not None


@pytest.mark.integration
def test_upserts_listing_by_external_id(postgres_connection) -> None:
    scope = read_enabled_scrape_scopes(postgres_connection)[0]
    run_id = create_scrape_run(
        postgres_connection,
        scope_id=scope.id,
        scope_name=scope.name,
    )

    listing = _listing()
    first_result = upsert_listing(postgres_connection, listing=listing, run_id=run_id)
    same_result = upsert_listing(postgres_connection, listing=listing, run_id=run_id)
    changed_result = upsert_listing(
        postgres_connection,
        listing=_listing(content_hash="hash-v2", title="Updated title"),
        run_id=run_id,
    )

    assert first_result.created is True
    assert first_result.changed is False
    assert same_result.listing_id == first_result.listing_id
    assert same_result.created is False
    assert same_result.changed is False
    assert changed_result.listing_id == first_result.listing_id
    assert changed_result.created is False
    assert changed_result.changed is True

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select
              content_hash,
              title,
              status,
              missing_count,
              first_seen_run_id,
              last_seen_run_id
            from listings
            where external_id = %s
            """,
            (listing.external_id,),
        )
        row = cursor.fetchone()

    assert row["content_hash"] == "hash-v2"
    assert row["title"] == "Updated title"
    assert row["status"] == "active"
    assert row["missing_count"] == 0
    assert row["first_seen_run_id"] == run_id
    assert row["last_seen_run_id"] == run_id


@pytest.mark.integration
def test_upsert_listings_returns_run_counts(postgres_connection) -> None:
    scope = read_enabled_scrape_scopes(postgres_connection)[0]
    run_id = create_scrape_run(
        postgres_connection,
        scope_id=scope.id,
        scope_name=scope.name,
    )

    upsert_listing(postgres_connection, listing=_listing(external_id="614587"), run_id=run_id)

    summary = upsert_listings(
        postgres_connection,
        listings=(
            _listing(external_id="614587", content_hash="changed"),
            _listing(external_id="614588", content_hash="new"),
        ),
        run_id=run_id,
    )

    assert summary.listings_seen == 2
    assert summary.new_listings == 1
    assert summary.changed_listings == 1


@pytest.mark.integration
def test_upsert_listing_rejects_incomplete_listing(postgres_connection) -> None:
    scope = read_enabled_scrape_scopes(postgres_connection)[0]
    run_id = create_scrape_run(
        postgres_connection,
        scope_id=scope.id,
        scope_name=scope.name,
    )

    with pytest.raises(ValueError, match="content_hash"):
        upsert_listing(
            postgres_connection,
            listing=_listing(content_hash=""),
            run_id=run_id,
        )

    with pytest.raises(ValueError, match="url"):
        upsert_listing(
            postgres_connection,
            listing=_listing(url=None),
            run_id=run_id,
        )


def _listing(
    *,
    external_id: str = "614587",
    content_hash: str = "hash-v1",
    title: str = "Stonefields Auckland - Auckland - Auckland - Central",
    url: str | None = "https://example.test/listing/614587",
) -> Listing:
    return Listing(
        external_id=external_id,
        content_hash=content_hash,
        island="North Island",
        region="Auckland",
        subregion="Auckland - Central",
        city="Stonefields",
        duration_days=6,
        start_date=date(2026, 5, 5),
        end_date=date(2026, 5, 11),
        house_type="Duplex",
        total_animals=1,
        dogs_count=1,
        starts_soon=True,
        reply_rating_score=10,
        listing_tag="Goofy Dog in Stonefields",
        title=title,
        intro="Looking for someone to look after one dog.",
        url=url,
    )
