"""Continuous home-hosted production runner for database-backed scrape scopes."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from fcntl import LOCK_EX, LOCK_NB, LOCK_UN, flock
from logging import Logger, getLogger
from os import getpid
from pathlib import Path
from time import sleep, time

from pet_sitting_palantir.kiwihousesitters.constants import DEFAULT_MAX_PAGES
from pet_sitting_palantir.settings import (
    HOME_RUNNER_LOCK_FILE,
    HOME_RUNNER_TICK_INTERVAL_SECONDS,
    KIWIHOUSESITTERS_REQUEST_INTERVAL_SECONDS,
)
from pet_sitting_palantir.workflows.run_due_scopes import DueScopeRunResult, run_due_scrape_scopes

logger = getLogger(__name__)

DueScopeRunner = Callable[..., DueScopeRunResult]


class RunnerAlreadyActiveError(RuntimeError):
    """Raised when another home-hosted production runner owns the lock."""


def run_home_runner(
    *,
    max_pages: int | None = DEFAULT_MAX_PAGES,
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
    max_pages: int | None = DEFAULT_MAX_PAGES,
    tick_interval_seconds: int = HOME_RUNNER_TICK_INTERVAL_SECONDS,
    due_scope_runner: DueScopeRunner = run_due_scrape_scopes,
    sleep_for: Callable[[float], None] = sleep,
    clock: Callable[[], float] = time,
    runtime_logger: Logger = logger,
) -> None:
    """Run due-scope ticks forever, retrying after tick-level failures."""
    try:
        while True:
            _run_tick(
                max_pages=max_pages,
                due_scope_runner=due_scope_runner,
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
        return

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
        return

    if result.scopes_due:
        for stored_result in result.results:
            runtime_logger.info(
                "scope_ok name=%s pages=%s "
                "listings=%s new=%s changed=%s missing=%s",
                stored_result.scope_name,
                stored_result.pages_fetched,
                stored_result.listings_seen,
                stored_result.new_listings,
                stored_result.changed_listings,
                stored_result.missing_marked,
            )
        return

    runtime_logger.info("tick_ok status=%s", result.status)


def _seconds_until_next_tick(timestamp: float, tick_interval_seconds: int) -> float:
    remainder = timestamp % tick_interval_seconds
    return tick_interval_seconds if remainder == 0 else tick_interval_seconds - remainder


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
