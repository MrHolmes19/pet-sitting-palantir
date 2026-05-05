"""Workflow for running every database-backed scrape scope that is due."""

from dataclasses import asdict, dataclass
from typing import Any

from psycopg import Connection

from pet_sitting_palantir.kiwihousesitters.constants import DEFAULT_MAX_PAGES
from pet_sitting_palantir.storage import connect_database, read_due_scrape_scopes
from pet_sitting_palantir.workflows.scrape_and_store import (
    Scraper,
    StoredScrapeResult,
    scrape_and_store_scope_with_connection,
)


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
    max_pages: int = DEFAULT_MAX_PAGES,
    database_url: str | None = None,
    scraper: Scraper | None = None,
) -> DueScopeRunResult:
    """Run every enabled scrape scope that is currently due."""
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
    max_pages: int = DEFAULT_MAX_PAGES,
    scraper: Scraper | None = None,
) -> DueScopeRunResult:
    """Run due scopes using an existing database connection."""
    due_scopes = read_due_scrape_scopes(connection)
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
