from datetime import UTC, datetime
from logging import getLogger
from zoneinfo import ZoneInfo

import pytest

from pet_sitting_palantir.alerts import CreatedAlertEvent
from pet_sitting_palantir.workflows.deliver_alerts import AlertDeliverySummary
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
        alert_delivery_runner=_no_deliveries,
        sleep_for=sleep_until_stopped,
        clock=lambda: 1,
        runtime_logger=getLogger("test.home_runner"),
    )

    assert attempted_max_pages == [None, None]
    assert sleep_delays == [299, 299]
    assert "tick_fail type=ConnectionError error=offline retry=next_tick" in caplog.text


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
        alert_delivery_runner=_no_deliveries,
    )

    assert "tick_failed due=1 failed=1" in caplog.text
    assert "scope_fail name=all_nz error=Unexpected status code: 403" in (
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
                    alert_events=(_alert_event(),),
                ),
            ),
            failures=(),
        ),
        runtime_logger=getLogger("test.home_runner"),
        alert_delivery_runner=_no_deliveries,
    )

    assert (
        "scope_ok name=auckland_central "
        "pages=2 listings=36 new=1 changed=2 missing=0 alerts=1"
    ) in caplog.text
    assert (
        "alert_queued filter=test filter type=first_match listing=614587 "
        "channels=telegram,email deliver_after=2026-08-01T06:00:00+12:00 "
        "url=https://example.test/listing/614587"
    ) in caplog.text


def test_tick_logs_heartbeat_when_no_scope_is_due(caplog) -> None:
    caplog.set_level("INFO", logger="test.home_runner")

    _run_tick(
        max_pages=None,
        due_scope_runner=lambda *, max_pages: DueScopeRunResult(
            status="nothing_due",
            scopes_due=0,
            scopes_succeeded=0,
            scopes_failed=0,
            results=(),
            failures=(),
        ),
        runtime_logger=getLogger("test.home_runner"),
        alert_delivery_runner=_no_deliveries,
    )

    assert "tick_start" in caplog.text
    assert "tick_ok status=nothing_due" in caplog.text


def test_tick_delivers_after_new_events_are_persisted_in_same_tick() -> None:
    actions = []

    def scrape(*, max_pages):
        actions.append("scrape")
        return DueScopeRunResult(
            status="success",
            scopes_due=1,
            scopes_succeeded=1,
            scopes_failed=0,
            results=(),
            failures=(),
        )

    def deliver():
        actions.append("deliver")
        return _no_deliveries()

    _run_tick(
        max_pages=None,
        due_scope_runner=scrape,
        runtime_logger=getLogger("test.home_runner"),
        alert_delivery_runner=deliver,
    )

    assert actions == ["scrape", "deliver"]


def test_runner_startup_logs_selected_request_interval(monkeypatch, caplog, tmp_path) -> None:
    monkeypatch.setattr(
        "pet_sitting_palantir.workflows.home_runner._run_continuously",
        lambda *, max_pages: None,
    )
    caplog.set_level("INFO", logger="pet_sitting_palantir.workflows.home_runner")

    run_home_runner(lock_file=tmp_path / "home-runner.lock")

    assert "runner_start tick=300s request_delay=0.5s" in caplog.text


def test_single_instance_lock_rejects_parallel_runner(tmp_path) -> None:
    lock_file = tmp_path / "home-runner.lock"

    with _single_instance_lock(lock_file):
        active_runner_pid = lock_file.read_text()
        with pytest.raises(RunnerAlreadyActiveError, match="already active"):
            with _single_instance_lock(lock_file):
                raise AssertionError("a second runner must not acquire the lock")
        assert lock_file.read_text() == active_runner_pid


def test_stored_scrape_result_serializes_alert_event_count_without_preview_payload() -> None:
    result = StoredScrapeResult(
        scope_name="auckland_central",
        run_id=11,
        search_url="https://example.test/search",
        pages_fetched=1,
        listings_seen=1,
        new_listings=1,
        changed_listings=0,
        missing_marked=0,
        status="success",
        alert_events=(_alert_event(),),
    )

    payload = result.to_dict()

    assert payload["alerts_created"] == 1
    assert "alert_events" not in payload


def _alert_event() -> CreatedAlertEvent:
    return CreatedAlertEvent(
        id=17,
        listing_id=20,
        listing_external_id="614587",
        filter_name="test filter",
        event_type="first_match",
        target_channels=("telegram", "email"),
        deliver_after=datetime(2026, 7, 31, 18, tzinfo=UTC).astimezone(
            ZoneInfo("Pacific/Auckland")
        ),
        listing_url="https://example.test/listing/614587",
    )


def _no_deliveries() -> AlertDeliverySummary:
    return AlertDeliverySummary(
        deliveries_due=0,
        attempts_made=0,
        sent=0,
        failed=0,
        unconfigured=0,
        failures=(),
    )
