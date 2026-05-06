"""Workflow for scraping one configured scope and persisting the result."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from psycopg import Connection

from pet_sitting_palantir.kiwihousesitters.constants import DEFAULT_MAX_PAGES
from pet_sitting_palantir.kiwihousesitters.scraper import ScrapeResult, scrape_scope
from pet_sitting_palantir.kiwihousesitters.search_filters import build_search_request
from pet_sitting_palantir.storage import (
    ScrapeRunCounts,
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

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


def scrape_and_store_scope(
    *,
    scope_name: str,
    max_pages: int | None = DEFAULT_MAX_PAGES,
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
    max_pages: int | None = DEFAULT_MAX_PAGES,
    scraper: Scraper = scrape_scope,
) -> StoredScrapeResult:
    """Scrape one enabled scope using an existing database connection."""
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
        records = tuple(
            listing_record_from_scraped_listing(listing) for listing in scrape_result.listings
        )
        if not records:
            counts = ScrapeRunCounts(
                pages_fetched=scrape_result.pages_fetched,
                listings_seen=0,
            )
            close_scrape_run(connection, run_id=run_id, status="suspicious", counts=counts)
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
        )
        missing_marked = mark_missing_listings_for_scope(
            connection,
            scope=scope,
            seen_external_ids={record.external_id for record in records},
        )
        mark_expired_by_date(connection)
        counts = ScrapeRunCounts(
            pages_fetched=scrape_result.pages_fetched,
            listings_seen=summary.listings_seen,
            new_listings=summary.new_listings,
            changed_listings=summary.changed_listings,
            missing_marked=missing_marked,
        )
        close_scrape_run(connection, run_id=run_id, status="success", counts=counts)
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
        )
    except Exception as error:
        _rollback_if_transactional(connection)
        close_scrape_run(
            connection,
            run_id=run_id,
            status="failed",
            error_message=str(error),
        )
        _commit_if_transactional(connection)
        raise


def _commit_if_transactional(connection: Connection) -> None:
    if not connection.autocommit:
        connection.commit()


def _rollback_if_transactional(connection: Connection) -> None:
    if not connection.autocommit:
        connection.rollback()
