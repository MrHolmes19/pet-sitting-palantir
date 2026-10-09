import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg import sql
from psycopg.rows import dict_row

from pet_sitting_palantir.alerts import (
    AlertDelivery,
    AlertFilterDefinition,
    AlertQuietHours,
    ProviderDeliveryResult,
)
from pet_sitting_palantir.domain.models import Listing
from pet_sitting_palantir.kiwihousesitters.client import (
    KiwiHouseSittersDeadlineExceeded,
    KiwiHouseSittersWAFChallengeError,
)
from pet_sitting_palantir.kiwihousesitters.scraper import ScrapeResult
from pet_sitting_palantir.storage import (
    ScrapeRunCounts,
    close_scrape_run,
    create_scrape_run,
    listing_record_from_scraped_listing,
    mark_expired_by_date,
    read_due_scrape_scopes,
    read_enabled_scrape_scope,
    read_enabled_scrape_scopes,
    read_latest_waf_challenge_at,
    upsert_listing,
    upsert_listings,
)
from pet_sitting_palantir.workflows.deliver_alerts import deliver_due_alerts_with_connection
from pet_sitting_palantir.workflows.healthcheck import read_healthcheck_summary
from pet_sitting_palantir.workflows.run_due_scopes import run_due_scrape_scopes_with_connection
from pet_sitting_palantir.workflows.scrape_and_store import scrape_and_store_scope_with_connection

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
        "north_shore_city",
    ]
    assert scopes[1].site_filter == {
        "state": "north-island",
        "region": "auckland",
        "subregion": "auckland-central",
    }


@pytest.mark.integration
def test_reads_one_enabled_scrape_scope_by_name(postgres_connection) -> None:
    scope = read_enabled_scrape_scope(postgres_connection, name="auckland_central")

    assert scope is not None
    assert scope.name == "auckland_central"
    assert scope.site_filter == {
        "state": "north-island",
        "region": "auckland",
        "subregion": "auckland-central",
    }


@pytest.mark.integration
def test_reads_due_scrape_scopes_by_cadence(postgres_connection) -> None:
    assert [scope.name for scope in read_due_scrape_scopes(postgres_connection)] == [
        "auckland_central",
        "north_shore_city",
        "auckland_region",
        "north_island",
        "all_nz",
    ]

    with postgres_connection.cursor() as cursor:
        cursor.execute("update scrape_scopes set last_success_at = now()")

    assert read_due_scrape_scopes(postgres_connection) == []

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            update scrape_scopes
            set last_success_at = now() - interval '6 minutes'
            where name = 'auckland_central'
            """
        )
        cursor.execute(
            """
            update scrape_scopes
            set last_success_at = now() - interval '8 minutes 30 seconds'
            where name = 'north_shore_city'
            """
        )

    assert [scope.name for scope in read_due_scrape_scopes(postgres_connection)] == [
        "auckland_central"
    ]

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            update scrape_scopes
            set last_success_at = now() - interval '9 minutes 30 seconds'
            where name = 'north_shore_city'
            """
        )

    assert [scope.name for scope in read_due_scrape_scopes(postgres_connection)] == [
        "auckland_central",
        "north_shore_city",
    ]


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
def test_reads_latest_waf_challenge_from_failed_run(postgres_connection) -> None:
    assert read_latest_waf_challenge_at(postgres_connection) is None
    scope = read_enabled_scrape_scope(postgres_connection, name="auckland_central")
    assert scope is not None
    run_id = create_scrape_run(
        postgres_connection,
        scope_id=scope.id,
        scope_name=scope.name,
    )
    close_scrape_run(
        postgres_connection,
        run_id=run_id,
        status="failed",
        error_message="kiwihousesitters_waf_challenge; Unexpected status code: 202",
    )

    assert read_latest_waf_challenge_at(postgres_connection) is not None


@pytest.mark.integration
def test_upserts_listing_by_external_id(postgres_connection) -> None:
    scope = read_enabled_scrape_scopes(postgres_connection)[0]
    run_id = create_scrape_run(
        postgres_connection,
        scope_id=scope.id,
        scope_name=scope.name,
    )

    listing = listing_record_from_scraped_listing(_listing())
    first_result = upsert_listing(postgres_connection, listing=listing, run_id=run_id)
    same_result = upsert_listing(postgres_connection, listing=listing, run_id=run_id)
    changed_result = upsert_listing(
        postgres_connection,
        listing=listing_record_from_scraped_listing(
            _listing(content_hash="hash-v2", title="Updated title")
        ),
        run_id=run_id,
    )

    assert first_result.created is True
    assert first_result.changed is False
    assert first_result.previous_status is None
    assert first_result.appearance_sequence == 1
    assert first_result.confirmed_reappearance is False
    assert same_result.listing_id == first_result.listing_id
    assert same_result.created is False
    assert same_result.changed is False
    assert same_result.previous_status == "active"
    assert same_result.appearance_sequence == 1
    assert changed_result.listing_id == first_result.listing_id
    assert changed_result.created is False
    assert changed_result.changed is True
    assert changed_result.previous_content_hash == "hash-v1"
    assert changed_result.appearance_sequence == 1

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select
              content_hash,
              title,
              status,
              missing_count,
              appearance_sequence,
              first_seen_run_id,
              last_seen_run_id,
              first_seen_context
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
    assert row["appearance_sequence"] == 1
    assert row["first_seen_run_id"] == run_id
    assert row["last_seen_run_id"] == run_id
    assert row["first_seen_context"] == "observed"


@pytest.mark.integration
def test_upsert_listings_returns_run_counts(postgres_connection) -> None:
    scope = read_enabled_scrape_scopes(postgres_connection)[0]
    run_id = create_scrape_run(
        postgres_connection,
        scope_id=scope.id,
        scope_name=scope.name,
    )

    upsert_listing(
        postgres_connection,
        listing=listing_record_from_scraped_listing(_listing(external_id="614587")),
        run_id=run_id,
    )

    summary = upsert_listings(
        postgres_connection,
        listings=(
            listing_record_from_scraped_listing(
                _listing(external_id="614587", content_hash="changed")
            ),
            listing_record_from_scraped_listing(_listing(external_id="614588", content_hash="new")),
        ),
        run_id=run_id,
    )

    assert summary.listings_seen == 2
    assert summary.new_listings == 1
    assert summary.changed_listings == 1
    assert [result.external_id for result in summary.results] == ["614587", "614588"]


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
            listing=listing_record_from_scraped_listing(_listing(content_hash="")),
            run_id=run_id,
        )

    with pytest.raises(ValueError, match="url"):
        upsert_listing(
            postgres_connection,
            listing=listing_record_from_scraped_listing(_listing(url=None)),
            run_id=run_id,
        )


@pytest.mark.integration
def test_alert_events_and_delivery_attempts_enforce_event_and_success_deduplication(
    postgres_connection,
) -> None:
    run_id = create_scrape_run(
        postgres_connection,
        scope_id=None,
        scope_name="manual_alert_event",
    )
    listing_result = upsert_listing(
        postgres_connection,
        listing=listing_record_from_scraped_listing(_listing(external_id="alert-record")),
        run_id=run_id,
    )

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            insert into alert_filters (name, site_filter, local_filter)
            values ('sample filter', '{}'::jsonb, '{}'::jsonb)
            returning id
            """
        )
        filter_id = cursor.fetchone()["id"]
        cursor.execute(
            """
            insert into alert_events (
              listing_id,
              filter_id,
              detected_run_id,
              event_type,
              appearance_sequence,
              alert_fingerprint,
              listing_content_hash,
              target_channels
            )
            values (%s, %s, %s, 'first_match', 1, 'fingerprint-v1', 'hash-v1', %s)
            returning id
            """,
            (listing_result.listing_id, filter_id, run_id, ["telegram"]),
        )
        alert_event_id = cursor.fetchone()["id"]

    with pytest.raises(psycopg.errors.UniqueViolation):
        with postgres_connection.cursor() as cursor:
            cursor.execute(
                """
                insert into alert_events (
                  listing_id,
                  filter_id,
                  detected_run_id,
                  event_type,
                  appearance_sequence,
                  alert_fingerprint,
                  listing_content_hash,
                  target_channels
                )
                values (%s, %s, %s, 'material_change', 1, 'fingerprint-v1', 'hash-v1', %s)
                """,
                (listing_result.listing_id, filter_id, run_id, ["telegram"]),
            )

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            insert into alert_delivery_attempts (
              alert_event_id,
              channel,
              status,
              error_message
            )
            values (%s, 'telegram', 'failed', 'offline')
            """,
            (alert_event_id,),
        )
        cursor.execute(
            """
            insert into alert_delivery_attempts (alert_event_id, channel, status)
            values (%s, 'telegram', 'sent')
            """,
            (alert_event_id,),
        )

    with pytest.raises(psycopg.errors.UniqueViolation):
        with postgres_connection.cursor() as cursor:
            cursor.execute(
                """
                insert into alert_delivery_attempts (alert_event_id, channel, status)
                values (%s, 'telegram', 'sent')
                """,
                (alert_event_id,),
            )


@pytest.mark.integration
def test_scrape_and_store_scope_persists_scraper_result(postgres_connection) -> None:
    def fake_scraper(site_filter, *, max_pages):
        assert site_filter == {
            "state": "north-island",
            "region": "auckland",
            "subregion": "auckland-central",
        }
        assert max_pages is None
        return ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(_listing(),),
        )

    result = scrape_and_store_scope_with_connection(
        postgres_connection,
        scope_name="auckland_central",
        max_pages=None,
        scraper=fake_scraper,
    )

    assert result.status == "success"
    assert result.scope_name == "auckland_central"
    assert result.pages_fetched == 1
    assert result.listings_seen == 1
    assert result.new_listings == 1
    assert result.changed_listings == 0
    assert result.missing_marked == 0

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select
              scrape_runs.status,
              scrape_runs.pages_fetched,
              scrape_runs.listings_seen,
              scrape_runs.new_listings,
              scrape_runs.changed_listings,
              scrape_runs.missing_marked,
              scrape_scopes.last_attempt_at,
              scrape_scopes.last_success_at
            from scrape_runs
            join scrape_scopes on scrape_scopes.id = scrape_runs.scope_id
            where scrape_runs.id = %s
            """,
            (result.run_id,),
        )
        run = cursor.fetchone()

        cursor.execute(
            """
            select external_id, title, region, subregion, starts_soon, status, first_seen_context
            from listings
            where external_id = %s
            """,
            ("614587",),
        )
        listing = cursor.fetchone()

    assert run["status"] == "success"
    assert run["pages_fetched"] == 1
    assert run["listings_seen"] == 1
    assert run["new_listings"] == 1
    assert run["changed_listings"] == 0
    assert run["missing_marked"] == 0
    assert run["last_attempt_at"] is not None
    assert run["last_success_at"] is not None
    assert listing == {
        "external_id": "614587",
        "title": "Stonefields Auckland - Auckland - Auckland - Central",
        "region": "Auckland",
        "subregion": "Auckland - Central",
        "starts_soon": True,
        "status": "active",
        "first_seen_context": "baseline",
    }


@pytest.mark.integration
def test_scrape_and_store_scope_rejects_bounded_persistence_before_scraping(
    postgres_connection,
) -> None:
    scraped = False

    def fake_scraper(site_filter, *, max_pages):
        nonlocal scraped
        scraped = True
        return ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(_listing(),),
        )

    with pytest.raises(ValueError, match="require --max-pages all"):
        scrape_and_store_scope_with_connection(
            postgres_connection,
            scope_name="auckland_central",
            max_pages=1,
            scraper=fake_scraper,
        )

    assert scraped is False


@pytest.mark.integration
def test_successful_scrape_synchronizes_filter_and_creates_vendor_neutral_event(
    postgres_connection,
) -> None:
    definition = _matching_alert_filter()

    def fake_scraper(site_filter, *, max_pages):
        return ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(_matching_listing(),),
        )

    result = scrape_and_store_scope_with_connection(
        postgres_connection,
        scope_name="auckland_central",
        scraper=fake_scraper,
        alert_filters=(definition,),
    )

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select
              alert_filters.name,
              alert_filters.enabled,
              alert_events.event_type,
              alert_events.target_channels,
              alert_events.listing_content_hash,
              count(alert_delivery_attempts.id) as delivery_attempts
            from alert_filters
            join alert_events on alert_events.filter_id = alert_filters.id
            left join alert_delivery_attempts
              on alert_delivery_attempts.alert_event_id = alert_events.id
            where alert_events.detected_run_id = %s
            group by alert_filters.name, alert_filters.enabled, alert_events.id
            """,
            (result.run_id,),
        )
        event = cursor.fetchone()

    assert event == {
        "name": definition.name,
        "enabled": True,
        "event_type": "first_match",
        "target_channels": ["telegram", "email"],
        "listing_content_hash": "matching-v1",
        "delivery_attempts": 0,
    }
    assert result.alert_events[0].filter_name == definition.name
    assert result.alert_events[0].listing_external_id == "matching-listing"


@pytest.mark.integration
def test_due_telegram_event_is_sent_once_and_records_message(postgres_connection) -> None:
    definition = replace(
        _matching_alert_filter(),
        delivery=replace(_matching_alert_filter().delivery, channels=("telegram",)),
    )

    scrape_and_store_scope_with_connection(
        postgres_connection,
        scope_name="auckland_central",
        scraper=lambda site_filter, *, max_pages: ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(_matching_listing(),),
        ),
        alert_filters=(definition,),
    )
    provider = _FakeProvider((ProviderDeliveryResult(sent=True, provider_message_id="42"),))

    first = deliver_due_alerts_with_connection(
        postgres_connection,
        providers={"telegram": provider},
        current_time=datetime.now(UTC) + timedelta(days=1),
    )
    second = deliver_due_alerts_with_connection(
        postgres_connection,
        providers={"telegram": provider},
        current_time=datetime.now(UTC) + timedelta(days=1),
    )

    with postgres_connection.cursor() as cursor:
        cursor.execute("select status, message, provider_message_id from alert_delivery_attempts")
        attempt = cursor.fetchone()

    assert first.sent == 1
    assert second.deliveries_due == 0
    assert len(provider.messages) == 1
    assert provider.messages[0].startswith("workflow event filter\n\nSTONEFIELDS, AUCKLAND")
    assert "STONEFIELDS, AUCKLAND" in provider.messages[0]
    assert "DATES: 1 Aug 2026 - 22 Aug 2026" in provider.messages[0]
    assert "PETS: 1 dog" in provider.messages[0]
    assert attempt["status"] == "sent"
    assert attempt["message"] == provider.messages[0]
    assert attempt["provider_message_id"] == "42"


@pytest.mark.integration
def test_failed_telegram_event_retries_without_recreating_alert_event(postgres_connection) -> None:
    definition = replace(
        _matching_alert_filter(),
        delivery=replace(_matching_alert_filter().delivery, channels=("telegram",)),
    )
    scrape_and_store_scope_with_connection(
        postgres_connection,
        scope_name="auckland_central",
        scraper=lambda site_filter, *, max_pages: ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(_matching_listing(),),
        ),
        alert_filters=(definition,),
    )
    provider = _FakeProvider(
        (
            ProviderDeliveryResult(sent=False, error_message="Telegram request failed: Timeout"),
            ProviderDeliveryResult(sent=True, provider_message_id="43"),
        )
    )

    failed = deliver_due_alerts_with_connection(
        postgres_connection,
        providers={"telegram": provider},
        current_time=datetime.now(UTC) + timedelta(days=1),
    )
    sent = deliver_due_alerts_with_connection(
        postgres_connection,
        providers={"telegram": provider},
        current_time=datetime.now(UTC) + timedelta(days=1),
    )

    with postgres_connection.cursor() as cursor:
        cursor.execute("select status from alert_delivery_attempts order by id")
        statuses = [attempt["status"] for attempt in cursor.fetchall()]
        cursor.execute("select count(*) as events from alert_events")
        event_count = cursor.fetchone()["events"]

    assert failed.failed == 1
    assert sent.sent == 1
    assert statuses == ["failed", "sent"]
    assert event_count == 1


@pytest.mark.integration
def test_future_alert_delivery_is_not_sent(postgres_connection) -> None:
    definition = replace(
        _matching_alert_filter(),
        delivery=replace(_matching_alert_filter().delivery, channels=("telegram",)),
    )
    scrape_and_store_scope_with_connection(
        postgres_connection,
        scope_name="auckland_central",
        scraper=lambda site_filter, *, max_pages: ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(_matching_listing(),),
        ),
        alert_filters=(definition,),
    )
    with postgres_connection.cursor() as cursor:
        cursor.execute("update alert_events set deliver_after = now() + interval '1 day'")
    provider = _FakeProvider((ProviderDeliveryResult(sent=True),))

    result = deliver_due_alerts_with_connection(
        postgres_connection,
        providers={"telegram": provider},
        current_time=datetime.now(UTC),
    )

    assert result.deliveries_due == 0
    assert provider.messages == []


@pytest.mark.integration
def test_successful_scrapes_only_create_new_event_for_material_fingerprint_change(
    postgres_connection,
) -> None:
    definition = _matching_alert_filter()

    def scrape(listing):
        return lambda site_filter, *, max_pages: ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(listing,),
        )

    scrape_and_store_scope_with_connection(
        postgres_connection,
        scope_name="auckland_central",
        scraper=scrape(_matching_listing()),
        alert_filters=(definition,),
    )
    scrape_and_store_scope_with_connection(
        postgres_connection,
        scope_name="auckland_central",
        scraper=scrape(
            replace(_matching_listing(), content_hash="display-only", title="New title")
        ),
        alert_filters=(definition,),
    )
    scrape_and_store_scope_with_connection(
        postgres_connection,
        scope_name="auckland_central",
        scraper=scrape(
            replace(
                _matching_listing(),
                content_hash="new-date",
                start_date=date(2026, 8, 2),
            )
        ),
        alert_filters=(definition,),
    )

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select event_type
            from alert_events
            order by id
            """
        )
        event_types = [row["event_type"] for row in cursor.fetchall()]

    assert event_types == ["first_match", "material_change"]


@pytest.mark.integration
def test_confirmed_reappearance_with_change_creates_reappearance_event(
    postgres_connection,
) -> None:
    definition = _matching_alert_filter()

    def scrape(listing):
        return lambda site_filter, *, max_pages: ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(listing,),
        )

    scrape_and_store_scope_with_connection(
        postgres_connection,
        scope_name="auckland_central",
        scraper=scrape(_matching_listing()),
        alert_filters=(definition,),
    )
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            update listings
            set status = 'missing_confirmed',
                missing_count = 6,
                missing_since = now(),
                closed_at = now()
            where external_id = 'matching-listing'
            """
        )
    scrape_and_store_scope_with_connection(
        postgres_connection,
        scope_name="auckland_central",
        scraper=scrape(
            replace(
                _matching_listing(),
                content_hash="returned-changed",
                end_date=date(2026, 8, 23),
            )
        ),
        alert_filters=(definition,),
    )

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select event_type, appearance_sequence
            from alert_events
            order by id
            """
        )
        events = cursor.fetchall()

    assert events == [
        {"event_type": "first_match", "appearance_sequence": 1},
        {"event_type": "confirmed_reappearance", "appearance_sequence": 2},
    ]


@pytest.mark.integration
def test_broad_successful_scrape_does_not_alert_for_listing_outside_filter_area(
    postgres_connection,
) -> None:
    definition = _matching_alert_filter()

    def fake_scraper(site_filter, *, max_pages):
        return ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(replace(_matching_listing(), subregion="North Shore City"),),
        )

    scrape_and_store_scope_with_connection(
        postgres_connection,
        scope_name="all_nz",
        scraper=fake_scraper,
        alert_filters=(definition,),
    )

    with postgres_connection.cursor() as cursor:
        cursor.execute("select count(*) as event_count from alert_events")
        event_count = cursor.fetchone()["event_count"]

    assert event_count == 0


@pytest.mark.integration
def test_successful_scrape_marks_only_missing_listings_covered_by_scope(
    postgres_connection,
) -> None:
    seed_run_id = create_scrape_run(
        postgres_connection,
        scope_id=None,
        scope_name="manual_seed",
    )
    upsert_listing(
        postgres_connection,
        listing=listing_record_from_scraped_listing(
            _listing(external_id="covered-missing", title="Covered missing")
        ),
        run_id=seed_run_id,
    )
    upsert_listing(
        postgres_connection,
        listing=listing_record_from_scraped_listing(
            _listing(
                external_id="outside-scope",
                title="Outside scope",
                subregion="North Shore City",
            )
        ),
        run_id=seed_run_id,
    )
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            update scrape_scopes
            set last_success_at = now()
            where name = 'auckland_central'
            """
        )

    def fake_scraper(site_filter, *, max_pages):
        return ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(_listing(external_id="seen-now", title="Seen now"),),
        )

    result = scrape_and_store_scope_with_connection(
        postgres_connection,
        scope_name="auckland_central",
        scraper=fake_scraper,
    )

    assert result.status == "success"
    assert result.missing_marked == 1

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select external_id, status, missing_count, missing_since, closed_at
            from listings
            where external_id in ('covered-missing', 'outside-scope', 'seen-now')
            order by external_id
            """
        )
        rows = {row["external_id"]: row for row in cursor.fetchall()}

    assert rows["covered-missing"]["status"] == "missing_once"
    assert rows["covered-missing"]["missing_count"] == 1
    assert rows["covered-missing"]["missing_since"] is not None
    assert rows["covered-missing"]["closed_at"] is None
    assert rows["outside-scope"]["status"] == "active"
    assert rows["outside-scope"]["missing_count"] == 0
    assert rows["seen-now"]["status"] == "active"
    assert rows["seen-now"]["missing_count"] == 0


@pytest.mark.integration
def test_first_successful_scope_run_does_not_mark_missing(
    postgres_connection,
) -> None:
    seed_run_id = create_scrape_run(
        postgres_connection,
        scope_id=None,
        scope_name="manual_seed",
    )
    upsert_listing(
        postgres_connection,
        listing=listing_record_from_scraped_listing(
            _listing(external_id="existing-covered", title="Existing covered")
        ),
        run_id=seed_run_id,
    )

    def fake_scraper(site_filter, *, max_pages):
        return ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(_listing(external_id="first-run-seen", title="First run seen"),),
        )

    result = scrape_and_store_scope_with_connection(
        postgres_connection,
        scope_name="auckland_central",
        scraper=fake_scraper,
    )

    assert result.status == "success"
    assert result.missing_marked == 0

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select external_id, status, missing_count, missing_since, closed_at
            from listings
            where external_id in ('existing-covered', 'first-run-seen')
            order by external_id
            """
        )
        rows = {row["external_id"]: row for row in cursor.fetchall()}

    assert rows["existing-covered"]["status"] == "active"
    assert rows["existing-covered"]["missing_count"] == 0
    assert rows["existing-covered"]["missing_since"] is None
    assert rows["existing-covered"]["closed_at"] is None
    assert rows["first-run-seen"]["status"] == "active"
    assert rows["first-run-seen"]["missing_count"] == 0


@pytest.mark.integration
def test_missing_listing_reaching_threshold_becomes_missing_confirmed(
    postgres_connection,
) -> None:
    seed_run_id = create_scrape_run(
        postgres_connection,
        scope_id=None,
        scope_name="manual_seed",
    )
    upsert_listing(
        postgres_connection,
        listing=listing_record_from_scraped_listing(
            _listing(external_id="threshold-missing", title="Threshold missing")
        ),
        run_id=seed_run_id,
    )
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            update listings
            set status = 'missing_once',
                missing_count = 5,
                missing_since = now()
            where external_id = 'threshold-missing'
            """
        )
        cursor.execute(
            """
            update scrape_scopes
            set last_success_at = now()
            where name = 'auckland_central'
            """
        )

    def fake_scraper(site_filter, *, max_pages):
        return ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(_listing(external_id="different-seen", title="Different seen"),),
        )

    result = scrape_and_store_scope_with_connection(
        postgres_connection,
        scope_name="auckland_central",
        scraper=fake_scraper,
    )

    assert result.missing_marked == 1

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select status, missing_count, closed_at
            from listings
            where external_id = 'threshold-missing'
            """
        )
        row = cursor.fetchone()

    assert row["status"] == "missing_confirmed"
    assert row["missing_count"] == 6
    assert row["closed_at"] is not None


@pytest.mark.integration
def test_upsert_listing_reports_confirmed_reappearance_and_increments_sequence(
    postgres_connection,
) -> None:
    run_id = create_scrape_run(
        postgres_connection,
        scope_id=None,
        scope_name="manual_seed",
    )
    listing = listing_record_from_scraped_listing(_listing(external_id="reappearing"))
    upsert_listing(postgres_connection, listing=listing, run_id=run_id)
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            update listings
            set status = 'missing_confirmed',
                missing_count = 6,
                missing_since = now(),
                closed_at = now()
            where external_id = 'reappearing'
            """
        )

    reappeared = upsert_listing(
        postgres_connection,
        listing=listing_record_from_scraped_listing(
            _listing(external_id="reappearing", content_hash="hash-returned")
        ),
        run_id=run_id,
    )

    assert reappeared.previous_status == "missing_confirmed"
    assert reappeared.previous_content_hash == "hash-v1"
    assert reappeared.changed is True
    assert reappeared.confirmed_reappearance is True
    assert reappeared.appearance_sequence == 2

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select status, missing_count, closed_at, appearance_sequence
            from listings
            where external_id = 'reappearing'
            """
        )
        row = cursor.fetchone()

    assert row == {
        "status": "active",
        "missing_count": 0,
        "closed_at": None,
        "appearance_sequence": 2,
    }


@pytest.mark.integration
def test_upsert_listing_does_not_increment_sequence_after_missing_once(
    postgres_connection,
) -> None:
    run_id = create_scrape_run(
        postgres_connection,
        scope_id=None,
        scope_name="manual_seed",
    )
    listing = listing_record_from_scraped_listing(_listing(external_id="transiently-missing"))
    upsert_listing(postgres_connection, listing=listing, run_id=run_id)
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            update listings
            set status = 'missing_once',
                missing_count = 1,
                missing_since = now()
            where external_id = 'transiently-missing'
            """
        )

    observed = upsert_listing(postgres_connection, listing=listing, run_id=run_id)

    assert observed.previous_status == "missing_once"
    assert observed.confirmed_reappearance is False
    assert observed.appearance_sequence == 1


@pytest.mark.integration
def test_zero_listing_scrape_is_suspicious_and_does_not_mark_missing(
    postgres_connection,
) -> None:
    seed_run_id = create_scrape_run(
        postgres_connection,
        scope_id=None,
        scope_name="manual_seed",
    )
    upsert_listing(
        postgres_connection,
        listing=listing_record_from_scraped_listing(
            _listing(external_id="not-missing-on-suspicious")
        ),
        run_id=seed_run_id,
    )

    def empty_scraper(site_filter, *, max_pages):
        return ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(),
        )

    result = scrape_and_store_scope_with_connection(
        postgres_connection,
        scope_name="auckland_central",
        scraper=empty_scraper,
    )

    assert result.status == "suspicious"
    assert result.listings_seen == 0
    assert result.missing_marked == 0

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select scrape_runs.status, scrape_runs.missing_marked, scrape_scopes.last_success_at
            from scrape_runs
            join scrape_scopes on scrape_scopes.id = scrape_runs.scope_id
            where scrape_runs.id = %s
            """,
            (result.run_id,),
        )
        run = cursor.fetchone()

        cursor.execute(
            """
            select status, missing_count
            from listings
            where external_id = 'not-missing-on-suspicious'
            """
        )
        listing = cursor.fetchone()

    assert run["status"] == "suspicious"
    assert run["missing_marked"] == 0
    assert run["last_success_at"] is None
    assert listing["status"] == "active"
    assert listing["missing_count"] == 0


@pytest.mark.integration
def test_mark_expired_by_date_closes_past_end_date_listing(postgres_connection) -> None:
    seed_run_id = create_scrape_run(
        postgres_connection,
        scope_id=None,
        scope_name="manual_seed",
    )
    upsert_listing(
        postgres_connection,
        listing=listing_record_from_scraped_listing(
            _listing(
                external_id="expired-listing",
                start_date=date(2025, 1, 1),
                end_date=date(2025, 1, 2),
            )
        ),
        run_id=seed_run_id,
    )

    assert mark_expired_by_date(postgres_connection) == 1

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select status, closed_at
            from listings
            where external_id = 'expired-listing'
            """
        )
        row = cursor.fetchone()

    assert row["status"] == "expired_by_date"
    assert row["closed_at"] is not None


@pytest.mark.integration
def test_run_due_scrape_scopes_runs_only_due_scopes(postgres_connection) -> None:
    with postgres_connection.cursor() as cursor:
        cursor.execute("update scrape_scopes set last_success_at = now()")
        cursor.execute(
            """
            update scrape_scopes
            set last_success_at = now() - interval '6 minutes'
            where name = 'auckland_central'
            """
        )

    def fake_scraper(site_filter, *, max_pages):
        assert site_filter == {
            "state": "north-island",
            "region": "auckland",
            "subregion": "auckland-central",
        }
        assert max_pages is None
        return ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(_listing(external_id="due-runner-listing"),),
        )

    result = run_due_scrape_scopes_with_connection(
        postgres_connection,
        max_pages=None,
        scraper=fake_scraper,
    )

    assert result.status == "success"
    assert result.scopes_due == 1
    assert result.scopes_succeeded == 1
    assert result.scopes_failed == 0
    assert result.results[0].scope_name == "auckland_central"

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select scrape_runs.scope_name, scrape_runs.status, listings.external_id
            from scrape_runs
            join listings on listings.last_seen_run_id = scrape_runs.id
            where listings.external_id = 'due-runner-listing'
            """
        )
        row = cursor.fetchone()

    assert row == {
        "scope_name": "auckland_central",
        "status": "success",
        "external_id": "due-runner-listing",
    }


@pytest.mark.integration
def test_waf_challenge_keeps_priority_running_while_broad_work_rests(
    postgres_connection,
) -> None:
    scope = read_enabled_scrape_scope(postgres_connection, name="auckland_central")
    assert scope is not None
    run_id = create_scrape_run(
        postgres_connection,
        scope_id=scope.id,
        scope_name=scope.name,
    )
    close_scrape_run(
        postgres_connection,
        run_id=run_id,
        status="failed",
        error_message="kiwihousesitters_waf_challenge; Unexpected status code: 202",
    )

    with postgres_connection.cursor() as cursor:
        cursor.execute("update scrape_scopes set last_success_at = now()")
        cursor.execute(
            """
            update scrape_scopes
            set last_success_at = case
              when name = 'all_nz' then now() - interval '2 days'
              when name = 'auckland_central' then now() - interval '6 minutes'
              else now() - interval '11 minutes'
            end
            where name in ('all_nz', 'auckland_central', 'north_shore_city')
            """
        )

    priority_filters = []

    def priority_scraper(site_filter, *, max_pages):
        priority_filters.append(site_filter)
        return ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(_listing(external_id="golden-lane-listing"),),
        )

    instant = datetime.now(tz=UTC)
    priority_during_local_cooldown = run_due_scrape_scopes_with_connection(
        postgres_connection,
        max_pages=None,
        scraper=priority_scraper,
        current_time=instant + timedelta(minutes=5),
        phase="priority",
    )
    broad = run_due_scrape_scopes_with_connection(
        postgres_connection,
        max_pages=None,
        scraper=lambda site_filter, *, max_pages: pytest.fail(
            "WAF cooldown should prevent broad site requests"
        ),
        current_time=instant + timedelta(minutes=5),
        phase="broad",
    )
    priority_after_local_cooldown = run_due_scrape_scopes_with_connection(
        postgres_connection,
        max_pages=None,
        scraper=priority_scraper,
        current_time=instant + timedelta(minutes=15),
        phase="priority",
    )

    assert priority_during_local_cooldown.status == "success"
    assert priority_after_local_cooldown.status == "success"
    assert priority_filters == [
        {
            "state": "north-island",
            "region": "auckland",
            "subregion": "north-shore-city",
        },
        {
            "state": "north-island",
            "region": "auckland",
            "subregion": "auckland-central",
        }
    ]
    assert broad.status == "waf_cooldown"
    assert broad.scopes_due == 0


@pytest.mark.integration
def test_run_due_scrape_scopes_starts_broad_campaign_without_advancing_parent_freshness(
    postgres_connection,
) -> None:
    seen_filters = []

    def fake_scraper(site_filter, *, max_pages):
        seen_filters.append(site_filter)
        return ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(_listing(external_id="fresh-baseline-listing"),),
        )

    result = run_due_scrape_scopes_with_connection(
        postgres_connection,
        max_pages=None,
        scraper=fake_scraper,
    )

    assert result.status == "success"
    assert result.scopes_due == 2
    assert result.scopes_succeeded == 2
    assert [stored.scope_name for stored in result.results] == [
        "auckland_region",
        "all_nz",
    ]
    assert seen_filters == [
        {"state": "north-island", "region": "auckland"},
        {},
    ]
    assert len(result.campaign_steps) == 1
    assert result.campaign_steps[0].scope_name == "all_nz"
    assert result.campaign_steps[0].status == "completed"
    assert result.campaign_steps[0].completed_leaves == 1
    assert result.campaign_steps[0].total_leaves == 1

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select
              name,
              last_attempt_at is not null as attempted,
              last_success_at is not null as fresh
            from scrape_scopes
            order by name
            """
        )
        scope_state = cursor.fetchall()

    assert scope_state == [
        {"name": "all_nz", "attempted": True, "fresh": True},
        {"name": "auckland_central", "attempted": False, "fresh": True},
        {"name": "auckland_region", "attempted": True, "fresh": True},
        {"name": "north_island", "attempted": False, "fresh": False},
        {"name": "north_shore_city", "attempted": False, "fresh": True},
    ]
    assert {scope.name for scope in read_due_scrape_scopes(postgres_connection)} == {
        "north_island"
    }


@pytest.mark.integration
def test_broad_completion_does_not_advance_golden_scope_freshness(
    postgres_connection,
) -> None:
    golden_freshness = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            update scrape_scopes
            set last_attempt_at = %s, last_success_at = %s
            """,
            (golden_freshness, golden_freshness),
        )
        cursor.execute(
            """
            update scrape_scopes
            set last_success_at = %s
            where name = 'all_nz'
            """,
            (golden_freshness - timedelta(days=2),),
        )

    result = run_due_scrape_scopes_with_connection(
        postgres_connection,
        max_pages=None,
        scraper=lambda site_filter, *, max_pages: ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(_listing(external_id="broad-only-listing"),),
        ),
        current_time=golden_freshness + timedelta(days=2),
        phase="broad",
    )

    assert result.status == "success"
    assert result.results[0].scope_name == "all_nz"
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select name, last_attempt_at, last_success_at
            from scrape_scopes
            where name in ('auckland_central', 'auckland_region', 'north_shore_city')
            order by name
            """
        )
        golden_scopes = cursor.fetchall()

    assert golden_scopes == [
        {
            "name": "auckland_central",
            "last_attempt_at": golden_freshness,
            "last_success_at": golden_freshness,
        },
        {
            "name": "auckland_region",
            "last_attempt_at": golden_freshness,
            "last_success_at": golden_freshness,
        },
        {
            "name": "north_shore_city",
            "last_attempt_at": golden_freshness,
            "last_success_at": golden_freshness,
        },
    ]


@pytest.mark.integration
def test_broad_campaign_merges_regions_into_original_parent_scope(postgres_connection) -> None:
    with postgres_connection.cursor() as cursor:
        cursor.execute("update scrape_scopes set last_success_at = now()")
        cursor.execute(
            """
            update scrape_scopes
            set last_success_at = now() - interval '2 days'
            where name = 'all_nz'
            """
        )

    seen_regions = []

    def fake_scraper(site_filter, *, max_pages):
        region = site_filter["region"]
        seen_regions.append(region)
        return ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(
                _listing(
                    external_id=f"campaign-{region}",
                    content_hash=f"hash-{region}",
                    url=f"https://example.test/listing/{region}",
                ),
            ),
        )

    started_at = datetime.now(tz=UTC)
    _record_historical_waf(
        postgres_connection,
        scope_name="all_nz",
        challenged_at=started_at - timedelta(days=2),
    )
    result = None
    for step_number in range(15):
        result = run_due_scrape_scopes_with_connection(
            postgres_connection,
            max_pages=None,
            scraper=fake_scraper,
            current_time=started_at + timedelta(minutes=10 * step_number),
        )

    assert result is not None
    assert len(seen_regions) == 15
    assert len(set(seen_regions)) == 15
    assert result.campaign_steps[0].status == "completed"
    assert result.results[0].scope_name == "all_nz"
    assert result.results[0].listings_seen == 15

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select status, completed_at
            from broad_scrape_campaigns
            where scope_name = 'all_nz'
            """
        )
        campaign = cursor.fetchone()
        cursor.execute(
            """
            select scope_name, status, listings_seen
            from scrape_runs
            order by id desc
            limit 1
            """
        )
        parent_run = cursor.fetchone()
        cursor.execute(
            """
            select count(*) as populated_leaves
            from broad_scrape_campaign_leaves
            where jsonb_array_length(listings) > 0
            """
        )
        populated_leaves = cursor.fetchone()["populated_leaves"]

    assert campaign["status"] == "completed"
    assert campaign["completed_at"] is not None
    assert parent_run == {
        "scope_name": "all_nz",
        "status": "success",
        "listings_seen": 15,
    }
    assert populated_leaves == 0


@pytest.mark.integration
def test_overlapping_broad_campaigns_partition_missing_evidence_by_island(
    postgres_connection,
) -> None:
    with postgres_connection.cursor() as cursor:
        cursor.execute("update scrape_scopes set last_success_at = now()")
        cursor.execute(
            """
            update scrape_scopes
            set last_success_at = now() - interval '2 days'
            where name in ('all_nz', 'north_island')
            """
        )

    seed_run_id = create_scrape_run(
        postgres_connection,
        scope_id=None,
        scope_name="missing-authority-seed",
    )
    for listing in (
        _listing(
            external_id="absent-northland",
            island="North Island",
            region="Northland",
            subregion="Whangarei",
            city="Whangarei",
        ),
        _listing(
            external_id="absent-canterbury",
            island="South Island",
            region="Canterbury",
            subregion="Christchurch",
            city="Christchurch",
        ),
    ):
        upsert_listing(
            postgres_connection,
            listing=listing_record_from_scraped_listing(listing),
            run_id=seed_run_id,
        )

    started_at = datetime.now(tz=UTC)
    for scope_name in ("all_nz", "north_island"):
        _record_historical_waf(
            postgres_connection,
            scope_name=scope_name,
            challenged_at=started_at - timedelta(days=2),
        )

    completed_scope_names = []

    def fake_scraper(site_filter, *, max_pages):
        region = site_filter["region"]
        return ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(_listing(external_id=f"partition-observed-{region}"),),
        )

    for step_number in range(25):
        result = run_due_scrape_scopes_with_connection(
            postgres_connection,
            max_pages=None,
            scraper=fake_scraper,
            current_time=started_at + timedelta(minutes=10 * step_number),
            phase="broad",
        )
        completed_scope_names.extend(stored.scope_name for stored in result.results)

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select external_id, status, missing_count
            from listings
            where external_id in ('absent-northland', 'absent-canterbury')
            order by external_id
            """
        )
        missing_rows = cursor.fetchall()

    assert completed_scope_names == ["all_nz", "north_island"]
    assert missing_rows == [
        {
            "external_id": "absent-canterbury",
            "status": "missing_once",
            "missing_count": 1,
        },
        {
            "external_id": "absent-northland",
            "status": "missing_once",
            "missing_count": 1,
        },
    ]


@pytest.mark.integration
def test_broad_campaign_does_not_overwrite_or_mark_newer_observations_missing(
    postgres_connection,
) -> None:
    with postgres_connection.cursor() as cursor:
        cursor.execute("update scrape_scopes set last_success_at = now()")
        cursor.execute(
            """
            update scrape_scopes
            set last_success_at = now() - interval '2 days'
            where name = 'all_nz'
            """
        )

    def fake_scraper(site_filter, *, max_pages):
        region = site_filter["region"]
        return ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(
                _listing(
                    external_id=(
                        "campaign-shared-listing" if region == "auckland" else f"leaf-{region}"
                    ),
                    content_hash=f"campaign-{region}",
                    url=f"https://example.test/listing/{region}",
                ),
            ),
        )

    started_at = datetime.now(tz=UTC)
    _record_historical_waf(
        postgres_connection,
        scope_name="all_nz",
        challenged_at=started_at - timedelta(days=2),
    )
    run_due_scrape_scopes_with_connection(
        postgres_connection,
        max_pages=None,
        scraper=fake_scraper,
        current_time=started_at,
    )

    newer_observation_at = started_at + timedelta(minutes=5)
    seed_run_id = create_scrape_run(
        postgres_connection,
        scope_id=None,
        scope_name="newer_auckland_observation",
    )
    for listing in (
        _listing(
            external_id="campaign-shared-listing",
            content_hash="newer-content",
        ),
        _listing(
            external_id="appeared-after-auckland-leaf",
            content_hash="new-listing-content",
        ),
    ):
        upsert_listing(
            postgres_connection,
            listing=listing_record_from_scraped_listing(listing),
            run_id=seed_run_id,
            observed_at=newer_observation_at,
        )

    for step_number in range(1, 15):
        result = run_due_scrape_scopes_with_connection(
            postgres_connection,
            max_pages=None,
            scraper=fake_scraper,
            current_time=started_at + timedelta(minutes=10 * step_number),
        )

    assert result.campaign_steps[0].status == "completed"
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select external_id, content_hash, status, missing_count, last_seen_at
            from listings
            where external_id in (
              'campaign-shared-listing',
              'appeared-after-auckland-leaf'
            )
            order by external_id
            """
        )
        rows = cursor.fetchall()

    assert rows == [
        {
            "external_id": "appeared-after-auckland-leaf",
            "content_hash": "new-listing-content",
            "status": "active",
            "missing_count": 0,
            "last_seen_at": newer_observation_at,
        },
        {
            "external_id": "campaign-shared-listing",
            "content_hash": "newer-content",
            "status": "active",
            "missing_count": 0,
            "last_seen_at": newer_observation_at,
        },
    ]


@pytest.mark.integration
def test_broad_campaign_pauses_on_waf_and_keeps_completed_progress(
    postgres_connection,
) -> None:
    with postgres_connection.cursor() as cursor:
        cursor.execute("update scrape_scopes set last_success_at = now()")
        cursor.execute(
            """
            update scrape_scopes
            set last_success_at = now() - interval '2 days'
            where name = 'all_nz'
            """
        )

    def challenged_scraper(site_filter, *, max_pages):
        raise KiwiHouseSittersWAFChallengeError(
            "kiwihousesitters_waf_challenge; Unexpected status code: 202"
        )

    instant = datetime.now(tz=UTC)
    result = run_due_scrape_scopes_with_connection(
        postgres_connection,
        max_pages=None,
        scraper=challenged_scraper,
        current_time=instant,
    )

    assert result.status == "failed"
    assert result.campaign_steps[0].status == "waf_paused"
    assert result.campaign_steps[0].leaf_key == "__full__"
    assert result.campaign_steps[0].waf_challenge_count == 1
    assert result.campaign_steps[0].next_attempt_at == instant + timedelta(hours=24)

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select status, waf_challenge_count, next_attempt_at
            from broad_scrape_campaigns
            where scope_name = 'all_nz'
            """
        )
        campaign = cursor.fetchone()
        cursor.execute(
            """
            select leaf_key, status, attempt_count
            from broad_scrape_campaign_leaves
            where campaign_id = (
              select id from broad_scrape_campaigns where scope_name = 'all_nz'
            )
              and leaf_key in ('__full__', 'auckland')
            order by leaf_key
            """
        )
        leaves = cursor.fetchall()
        cursor.execute(
            """
            select error_message
            from scrape_runs
            where status = 'failed'
            order by id desc
            limit 1
            """
        )
        failed_attempt = cursor.fetchone()

    assert campaign == {
        "status": "paused",
        "waf_challenge_count": 1,
        "next_attempt_at": instant + timedelta(hours=24),
    }
    assert leaves == [
        {"leaf_key": "__full__", "status": "split", "attempt_count": 1},
        {"leaf_key": "auckland", "status": "pending", "attempt_count": 0},
    ]
    assert failed_attempt == {"error_message": "kiwihousesitters_waf_challenge"}
    healthcheck = read_healthcheck_summary(
        postgres_connection,
        current_time=instant + timedelta(minutes=1),
    )
    assert healthcheck.failed_runs == 1

    deferred = run_due_scrape_scopes_with_connection(
        postgres_connection,
        max_pages=None,
        scraper=lambda site_filter, *, max_pages: pytest.fail(
            "paused campaign should not request the site"
        ),
        current_time=instant + timedelta(hours=1),
    )
    assert deferred.status == "waf_cooldown"
    assert deferred.campaign_steps == ()

    retried_filters = []

    def recovered_scraper(site_filter, *, max_pages):
        retried_filters.append(site_filter)
        return ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(_listing(external_id="recovered-auckland-leaf"),),
        )

    resumed = run_due_scrape_scopes_with_connection(
        postgres_connection,
        max_pages=None,
        scraper=recovered_scraper,
        current_time=instant + timedelta(hours=24, minutes=1),
    )
    assert resumed.campaign_steps[0].status == "in_progress"
    assert resumed.campaign_steps[0].leaf_key == "auckland"
    assert resumed.campaign_steps[0].completed_leaves == 1
    assert retried_filters == [{"state": "north-island", "region": "auckland"}]


@pytest.mark.integration
def test_direct_broad_deadline_splits_into_regional_fallback(postgres_connection) -> None:
    with postgres_connection.cursor() as cursor:
        cursor.execute("update scrape_scopes set last_success_at = now()")
        cursor.execute(
            """
            update scrape_scopes
            set last_success_at = now() - interval '2 days'
            where name = 'all_nz'
            """
        )

    instant = datetime.now(tz=UTC)
    result = run_due_scrape_scopes_with_connection(
        postgres_connection,
        max_pages=None,
        scraper=lambda site_filter, *, max_pages: (_ for _ in ()).throw(
            KiwiHouseSittersDeadlineExceeded("background deadline reached")
        ),
        current_time=instant,
        phase="broad",
    )

    assert result.status == "failed"
    assert result.campaign_steps[0].status == "split_paused"
    assert result.campaign_steps[0].leaf_key == "__full__"
    assert result.campaign_steps[0].completed_leaves == 0
    assert result.campaign_steps[0].total_leaves == 15
    assert result.campaign_steps[0].next_attempt_at == instant + timedelta(minutes=10)

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select leaf_key, status
            from broad_scrape_campaign_leaves
            where campaign_id = %s
            order by ordinal
            """,
            (result.campaign_steps[0].campaign_id,),
        )
        leaves = cursor.fetchall()

    assert leaves[0] == {"leaf_key": "__full__", "status": "split"}
    assert len(leaves) == 16
    assert all(leaf["status"] == "pending" for leaf in leaves[1:])


@pytest.mark.integration
def test_run_due_scrape_scopes_skips_due_subregions_when_region_is_due(
    postgres_connection,
) -> None:
    with postgres_connection.cursor() as cursor:
        cursor.execute("update scrape_scopes set last_success_at = now()")
        cursor.execute(
            """
            update scrape_scopes
            set last_success_at = now() - interval '6 minutes'
            where name = 'auckland_central'
            """
        )
        cursor.execute(
            """
            update scrape_scopes
            set last_success_at = now() - interval '61 minutes'
            where name = 'auckland_region'
            """
        )

    seen_filters = []

    def fake_scraper(site_filter, *, max_pages):
        seen_filters.append(site_filter)
        return ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(_listing(external_id="region-due-listing"),),
        )

    result = run_due_scrape_scopes_with_connection(
        postgres_connection,
        max_pages=None,
        scraper=fake_scraper,
    )

    assert result.status == "success"
    assert result.scopes_due == 1
    assert result.scopes_succeeded == 1
    assert result.results[0].scope_name == "auckland_region"
    assert seen_filters == [{"state": "north-island", "region": "auckland"}]


@pytest.mark.integration
def test_run_due_scrape_scopes_catches_up_region_without_rescheduling_island(
    postgres_connection,
) -> None:
    with postgres_connection.cursor() as cursor:
        cursor.execute("update scrape_scopes set last_success_at = now()")
        cursor.execute(
            """
            update scrape_scopes
            set last_success_at = now() - interval '62 minutes'
            where name in ('auckland_central', 'north_shore_city', 'auckland_region')
            """
        )
        cursor.execute(
            """
            update scrape_scopes
            set last_success_at = now() - interval '11 hours'
            where name = 'north_island'
            returning last_success_at
            """
        )
        island_last_success_at = cursor.fetchone()["last_success_at"]

    def fake_scraper(site_filter, *, max_pages):
        assert site_filter == {"state": "north-island", "region": "auckland"}
        return ScrapeResult(
            search_url="https://example.test/search",
            pages_fetched=1,
            listings=(_listing(external_id="outage-catch-up-listing"),),
        )

    result = run_due_scrape_scopes_with_connection(
        postgres_connection,
        max_pages=None,
        scraper=fake_scraper,
    )

    assert result.status == "success"
    assert [stored_result.scope_name for stored_result in result.results] == ["auckland_region"]

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "select last_success_at from scrape_scopes where name = 'north_island'"
        )
        current_island_last_success_at = cursor.fetchone()["last_success_at"]

    assert current_island_last_success_at == island_last_success_at


@pytest.mark.integration
def test_scrape_and_store_scope_closes_failed_run(postgres_connection) -> None:
    def failing_scraper(site_filter, *, max_pages):
        raise RuntimeError("scrape failed")

    with pytest.raises(RuntimeError, match="scrape failed"):
        scrape_and_store_scope_with_connection(
            postgres_connection,
            scope_name="auckland_central",
            scraper=failing_scraper,
        )

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select status, error_message
            from scrape_runs
            order by id desc
            limit 1
            """
        )
        run = cursor.fetchone()

    assert run["status"] == "failed"
    assert run["error_message"] == "scrape failed"


@pytest.mark.integration
def test_scrape_and_store_scope_sanitizes_waf_failure(postgres_connection) -> None:
    def challenged_scraper(site_filter, *, max_pages):
        raise KiwiHouseSittersWAFChallengeError(
            "kiwihousesitters_waf_challenge; body_snippet=window.gokuProps secret-token"
        )

    with pytest.raises(KiwiHouseSittersWAFChallengeError):
        scrape_and_store_scope_with_connection(
            postgres_connection,
            scope_name="auckland_central",
            scraper=challenged_scraper,
        )

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select status, error_message
            from scrape_runs
            order by id desc
            limit 1
            """
        )
        run = cursor.fetchone()

    assert run == {
        "status": "failed",
        "error_message": "kiwihousesitters_waf_challenge",
    }


@pytest.mark.integration
def test_scrape_and_store_scope_closes_interrupted_run(postgres_connection) -> None:
    def interrupted_scraper(site_filter, *, max_pages):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        scrape_and_store_scope_with_connection(
            postgres_connection,
            scope_name="auckland_central",
            scraper=interrupted_scraper,
        )

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            """
            select status, error_message
            from scrape_runs
            order by id desc
            limit 1
            """
        )
        run = cursor.fetchone()

    assert run["status"] == "failed"
    assert run["error_message"] == "KeyboardInterrupt"


def _record_historical_waf(
    connection,
    *,
    scope_name: str,
    challenged_at: datetime,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            insert into scrape_runs (
              scope_id,
              scope_name,
              started_at,
              finished_at,
              status,
              error_message
            )
            select
              id,
              name,
              %s,
              %s,
              'failed',
              'kiwihousesitters_waf_challenge'
            from scrape_scopes
            where name = %s
            """,
            (challenged_at, challenged_at, scope_name),
        )


def _listing(
    *,
    external_id: str = "614587",
    content_hash: str = "hash-v1",
    title: str = "Stonefields Auckland - Auckland - Auckland - Central",
    island: str = "North Island",
    region: str = "Auckland",
    subregion: str = "Auckland - Central",
    city: str = "Stonefields",
    start_date: date = date(2027, 5, 5),
    end_date: date = date(2027, 5, 11),
    url: str | None = "https://example.test/listing/614587",
) -> Listing:
    return Listing(
        external_id=external_id,
        content_hash=content_hash,
        island=island,
        region=region,
        subregion=subregion,
        city=city,
        duration_days=6,
        start_date=start_date,
        end_date=end_date,
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


def _matching_alert_filter() -> AlertFilterDefinition:
    return AlertFilterDefinition(
        name="workflow event filter",
        enabled=True,
        site_filter={
            "state": "north-island",
            "region": "auckland",
            "subregion": "auckland-central",
        },
        local_filter={
            "date_window_match": "contained",
            "start_date_on_or_after": "2026-08-01",
            "end_date_on_or_before": "2026-11-30",
            "min_duration_days": 8,
            "max_duration_days": None,
            "allowed_islands": None,
            "allowed_regions": None,
            "allowed_subregions": None,
            "max_total_animals": None,
            "max_dogs": 2,
            "dogs_allowed": True,
            "cats_allowed": False,
            "fish_allowed": False,
            "birds_allowed": False,
            "rabbits_guinea_pigs_allowed": False,
            "chickens_ducks_geese_allowed": False,
            "farm_animals_allowed": False,
            "horses_allowed": False,
            "reptiles_allowed": False,
            "other_pets_allowed": False,
            "no_pets_allowed": False,
            "min_reply_rating_score": None,
            "allowed_house_types": None,
            "excluded_house_types": [],
            "include_keywords": [],
            "exclude_keywords": [],
        },
        delivery=AlertDelivery(
            channels=("telegram", "email"),
            quiet_hours=AlertQuietHours(
                timezone="Pacific/Auckland",
                start=time(0),
                end=time(6),
            ),
        ),
    )


def _matching_listing() -> Listing:
    return Listing(
        external_id="matching-listing",
        content_hash="matching-v1",
        island="North Island",
        region="Auckland",
        subregion="Auckland - Central",
        city="Stonefields",
        duration_days=21,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 22),
        house_type="Duplex",
        total_animals=1,
        dogs_count=1,
        reply_rating_score=10,
        title="Central sit",
        intro="Pet care required.",
        url="https://example.test/listing/matching-listing",
    )


class _FakeProvider:
    channel = "telegram"

    def __init__(self, results: tuple[ProviderDeliveryResult, ...]) -> None:
        self.results = list(results)
        self.messages: list[str] = []

    def send(self, message) -> ProviderDeliveryResult:
        self.messages.append(message.text)
        return self.results.pop(0)
