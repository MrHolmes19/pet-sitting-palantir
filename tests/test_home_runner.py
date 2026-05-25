from logging import getLogger

import pytest

from pet_sitting_palantir.workflows.home_runner import (
    RunnerAlreadyActiveError,
    _run_continuously,
    _run_tick,
    _single_instance_lock,
    run_home_runner,
)
from pet_sitting_palantir.workflows.run_due_scopes import DueScopeFailure, DueScopeRunResult
from pet_sitting_palantir.workflows.scrape_and_store import StoredScrapeResult


def test_continuous_runner_retries_after_tick_error(caplog) -> None:
    attempted_max_pages = []
    sleep_delays = []

    def intermittently_offline_runner(*, max_pages):
        attempted_max_pages.append(max_pages)
        if len(attempted_max_pages) == 1:
            raise ConnectionError("offline")
        return DueScopeRunResult(
            status="nothing_due",
            scopes_due=0,
            scopes_succeeded=0,
            scopes_failed=0,
            results=(),
            failures=(),
        )

    def sleep_until_stopped(delay: float) -> None:
        sleep_delays.append(delay)
        if len(sleep_delays) == 2:
            raise KeyboardInterrupt

    caplog.set_level("ERROR", logger="test.home_runner")

    _run_continuously(
        max_pages=None,
        due_scope_runner=intermittently_offline_runner,
        sleep_for=sleep_until_stopped,
        clock=lambda: 1,
        runtime_logger=getLogger("test.home_runner"),
    )

    assert attempted_max_pages == [None, None]
    assert sleep_delays == [299, 299]
    assert "home_runner_tick_error error_type=ConnectionError" in caplog.text


def test_tick_logs_scope_failure_detail(caplog) -> None:
    caplog.set_level("ERROR", logger="test.home_runner")

    _run_tick(
        max_pages=None,
        due_scope_runner=lambda *, max_pages: DueScopeRunResult(
            status="failed",
            scopes_due=1,
            scopes_succeeded=0,
            scopes_failed=1,
            results=(),
            failures=(
                DueScopeFailure(
                    scope_name="all_nz",
                    error_message="Unexpected status code: 403",
                ),
            ),
        ),
        runtime_logger=getLogger("test.home_runner"),
    )

    assert "home_runner_tick_scope_failures scopes_due=1 scopes_failed=1" in caplog.text
    assert "home_runner_scope_failed scope_name=all_nz error=Unexpected status code: 403" in (
        caplog.text
    )


def test_tick_logs_successful_scope_detail(caplog) -> None:
    caplog.set_level("INFO", logger="test.home_runner")

    _run_tick(
        max_pages=None,
        due_scope_runner=lambda *, max_pages: DueScopeRunResult(
            status="success",
            scopes_due=1,
            scopes_succeeded=1,
            scopes_failed=0,
            results=(
                StoredScrapeResult(
                    scope_name="auckland_central",
                    run_id=11,
                    search_url="https://example.test/search",
                    pages_fetched=2,
                    listings_seen=36,
                    new_listings=1,
                    changed_listings=2,
                    missing_marked=0,
                    status="success",
                ),
            ),
            failures=(),
        ),
        runtime_logger=getLogger("test.home_runner"),
    )

    assert "home_runner_tick_complete status=success scopes_due=1 scopes_succeeded=1" in (
        caplog.text
    )
    assert (
        "home_runner_scope_complete scope_name=auckland_central status=success "
        "pages_fetched=2 listings_seen=36 new_listings=1 changed_listings=2 missing_marked=0"
    ) in caplog.text


def test_runner_startup_logs_selected_request_interval(monkeypatch, caplog, tmp_path) -> None:
    monkeypatch.setattr(
        "pet_sitting_palantir.workflows.home_runner._run_continuously",
        lambda *, max_pages: None,
    )
    caplog.set_level("INFO", logger="pet_sitting_palantir.workflows.home_runner")

    run_home_runner(lock_file=tmp_path / "home-runner.lock")

    assert "request_interval_seconds=0.5" in caplog.text


def test_single_instance_lock_rejects_parallel_runner(tmp_path) -> None:
    lock_file = tmp_path / "home-runner.lock"

    with _single_instance_lock(lock_file):
        active_runner_pid = lock_file.read_text()
        with pytest.raises(RunnerAlreadyActiveError, match="already active"):
            with _single_instance_lock(lock_file):
                raise AssertionError("a second runner must not acquire the lock")
        assert lock_file.read_text() == active_runner_pid
