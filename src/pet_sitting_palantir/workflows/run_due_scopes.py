"""Workflow for running every database-backed scrape scope that is due."""

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any, Literal

from psycopg import Connection

from pet_sitting_palantir.kiwihousesitters.client import KiwiHouseSittersClient
from pet_sitting_palantir.kiwihousesitters.constants import WAF_CHALLENGE_ERROR_MARKER
from pet_sitting_palantir.kiwihousesitters.scraper import scrape_scope
from pet_sitting_palantir.settings import (
    BROAD_SCRAPE_WAF_INITIAL_COOLDOWN_HOURS,
    KIWIHOUSESITTERS_REQUEST_INTERVAL_JITTER_SECONDS,
    NEW_ZEALAND_TIME_ZONE,
    PRIORITY_SCOPE_WAF_COOLDOWN_MINUTES,
    QUIET_HOURS_END,
    QUIET_HOURS_START,
    SCRAPE_FAILURE_RETRY_MAX_MINUTES,
)
from pet_sitting_palantir.storage import (
    ScrapeScope,
    connect_database,
    read_active_broad_scrape_campaign,
    read_due_scrape_scopes,
    read_latest_campaign_waf_challenge_at,
    read_latest_scope_waf_challenge_at,
    read_latest_waf_challenge_at,
)
from pet_sitting_palantir.workflows.broad_scrape_campaign import (
    BroadCampaignStep,
    is_broad_scrape_scope,
    run_broad_scrape_campaign_step,
)
from pet_sitting_palantir.workflows.scrape_and_store import (
    Scraper,
    StoredScrapeResult,
    scrape_and_store_scope_with_connection,
)

ScopePhase = Literal["all", "priority", "broad"]


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
    campaign_steps: tuple[BroadCampaignStep, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        payload = asdict(self)
        payload["results"] = [result.to_dict() for result in self.results]
        payload["failures"] = [asdict(failure) for failure in self.failures]
        payload["campaign_steps"] = [step.to_dict() for step in self.campaign_steps]
        return payload


def run_due_scrape_scopes(
    *,
    max_pages: int | None = None,
    database_url: str | None = None,
    scraper: Scraper | None = None,
    current_time: datetime | None = None,
    phase: ScopePhase = "all",
    time_budget_seconds: float | None = None,
) -> DueScopeRunResult:
    """Run every enabled scrape scope that is currently due."""
    instant = current_time or datetime.now(tz=UTC)
    if _is_quiet_hours(instant):
        return DueScopeRunResult(
            status="quiet_hours",
            scopes_due=0,
            scopes_succeeded=0,
            scopes_failed=0,
            results=(),
            failures=(),
        )

    selected_scraper = scraper
    if phase == "broad" and selected_scraper is None and time_budget_seconds is not None:
        deadline_client = KiwiHouseSittersClient(
            request_interval_jitter_seconds=KIWIHOUSESITTERS_REQUEST_INTERVAL_JITTER_SECONDS,
            deadline=monotonic() + time_budget_seconds,
        )

        def bounded_scraper(site_filter, *, max_pages):
            return scrape_scope(site_filter, max_pages=max_pages, client=deadline_client)

        selected_scraper = bounded_scraper

    connection = connect_database(database_url)
    try:
        return run_due_scrape_scopes_with_connection(
            connection,
            max_pages=max_pages,
            scraper=selected_scraper,
            current_time=instant,
            phase=phase,
        )
    finally:
        connection.close()


def run_due_priority_scrape_scopes(
    *,
    max_pages: int | None = None,
    database_url: str | None = None,
    scraper: Scraper | None = None,
    current_time: datetime | None = None,
) -> DueScopeRunResult:
    """Run only priority scopes; background failures never gate this phase."""
    return run_due_scrape_scopes(
        max_pages=max_pages,
        database_url=database_url,
        scraper=scraper,
        current_time=current_time,
        phase="priority",
    )


def run_due_broad_scrape_scopes(
    *,
    max_pages: int | None = None,
    time_budget_seconds: float,
    database_url: str | None = None,
    scraper: Scraper | None = None,
    current_time: datetime | None = None,
) -> DueScopeRunResult:
    """Run at most one deadline-bounded broad campaign step."""
    return run_due_scrape_scopes(
        max_pages=max_pages,
        database_url=database_url,
        scraper=scraper,
        current_time=current_time,
        phase="broad",
        time_budget_seconds=time_budget_seconds,
    )


def run_due_scrape_scopes_with_connection(
    connection: Connection,
    *,
    max_pages: int | None = None,
    scraper: Scraper | None = None,
    current_time: datetime | None = None,
    phase: ScopePhase = "all",
) -> DueScopeRunResult:
    """Run due scopes using an existing database connection."""
    instant = current_time or datetime.now(tz=UTC)
    if phase == "all":
        priority = run_due_scrape_scopes_with_connection(
            connection,
            max_pages=max_pages,
            scraper=scraper,
            current_time=instant,
            phase="priority",
        )
        broad = run_due_scrape_scopes_with_connection(
            connection,
            max_pages=max_pages,
            scraper=scraper,
            current_time=instant,
            phase="broad",
        )
        return _merge_phase_results(priority, broad)

    configured_due_scopes = tuple(
        scope
        for scope in read_due_scrape_scopes(connection)
        if is_broad_scrape_scope(scope) == (phase == "broad")
    )
    latest_waf_challenge_at = _latest_instant(
        read_latest_waf_challenge_at(connection),
        read_latest_campaign_waf_challenge_at(connection),
    ) if phase == "broad" else None
    active_campaigns = {
        scope.id: campaign
        for scope in configured_due_scopes
        if is_broad_scrape_scope(scope)
        and (campaign := read_active_broad_scrape_campaign(connection, scope_id=scope.id))
        is not None
    }
    latest_scope_waf_at = (
        {}
        if phase == "broad"
        else {
            scope.id: read_latest_scope_waf_challenge_at(
                connection,
                scope_name=scope.name,
            )
            for scope in configured_due_scopes
        }
    )
    ready_scopes = _scopes_ready_for_attempt(
        configured_due_scopes,
        current_time=instant,
        active_campaign_scope_ids=frozenset(active_campaigns),
        latest_scope_waf_at=latest_scope_waf_at,
    )
    if phase == "broad":
        due_scopes = _select_scopes_for_tick(
            ready_scopes,
            active_campaign_scope_ids=frozenset(active_campaigns),
            current_time=instant,
            latest_waf_challenge_at=latest_waf_challenge_at,
            active_campaigns=active_campaigns,
        )
        waf_cooldown_active = bool(configured_due_scopes) and _broad_scope_is_in_waf_cooldown(
            current_time=instant,
            latest_waf_challenge_at=latest_waf_challenge_at,
        )
    else:
        due_scopes = _select_broadest_due_scopes(ready_scopes)
        waf_cooldown_active = False
    priority_waf_cooldown_active = phase == "priority" and any(
        _scope_is_in_priority_waf_cooldown(
            scope,
            current_time=instant,
            latest_waf_challenge_at=latest_scope_waf_at.get(scope.id),
        )
        for scope in configured_due_scopes
    )
    results: list[StoredScrapeResult] = []
    failures: list[DueScopeFailure] = []
    campaign_steps: list[BroadCampaignStep] = []
    campaign_steps_succeeded = 0

    for scope in due_scopes:
        try:
            if is_broad_scrape_scope(scope):
                step = run_broad_scrape_campaign_step(
                    connection,
                    scope=scope,
                    scraper=scraper or scrape_scope,
                    current_time=instant,
                )
                campaign_steps.append(step)
                if step.stored_result is not None:
                    results.append(step.stored_result)
                elif step.status == "in_progress":
                    campaign_steps_succeeded += 1
                elif step.status in ("waf_paused", "failed_paused", "split_paused"):
                    error_message = step.error_message or step.status
                    if step.status == "waf_paused":
                        error_message = (
                            f"WAF challenge; campaign={step.campaign_id}; "
                            f"leaf={step.leaf_key}; resume_after={step.next_attempt_at.isoformat()}"
                        )
                    failures.append(
                        DueScopeFailure(
                            scope_name=scope.name,
                            error_message=error_message,
                        )
                    )
                continue

            kwargs: dict[str, Any] = {
                "connection": connection,
                "scope_name": scope.name,
                "max_pages": max_pages,
            }
            if scraper is not None:
                kwargs["scraper"] = scraper
            results.append(scrape_and_store_scope_with_connection(**kwargs))
        except Exception as error:
            error_message = str(error)
            if WAF_CHALLENGE_ERROR_MARKER in error_message:
                error_message = WAF_CHALLENGE_ERROR_MARKER
            failures.append(
                DueScopeFailure(
                    scope_name=scope.name,
                    error_message=error_message,
                )
            )

    status = _runner_status(scopes_due=len(due_scopes), failures_count=len(failures))
    if not due_scopes and waf_cooldown_active:
        status = "waf_cooldown"
    elif not due_scopes and priority_waf_cooldown_active:
        status = "priority_waf_cooldown"

    return DueScopeRunResult(
        status=status,
        scopes_due=len(due_scopes),
        scopes_succeeded=len(results) + campaign_steps_succeeded,
        scopes_failed=len(failures),
        results=tuple(results),
        failures=tuple(failures),
        campaign_steps=tuple(campaign_steps),
    )


def _merge_phase_results(
    priority: DueScopeRunResult,
    broad: DueScopeRunResult,
) -> DueScopeRunResult:
    scopes_due = priority.scopes_due + broad.scopes_due
    failures = (*priority.failures, *broad.failures)
    status = _runner_status(scopes_due=scopes_due, failures_count=len(failures))
    if scopes_due == 0 and broad.status == "waf_cooldown":
        status = "waf_cooldown"
    return DueScopeRunResult(
        status=status,
        scopes_due=scopes_due,
        scopes_succeeded=priority.scopes_succeeded + broad.scopes_succeeded,
        scopes_failed=len(failures),
        results=(*priority.results, *broad.results),
        failures=failures,
        campaign_steps=(*priority.campaign_steps, *broad.campaign_steps),
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


def _select_scopes_for_tick(
    scopes: Sequence[ScrapeScope],
    *,
    active_campaign_scope_ids: frozenset[int] = frozenset(),
    current_time: datetime | None = None,
    latest_waf_challenge_at: datetime | None = None,
    active_campaigns: Mapping[int, Any] | None = None,
) -> tuple[ScrapeScope, ...]:
    """Run due narrow work plus at most one ready broad campaign leaf."""
    narrow_scopes = _select_broadest_due_scopes(
        tuple(scope for scope in scopes if not is_broad_scrape_scope(scope))
    )
    broad_scopes = tuple(scope for scope in scopes if is_broad_scrape_scope(scope))
    campaign_by_scope = active_campaigns or {}
    broad_waf_cooldown = _broad_scope_is_in_waf_cooldown(
        current_time=current_time,
        latest_waf_challenge_at=latest_waf_challenge_at,
    )
    ready_active_scopes = tuple(
        scope
        for scope in broad_scopes
        if scope.id in active_campaign_scope_ids
        and not broad_waf_cooldown
        and (current_time is None or campaign_by_scope[scope.id].next_attempt_at <= current_time)
    )
    if ready_active_scopes:
        broad_scope = ready_active_scopes[0]
    elif active_campaign_scope_ids:
        broad_scope = None
    else:
        new_broad_scopes = tuple(
            scope
            for scope in broad_scopes
            if scope.id not in active_campaign_scope_ids
            and not broad_waf_cooldown
        )
        selected_new = _select_broadest_due_scopes(new_broad_scopes)
        broad_scope = selected_new[0] if selected_new else None

    return (*narrow_scopes, *((broad_scope,) if broad_scope is not None else ()))


def _scopes_ready_for_attempt(
    scopes: Sequence[ScrapeScope],
    *,
    current_time: datetime,
    active_campaign_scope_ids: frozenset[int] = frozenset(),
    latest_scope_waf_at: Mapping[int, datetime | None] | None = None,
) -> tuple[ScrapeScope, ...]:
    """Exclude recently failed scopes without treating their coverage as fresh."""
    if current_time.tzinfo is None:
        raise ValueError("current_time must include a timezone")

    return tuple(
        scope
        for scope in scopes
        if (
            scope.id in active_campaign_scope_ids
            or (
                not _scope_is_in_failure_cooldown(scope, current_time=current_time)
                and not _scope_is_in_priority_waf_cooldown(
                    scope,
                    current_time=current_time,
                    latest_waf_challenge_at=(latest_scope_waf_at or {}).get(scope.id),
                )
            )
        )
    )


def _broad_scope_is_in_waf_cooldown(
    *,
    current_time: datetime | None,
    latest_waf_challenge_at: datetime | None,
) -> bool:
    if current_time is None or latest_waf_challenge_at is None:
        return False
    return current_time - latest_waf_challenge_at < timedelta(
        hours=BROAD_SCRAPE_WAF_INITIAL_COOLDOWN_HOURS
    )


def _latest_instant(*instants: datetime | None) -> datetime | None:
    present = tuple(instant for instant in instants if instant is not None)
    return max(present) if present else None


def _scope_is_in_failure_cooldown(
    scope: ScrapeScope,
    *,
    current_time: datetime,
) -> bool:
    if scope.last_attempt_at is None:
        return False
    if scope.last_success_at is not None and scope.last_attempt_at <= scope.last_success_at:
        return False

    retry_minutes = min(
        scope.interval_minutes,
        SCRAPE_FAILURE_RETRY_MAX_MINUTES,
    )
    return current_time < scope.last_attempt_at + timedelta(minutes=retry_minutes)


def _scope_is_in_priority_waf_cooldown(
    scope: ScrapeScope,
    *,
    current_time: datetime,
    latest_waf_challenge_at: datetime | None,
) -> bool:
    if latest_waf_challenge_at is None:
        return False
    if scope.last_success_at is not None and scope.last_success_at >= latest_waf_challenge_at:
        return False
    return current_time < latest_waf_challenge_at + timedelta(
        minutes=PRIORITY_SCOPE_WAF_COOLDOWN_MINUTES
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
