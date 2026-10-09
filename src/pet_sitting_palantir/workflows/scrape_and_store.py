"""Workflow for scraping one configured scope and persisting the result."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Any, Protocol

from psycopg import Connection

from pet_sitting_palantir.alerts import (
    AlertFilterDefinition,
    CreatedAlertEvent,
    create_alert_events,
)
from pet_sitting_palantir.kiwihousesitters.constants import (
    DEFAULT_MAX_PAGES,
    WAF_CHALLENGE_ERROR_MARKER,
)
from pet_sitting_palantir.kiwihousesitters.scraper import ScrapeResult, scrape_scope
from pet_sitting_palantir.kiwihousesitters.search_filters import build_search_request
from pet_sitting_palantir.storage import (
    BroadScrapeCampaignCoverage,
    ScrapeRunCounts,
    ScrapeScope,
    close_scrape_run,
    connect_database,
    create_scrape_run,
    listing_record_from_scraped_listing,
    mark_expired_by_date,
    mark_missing_listings_for_scope,
    read_enabled_scrape_scope,
    upsert_listings,
)


class Scraper(Protocol):
    """Callable scraper interface used by the persistence workflow."""

    def __call__(
        self,
        site_filter: Mapping[str, Any] | None = None,
        *,
        max_pages: int | None = DEFAULT_MAX_PAGES,
    ) -> ScrapeResult: ...


@dataclass(frozen=True)
class StoredScrapeResult:
    """Summary of one persisted scrape."""

    scope_name: str
    run_id: int
    search_url: str
    pages_fetched: int
    listings_seen: int
    new_listings: int
    changed_listings: int
    missing_marked: int
    status: str
    alert_events: tuple[CreatedAlertEvent, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        payload = asdict(self)
        payload.pop("alert_events")
        payload["alerts_created"] = len(self.alert_events)
        return payload


def scrape_and_store_scope(
    *,
    scope_name: str,
    max_pages: int | None = None,
    database_url: str | None = None,
    scraper: Scraper = scrape_scope,
) -> StoredScrapeResult:
    """Scrape one enabled database scope and persist normalized listing records."""
    connection = connect_database(database_url)
    try:
        return scrape_and_store_scope_with_connection(
            connection,
            scope_name=scope_name,
            max_pages=max_pages,
            scraper=scraper,
        )
    finally:
        connection.close()


def scrape_and_store_scope_with_connection(
    connection: Connection,
    *,
    scope_name: str,
    max_pages: int | None = None,
    scraper: Scraper = scrape_scope,
    alert_filters: tuple[AlertFilterDefinition, ...] | None = None,
) -> StoredScrapeResult:
    """Scrape one enabled scope using an existing database connection."""
    if max_pages is not None:
        raise ValueError(
            "Persisted scrapes require --max-pages all so missing-listing lifecycle "
            "updates are based on complete coverage"
        )

    scope = read_enabled_scrape_scope(connection, name=scope_name)
    if scope is None:
        raise ValueError(f"Enabled scrape scope does not exist: {scope_name}")

    search_url = build_search_request(scope.site_filter).url
    run_id = create_scrape_run(
        connection,
        scope_id=scope.id,
        scope_name=scope.name,
        search_url=search_url,
    )
    _commit_if_transactional(connection)

    try:
        scrape_result = scraper(scope.site_filter, max_pages=max_pages)
        return _persist_scrape_result_for_run(
            connection,
            scope=scope,
            run_id=run_id,
            scrape_result=scrape_result,
            alert_filters=alert_filters,
        )
    except BaseException as error:
        _rollback_if_transactional(connection)
        close_scrape_run(
            connection,
            run_id=run_id,
            status="failed",
            error_message=_safe_error_message(error),
        )
        _commit_if_transactional(connection)
        raise


def store_completed_scrape_result_with_connection(
    connection: Connection,
    *,
    scope_name: str,
    scrape_result: ScrapeResult,
    alert_filters: tuple[AlertFilterDefinition, ...] | None = None,
    observed_at_by_external_id: Mapping[str, datetime] | None = None,
    coverage_observations: tuple[BroadScrapeCampaignCoverage, ...] | None = None,
    advance_covered_scopes: bool = True,
    excluded_missing_regions: frozenset[str] = frozenset(),
    allowed_missing_states: frozenset[str] | None = None,
    commit: bool = True,
) -> StoredScrapeResult:
    """Atomically persist a complete result assembled by a resumable campaign."""
    scope = read_enabled_scrape_scope(connection, name=scope_name)
    if scope is None:
        raise ValueError(f"Enabled scrape scope does not exist: {scope_name}")

    run_id = create_scrape_run(
        connection,
        scope_id=scope.id,
        scope_name=scope.name,
        search_url=scrape_result.search_url,
    )
    if commit:
        _commit_if_transactional(connection)
    try:
        return _persist_scrape_result_for_run(
            connection,
            scope=scope,
            run_id=run_id,
            scrape_result=scrape_result,
            alert_filters=alert_filters,
            observed_at_by_external_id=observed_at_by_external_id,
            coverage_observations=coverage_observations,
            advance_covered_scopes=advance_covered_scopes,
            excluded_missing_regions=excluded_missing_regions,
            allowed_missing_states=allowed_missing_states,
            commit=commit,
        )
    except BaseException as error:
        _rollback_if_transactional(connection)
        if not commit:
            raise
        close_scrape_run(
            connection,
            run_id=run_id,
            status="failed",
            error_message=_safe_error_message(error),
        )
        _commit_if_transactional(connection)
        raise


def _persist_scrape_result_for_run(
    connection: Connection,
    *,
    scope: ScrapeScope,
    run_id: int,
    scrape_result: ScrapeResult,
    alert_filters: tuple[AlertFilterDefinition, ...] | None,
    observed_at_by_external_id: Mapping[str, datetime] | None = None,
    coverage_observations: tuple[BroadScrapeCampaignCoverage, ...] | None = None,
    advance_covered_scopes: bool = True,
    excluded_missing_regions: frozenset[str] = frozenset(),
    allowed_missing_states: frozenset[str] | None = None,
    commit: bool = True,
) -> StoredScrapeResult:
    records = tuple(
        listing_record_from_scraped_listing(listing) for listing in scrape_result.listings
    )
    if not records:
        counts = ScrapeRunCounts(
            pages_fetched=scrape_result.pages_fetched,
            listings_seen=0,
        )
        close_scrape_run(connection, run_id=run_id, status="suspicious", counts=counts)
        if commit:
            _commit_if_transactional(connection)

        return StoredScrapeResult(
            scope_name=scope.name,
            run_id=run_id,
            search_url=scrape_result.search_url,
            pages_fetched=scrape_result.pages_fetched,
            listings_seen=0,
            new_listings=0,
            changed_listings=0,
            missing_marked=0,
            status="suspicious",
        )

    summary = upsert_listings(
        connection,
        listings=records,
        run_id=run_id,
        first_seen_context="baseline" if scope.last_success_at is None else "observed",
        observed_at_by_external_id=observed_at_by_external_id,
    )
    alert_event_summary = create_alert_events(
        connection,
        observations=zip(records, summary.results, strict=True),
        run_id=run_id,
        filter_definitions=alert_filters,
    )
    if scope.last_success_at is None:
        missing_marked = 0
    elif coverage_observations is None:
        missing_marked = mark_missing_listings_for_scope(
            connection,
            scope=scope,
            seen_external_ids={record.external_id for record in records},
        )
    else:
        eligible_coverage = tuple(
            coverage
            for coverage in coverage_observations
            if isinstance(coverage.site_filter.get("region"), str)
            and coverage.site_filter.get("region") not in excluded_missing_regions
            and (
                allowed_missing_states is None
                or coverage.site_filter.get("state") in allowed_missing_states
            )
        )
        missing_marked = sum(
            mark_missing_listings_for_scope(
                connection,
                scope=replace(scope, site_filter=coverage.site_filter),
                seen_external_ids=set(coverage.seen_external_ids),
                observed_no_later_than=coverage.completed_at,
            )
            for coverage in eligible_coverage
        )
    mark_expired_by_date(connection)
    counts = ScrapeRunCounts(
        pages_fetched=scrape_result.pages_fetched,
        listings_seen=summary.listings_seen,
        new_listings=summary.new_listings,
        changed_listings=summary.changed_listings,
        missing_marked=missing_marked,
    )
    close_scrape_run(
        connection,
        run_id=run_id,
        status="success",
        counts=counts,
        advance_covered_scopes=advance_covered_scopes,
    )
    if commit:
        _commit_if_transactional(connection)

    return StoredScrapeResult(
        scope_name=scope.name,
        run_id=run_id,
        search_url=scrape_result.search_url,
        pages_fetched=scrape_result.pages_fetched,
        listings_seen=summary.listings_seen,
        new_listings=summary.new_listings,
        changed_listings=summary.changed_listings,
        missing_marked=missing_marked,
        status="success",
        alert_events=alert_event_summary.events,
    )


def _commit_if_transactional(connection: Connection) -> None:
    if not connection.autocommit:
        connection.commit()


def _rollback_if_transactional(connection: Connection) -> None:
    if not connection.autocommit:
        connection.rollback()


def _safe_error_message(error: BaseException) -> str:
    message = str(error) or type(error).__name__
    if WAF_CHALLENGE_ERROR_MARKER in message:
        return WAF_CHALLENGE_ERROR_MARKER
    return message
