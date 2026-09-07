"""Daily operational health notifications for the home-hosted runner."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from psycopg import Connection

from pet_sitting_palantir.alerts.messages import AlertMessage
from pet_sitting_palantir.alerts.providers import (
    NotificationDispatchSummary,
    send_notification,
)
from pet_sitting_palantir.settings import (
    HOME_RUNNER_HEALTHCHECK_LOOKBACK_HOURS,
    NEW_ZEALAND_TIME_ZONE,
)
from pet_sitting_palantir.storage import connect_database

NotificationSender = Callable[[AlertMessage], NotificationDispatchSummary]

HEALTHCHECK_OK_MAX_FAILED_ATTEMPTS = 4
HEALTHCHECK_WARN_MAX_FAILED_ATTEMPTS = 19
HEALTHCHECK_STALE_INTERVAL_MULTIPLIER = 2


@dataclass(frozen=True)
class ScopeRunCount:
    """Successful scrape count for one executed scope."""

    scope_name: str
    runs: int
    new_listings: int = 0
    changed_listings: int = 0


@dataclass(frozen=True)
class ScopeFreshness:
    """Last successful coverage time for one enabled scope."""

    scope_name: str
    interval_minutes: int
    last_success_at: datetime | None


@dataclass(frozen=True)
class HealthcheckSummary:
    """Database-backed operational summary for the daily health notification."""

    generated_at: datetime
    successful_runs: int
    failed_runs: int
    new_listings: int
    changed_listings: int
    scope_runs: tuple[ScopeRunCount, ...]
    stalest_scope: ScopeFreshness | None
    database_error: str | None = None


@dataclass(frozen=True)
class HealthcheckDeliverySummary:
    """Outcome of one daily health notification attempt."""

    status: str
    message: str | None = None
    provider_message_id: str | None = None
    error_message: str | None = None


def send_healthcheck(
    *,
    current_time: datetime | None = None,
    notification_sender: NotificationSender = send_notification,
    database_url: str | None = None,
) -> HealthcheckDeliverySummary:
    """Send one operational health check through the configured notification layer."""
    generated_at = _local_time(current_time)
    try:
        with connect_database(database_url) as connection:
            summary = read_healthcheck_summary(connection, current_time=generated_at)
    except Exception as error:
        summary = HealthcheckSummary(
            generated_at=generated_at,
            successful_runs=0,
            failed_runs=0,
            new_listings=0,
            changed_listings=0,
            scope_runs=(),
            stalest_scope=None,
            database_error=type(error).__name__,
        )

    message = format_healthcheck_message(summary)
    result = notification_sender(AlertMessage(text=message))
    if result.providers_configured == 0:
        return HealthcheckDeliverySummary(
            status="unconfigured",
            message=message,
            error_message="No configured notification providers",
        )
    if result.sent == 0:
        return HealthcheckDeliverySummary(
            status="failed",
            message=message,
            error_message=_dispatch_error_text(result),
        )
    if result.failed:
        return HealthcheckDeliverySummary(
            status="partial_failure",
            message=message,
            provider_message_id=_provider_message_id_text(result),
            error_message=_dispatch_error_text(result),
        )

    return HealthcheckDeliverySummary(
        status="sent",
        message=message,
        provider_message_id=_provider_message_id_text(result),
    )


def read_healthcheck_summary(
    connection: Connection,
    *,
    current_time: datetime | None = None,
) -> HealthcheckSummary:
    """Read the database counters used by the daily health notification."""
    generated_at = _local_time(current_time)
    since = generated_at.astimezone(UTC) - timedelta(hours=HOME_RUNNER_HEALTHCHECK_LOOKBACK_HOURS)

    with connection.cursor() as cursor:
        cursor.execute(
            """
            select
              scope_name,
              count(*) as runs,
              sum(new_listings) as new_listings,
              sum(changed_listings) as changed_listings
            from scrape_runs
            where status = 'success'
              and finished_at >= %s
            group by scope_name
            order by scope_name
            """,
            (since,),
        )
        scope_runs = tuple(
            ScopeRunCount(
                scope_name=row["scope_name"],
                runs=row["runs"],
                new_listings=row["new_listings"] or 0,
                changed_listings=row["changed_listings"] or 0,
            )
            for row in cursor.fetchall()
        )

        cursor.execute(
            """
            select count(*) as runs
            from scrape_runs
            where status in ('failed', 'partial_failure', 'suspicious')
              and started_at >= %s
            """,
            (since,),
        )
        failed_runs = cursor.fetchone()["runs"]

        cursor.execute(
            """
            select name, interval_minutes, last_success_at
            from scrape_scopes
            where enabled = true
            order by name
            """
        )
        scope_freshness = tuple(
            ScopeFreshness(
                scope_name=row["name"],
                interval_minutes=row["interval_minutes"],
                last_success_at=row["last_success_at"],
            )
            for row in cursor.fetchall()
        )

    return HealthcheckSummary(
        generated_at=generated_at,
        successful_runs=sum(scope.runs for scope in scope_runs),
        failed_runs=failed_runs,
        new_listings=sum(row.new_listings for row in scope_runs),
        changed_listings=sum(row.changed_listings for row in scope_runs),
        scope_runs=scope_runs,
        stalest_scope=_stalest_scope(scope_freshness, generated_at=generated_at),
    )


def format_healthcheck_message(summary: HealthcheckSummary) -> str:
    """Format the daily operational health check."""
    if summary.database_error:
        return "\n".join(
            (
                "-- Health check -- CRITICAL",
                f"Database: unavailable ({summary.database_error})",
            )
        )

    status = _healthcheck_status(summary)
    return "\n".join(
        (
            f"-- Health check -- {status}",
            *_scope_run_lines(summary.scope_runs),
            (
                f"Total: {summary.successful_runs} scans, "
                f"{summary.new_listings} new, {summary.changed_listings} changed"
            ),
            f"Failed scan attempts: {summary.failed_runs}",
            f"Stalest coverage: {_freshness_text(summary)}",
        )
    )


def _healthcheck_status(summary: HealthcheckSummary) -> str:
    if summary.database_error:
        return "CRITICAL"
    if summary.successful_runs == 0 or _scope_is_excessively_stale(summary.stalest_scope, summary):
        return "CRITICAL"
    if summary.failed_runs == 0:
        return "FLAWLESS"
    if summary.failed_runs <= HEALTHCHECK_OK_MAX_FAILED_ATTEMPTS:
        return "OK"
    if summary.failed_runs <= HEALTHCHECK_WARN_MAX_FAILED_ATTEMPTS:
        return "WARN"
    return "CRITICAL"


def _local_time(current_time: datetime | None) -> datetime:
    instant = current_time or datetime.now(tz=NEW_ZEALAND_TIME_ZONE)
    if instant.tzinfo is None:
        raise ValueError("current_time must include a timezone")
    return instant.astimezone(NEW_ZEALAND_TIME_ZONE)


def _scope_run_lines(scope_runs: tuple[ScopeRunCount, ...]) -> tuple[str, ...]:
    if not scope_runs:
        return ("Scans: none",)
    return tuple(f"- {scope.scope_name}: {scope.runs}" for scope in scope_runs)


def _freshness_text(summary: HealthcheckSummary) -> str:
    if summary.stalest_scope is None:
        return "no enabled scopes"
    if summary.stalest_scope.last_success_at is None:
        return (
            f"never ({summary.stalest_scope.scope_name}, "
            f"interval {summary.stalest_scope.interval_minutes}m)"
        )

    age = summary.generated_at - summary.stalest_scope.last_success_at.astimezone(
        NEW_ZEALAND_TIME_ZONE
    )
    age_seconds = max(0, int(age.total_seconds()))
    if age_seconds < 90 * 60:
        age_text = f"{round(age_seconds / 60)}m"
    elif age_seconds < 48 * 60 * 60:
        age_text = f"{round(age_seconds / 3600)}h"
    else:
        age_text = f"{round(age_seconds / 86400)}d"
    return (
        f"{age_text} ({summary.stalest_scope.scope_name}, "
        f"interval {summary.stalest_scope.interval_minutes}m)"
    )


def _stalest_scope(
    scopes: tuple[ScopeFreshness, ...],
    *,
    generated_at: datetime,
) -> ScopeFreshness | None:
    if not scopes:
        return None
    return max(
        scopes,
        key=lambda scope: _scope_staleness_ratio(scope, generated_at=generated_at),
    )


def _scope_staleness_ratio(scope: ScopeFreshness, *, generated_at: datetime) -> float:
    if scope.last_success_at is None:
        return float("inf")
    age = generated_at - scope.last_success_at.astimezone(NEW_ZEALAND_TIME_ZONE)
    age_seconds = max(0, age.total_seconds())
    return age_seconds / (scope.interval_minutes * 60)


def _scope_is_excessively_stale(
    scope: ScopeFreshness | None,
    summary: HealthcheckSummary,
) -> bool:
    if scope is None or scope.last_success_at is None:
        return True
    age = summary.generated_at - scope.last_success_at.astimezone(NEW_ZEALAND_TIME_ZONE)
    stale_after = timedelta(minutes=scope.interval_minutes * HEALTHCHECK_STALE_INTERVAL_MULTIPLIER)
    return age > stale_after


def _provider_message_id_text(result: NotificationDispatchSummary) -> str | None:
    if not result.provider_message_ids:
        return None
    return ",".join(
        f"{channel}:{message_id}"
        for channel, message_id in sorted(result.provider_message_ids.items())
    )


def _dispatch_error_text(result: NotificationDispatchSummary) -> str | None:
    if not result.failures:
        return None
    return "; ".join(f"{failure.channel}: {failure.error_message}" for failure in result.failures)
