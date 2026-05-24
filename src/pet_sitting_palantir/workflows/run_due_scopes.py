"""Workflow for running every database-backed scrape scope that is due."""

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from psycopg import Connection

from pet_sitting_palantir.kiwihousesitters.constants import DEFAULT_MAX_PAGES
from pet_sitting_palantir.storage import ScrapeScope, connect_database, read_due_scrape_scopes
from pet_sitting_palantir.workflows.scrape_and_store import (
    Scraper,
    StoredScrapeResult,
    scrape_and_store_scope_with_connection,
)

NEW_ZEALAND_TIME_ZONE = ZoneInfo("Pacific/Auckland")
QUIET_HOURS_START = time(hour=0)
QUIET_HOURS_END = time(hour=6)


@dataclass(frozen=True)
class DueScopeFailure:
    """Failure captured while running one due scrape scope."""

    scope_name: str
    error_message: str


@dataclass(frozen=True)
class DueScopeRunResult:
    """Summary of one due-scope runner invocation."""

    status: str
    scopes_due: int
    scopes_succeeded: int
    scopes_failed: int
    results: tuple[StoredScrapeResult, ...]
    failures: tuple[DueScopeFailure, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        payload = asdict(self)
        payload["results"] = [result.to_dict() for result in self.results]
        payload["failures"] = [asdict(failure) for failure in self.failures]
        return payload


def run_due_scrape_scopes(
    *,
    max_pages: int | None = DEFAULT_MAX_PAGES,
    database_url: str | None = None,
    scraper: Scraper | None = None,
    current_time: datetime | None = None,
) -> DueScopeRunResult:
    """Run every enabled scrape scope that is currently due."""
    if _is_quiet_hours(current_time):
        return DueScopeRunResult(
            status="quiet_hours",
            scopes_due=0,
            scopes_succeeded=0,
            scopes_failed=0,
            results=(),
            failures=(),
        )

    connection = connect_database(database_url)
    try:
        return run_due_scrape_scopes_with_connection(
            connection,
            max_pages=max_pages,
            scraper=scraper,
        )
    finally:
        connection.close()


def run_due_scrape_scopes_with_connection(
    connection: Connection,
    *,
    max_pages: int | None = DEFAULT_MAX_PAGES,
    scraper: Scraper | None = None,
) -> DueScopeRunResult:
    """Run due scopes using an existing database connection."""
    due_scopes = _select_broadest_due_scopes(read_due_scrape_scopes(connection))
    results: list[StoredScrapeResult] = []
    failures: list[DueScopeFailure] = []

    for scope in due_scopes:
        try:
            kwargs: dict[str, Any] = {
                "connection": connection,
                "scope_name": scope.name,
                "max_pages": max_pages,
            }
            if scraper is not None:
                kwargs["scraper"] = scraper
            results.append(scrape_and_store_scope_with_connection(**kwargs))
        except Exception as error:
            failures.append(
                DueScopeFailure(
                    scope_name=scope.name,
                    error_message=str(error),
                )
            )

    return DueScopeRunResult(
        status=_runner_status(scopes_due=len(due_scopes), failures_count=len(failures)),
        scopes_due=len(due_scopes),
        scopes_succeeded=len(results),
        scopes_failed=len(failures),
        results=tuple(results),
        failures=tuple(failures),
    )


def _runner_status(*, scopes_due: int, failures_count: int) -> str:
    if scopes_due == 0:
        return "nothing_due"
    if failures_count == 0:
        return "success"
    if failures_count == scopes_due:
        return "failed"
    return "partial_failure"


def _is_quiet_hours(current_time: datetime | None = None) -> bool:
    """Return whether scraping is paused for the overnight New Zealand window."""
    instant = current_time or datetime.now(tz=NEW_ZEALAND_TIME_ZONE)
    if instant.tzinfo is None:
        raise ValueError("current_time must include a timezone")

    local_time = instant.astimezone(NEW_ZEALAND_TIME_ZONE).time()
    return QUIET_HOURS_START <= local_time < QUIET_HOURS_END


def _select_broadest_due_scopes(scopes: Sequence[ScrapeScope]) -> tuple[ScrapeScope, ...]:
    """Remove due scopes covered by a broader due scope in the same invocation."""
    return tuple(
        scope
        for scope in scopes
        if not any(_scope_is_broader_than(other, scope) for other in scopes)
    )


def _scope_is_broader_than(parent: ScrapeScope, child: ScrapeScope) -> bool:
    return _site_filter_covers(parent.site_filter, child.site_filter) and not _site_filter_covers(
        child.site_filter,
        parent.site_filter,
    )


def _site_filter_covers(
    parent_filter: Mapping[str, Any],
    child_filter: Mapping[str, Any],
) -> bool:
    return all(child_filter.get(key) == value for key, value in parent_filter.items())
