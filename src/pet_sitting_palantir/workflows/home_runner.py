"""Continuous home-hosted production runner for database-backed scrape scopes."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from fcntl import LOCK_EX, LOCK_NB, LOCK_UN, flock
from logging import Logger, getLogger
from os import getpid
from pathlib import Path
from time import sleep, time

from pet_sitting_palantir.settings import (
    HOME_RUNNER_HEALTHCHECK_TIME,
    HOME_RUNNER_HEALTHCHECK_WINDOW_MINUTES,
    HOME_RUNNER_LOCK_FILE,
    HOME_RUNNER_TICK_INTERVAL_SECONDS,
    KIWIHOUSESITTERS_REQUEST_INTERVAL_SECONDS,
    NEW_ZEALAND_TIME_ZONE,
)
from pet_sitting_palantir.workflows.deliver_alerts import (
    AlertDeliverySummary,
    deliver_due_alerts,
)
from pet_sitting_palantir.workflows.healthcheck import (
    HealthcheckDeliverySummary,
    send_healthcheck,
)
from pet_sitting_palantir.workflows.run_due_scopes import (
    DueScopeRunResult,
    run_due_scrape_scopes,
)

logger = getLogger(__name__)

DueScopeRunner = Callable[..., DueScopeRunResult]
AlertDeliveryRunner = Callable[[], AlertDeliverySummary]
HealthcheckRunner = Callable[..., HealthcheckDeliverySummary]


class RunnerAlreadyActiveError(RuntimeError):
    """Raised when another home-hosted production runner owns the lock."""


def run_home_runner(
    *,
    max_pages: int | None = None,
    lock_file: Path = HOME_RUNNER_LOCK_FILE,
) -> None:
    """Run the production due-scope supervisor until interrupted."""
    with _single_instance_lock(lock_file):
        logger.info(
            "runner_start tick=%ss request_delay=%ss",
            HOME_RUNNER_TICK_INTERVAL_SECONDS,
            KIWIHOUSESITTERS_REQUEST_INTERVAL_SECONDS,
        )
        _run_continuously(max_pages=max_pages)


def _run_continuously(
    *,
    max_pages: int | None = None,
    tick_interval_seconds: int = HOME_RUNNER_TICK_INTERVAL_SECONDS,
    due_scope_runner: DueScopeRunner = run_due_scrape_scopes,
    alert_delivery_runner: AlertDeliveryRunner = deliver_due_alerts,
    healthcheck_runner: HealthcheckRunner = send_healthcheck,
    sleep_for: Callable[[float], None] = sleep,
    clock: Callable[[], float] = time,
    runtime_logger: Logger = logger,
) -> None:
    """Run due-scope ticks forever, retrying after tick-level failures."""
    last_healthcheck_date = None
    try:
        while True:
            current_time = datetime.fromtimestamp(clock(), tz=NEW_ZEALAND_TIME_ZONE)
            if _healthcheck_is_due(
                current_time=current_time,
                last_healthcheck_date=last_healthcheck_date,
            ):
                healthcheck = healthcheck_runner(current_time=current_time)
                if healthcheck.status == "sent":
                    runtime_logger.info(
                        "healthcheck_sent provider_message_id=%s",
                        healthcheck.provider_message_id,
                    )
                    last_healthcheck_date = current_time.date()
                elif healthcheck.status == "partial_failure":
                    runtime_logger.error(
                        "healthcheck_partial provider_message_id=%s error=%s",
                        healthcheck.provider_message_id,
                        healthcheck.error_message,
                    )
                    last_healthcheck_date = current_time.date()
                elif healthcheck.status == "unconfigured":
                    runtime_logger.error(
                        "healthcheck_unconfigured error=%s",
                        healthcheck.error_message,
                    )
                    last_healthcheck_date = current_time.date()
                else:
                    runtime_logger.error(
                        "healthcheck_fail error=%s retry=next_tick",
                        healthcheck.error_message,
                    )

            _run_tick(
                max_pages=max_pages,
                due_scope_runner=due_scope_runner,
                alert_delivery_runner=alert_delivery_runner,
                runtime_logger=runtime_logger,
            )
            sleep_for(_seconds_until_next_tick(clock(), tick_interval_seconds))
    except KeyboardInterrupt:
        runtime_logger.info("runner_stop")


def _run_tick(
    *,
    max_pages: int | None,
    due_scope_runner: DueScopeRunner,
    runtime_logger: Logger,
    alert_delivery_runner: AlertDeliveryRunner = deliver_due_alerts,
) -> None:
    runtime_logger.info("tick_start")
    try:
        result = due_scope_runner(max_pages=max_pages)
    except Exception as error:
        runtime_logger.error(
            "tick_fail type=%s error=%s retry=next_tick",
            type(error).__name__,
            error,
        )
    else:
        if result.scopes_failed:
            runtime_logger.error(
                "tick_failed due=%s failed=%s",
                result.scopes_due,
                result.scopes_failed,
            )
            for failure in result.failures:
                runtime_logger.error(
                    "scope_fail name=%s error=%s",
                    failure.scope_name,
                    failure.error_message,
                )
        elif result.scopes_due:
            for stored_result in result.results:
                runtime_logger.info(
                    "scope_ok name=%s pages=%s "
                    "listings=%s new=%s changed=%s missing=%s alerts=%s",
                    stored_result.scope_name,
                    stored_result.pages_fetched,
                    stored_result.listings_seen,
                    stored_result.new_listings,
                    stored_result.changed_listings,
                    stored_result.missing_marked,
                    len(stored_result.alert_events),
                )
                for event in stored_result.alert_events:
                    runtime_logger.info(
                        "alert_queued filter=%s type=%s listing=%s channels=%s "
                        "deliver_after=%s url=%s",
                        event.filter_name,
                        event.event_type,
                        event.listing_external_id,
                        ",".join(event.target_channels),
                        event.deliver_after.isoformat(),
                        event.listing_url,
                    )
        else:
            runtime_logger.info("tick_ok status=%s", result.status)

    try:
        delivery = alert_delivery_runner()
    except Exception as error:
        runtime_logger.error(
            "delivery_fail type=%s error=%s retry=next_tick",
            type(error).__name__,
            error,
        )
        return

    runtime_logger.info(
        "delivery_ok due=%s attempted=%s sent=%s failed=%s unconfigured=%s",
        delivery.deliveries_due,
        delivery.attempts_made,
        delivery.sent,
        delivery.failed,
        delivery.unconfigured,
    )
    for failure in delivery.failures:
        runtime_logger.error(
            "delivery_unsent event=%s channel=%s error=%s retry=next_tick",
            failure.alert_event_id,
            failure.channel,
            failure.error_message,
        )


def _seconds_until_next_tick(timestamp: float, tick_interval_seconds: int) -> float:
    remainder = timestamp % tick_interval_seconds
    return tick_interval_seconds if remainder == 0 else tick_interval_seconds - remainder


def _healthcheck_is_due(
    *,
    current_time: datetime,
    last_healthcheck_date,
) -> bool:
    if current_time.tzinfo is None:
        raise ValueError("current_time must include a timezone")
    local_time = current_time.astimezone(NEW_ZEALAND_TIME_ZONE)
    window_start = local_time.replace(
        hour=HOME_RUNNER_HEALTHCHECK_TIME.hour,
        minute=HOME_RUNNER_HEALTHCHECK_TIME.minute,
        second=0,
        microsecond=0,
    )
    window_end = window_start + timedelta(minutes=HOME_RUNNER_HEALTHCHECK_WINDOW_MINUTES)
    return (
        window_start <= local_time < window_end
        and last_healthcheck_date != local_time.date()
    )


@contextmanager
def _single_instance_lock(lock_file: Path) -> Iterator[None]:
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    with lock_file.open("a+") as lock_handle:
        try:
            flock(lock_handle.fileno(), LOCK_EX | LOCK_NB)
        except BlockingIOError as error:
            raise RunnerAlreadyActiveError(
                f"Production runner is already active; lock file: {lock_file}"
            ) from error

        lock_handle.seek(0)
        lock_handle.truncate()
        lock_handle.write(f"{getpid()}\n")
        lock_handle.flush()
        try:
            yield
        finally:
            flock(lock_handle.fileno(), LOCK_UN)
