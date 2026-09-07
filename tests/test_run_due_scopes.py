from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from pet_sitting_palantir.storage import ScrapeScope
from pet_sitting_palantir.workflows.run_due_scopes import (
    DueScopeRunResult,
    _scopes_ready_for_attempt,
    _select_broadest_due_scopes,
    run_due_scrape_scopes,
)

NEW_ZEALAND_TIME_ZONE = ZoneInfo("Pacific/Auckland")


def test_run_due_scrape_scopes_pauses_during_new_zealand_quiet_hours(monkeypatch) -> None:
    def unexpected_database_connection(database_url=None):
        raise AssertionError("quiet-hours runs should not connect to Postgres")

    monkeypatch.setattr(
        "pet_sitting_palantir.workflows.run_due_scopes.connect_database",
        unexpected_database_connection,
    )

    result = run_due_scrape_scopes(
        current_time=datetime(2026, 5, 24, 5, 59, tzinfo=NEW_ZEALAND_TIME_ZONE)
    )

    assert result.status == "quiet_hours"
    assert result.scopes_due == 0
    assert result.scopes_succeeded == 0
    assert result.scopes_failed == 0


def test_run_due_scrape_scopes_pauses_from_midnight(monkeypatch) -> None:
    def unexpected_database_connection(database_url=None):
        raise AssertionError("quiet-hours runs should not connect to Postgres")

    monkeypatch.setattr(
        "pet_sitting_palantir.workflows.run_due_scopes.connect_database",
        unexpected_database_connection,
    )

    result = run_due_scrape_scopes(
        current_time=datetime(2026, 5, 24, 0, 0, tzinfo=NEW_ZEALAND_TIME_ZONE)
    )

    assert result.status == "quiet_hours"


def test_run_due_scrape_scopes_resumes_at_six_am_new_zealand_time(monkeypatch) -> None:
    class FakeConnection:
        closed = False

        def close(self) -> None:
            self.closed = True

    connection = FakeConnection()
    expected_result = DueScopeRunResult(
        status="nothing_due",
        scopes_due=0,
        scopes_succeeded=0,
        scopes_failed=0,
        results=(),
        failures=(),
    )

    monkeypatch.setattr(
        "pet_sitting_palantir.workflows.run_due_scopes.connect_database",
        lambda database_url=None: connection,
    )
    monkeypatch.setattr(
        "pet_sitting_palantir.workflows.run_due_scopes.run_due_scrape_scopes_with_connection",
        lambda connection, max_pages, scraper, current_time: expected_result,
    )

    result = run_due_scrape_scopes(
        current_time=datetime(2026, 5, 24, 6, 0, tzinfo=NEW_ZEALAND_TIME_ZONE)
    )

    assert result is expected_result
    assert connection.closed is True


def test_select_broadest_due_scopes_prefers_all_nz_over_overlapping_scopes() -> None:
    scopes = (
        _scope(
            "auckland_central",
            {"state": "north-island", "region": "auckland", "subregion": "auckland-central"},
        ),
        _scope(
            "north_shore_city",
            {"state": "north-island", "region": "auckland", "subregion": "north-shore-city"},
        ),
        _scope("auckland_region", {"state": "north-island", "region": "auckland"}),
        _scope("north_island", {"state": "north-island"}),
        _scope("all_nz", {}),
    )

    selected = _select_broadest_due_scopes(scopes)

    assert [scope.name for scope in selected] == ["all_nz"]


def test_select_broadest_due_scopes_keeps_disjoint_islands() -> None:
    scopes = (
        _scope("north_island", {"state": "north-island"}),
        _scope("south_island", {"state": "south-island"}),
        _scope("auckland_region", {"state": "north-island", "region": "auckland"}),
    )

    selected = _select_broadest_due_scopes(scopes)

    assert [scope.name for scope in selected] == ["north_island", "south_island"]


def test_select_broadest_due_scopes_prefers_due_region_over_due_subregions() -> None:
    scopes = (
        _scope(
            "auckland_central",
            {"state": "north-island", "region": "auckland", "subregion": "auckland-central"},
        ),
        _scope(
            "north_shore_city",
            {"state": "north-island", "region": "auckland", "subregion": "north-shore-city"},
        ),
        _scope("auckland_region", {"state": "north-island", "region": "auckland"}),
        _scope("wellington", {"state": "north-island", "region": "wellington"}),
    )

    selected = _select_broadest_due_scopes(scopes)

    assert [scope.name for scope in selected] == ["auckland_region", "wellington"]


def test_recently_failed_broad_scope_cools_down_without_hiding_narrow_scope() -> None:
    now = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)
    all_nz = _scope(
        "all_nz",
        {},
        interval_minutes=1440,
        last_attempt_at=now - timedelta(minutes=5),
        last_success_at=now - timedelta(days=2),
    )
    auckland_central = _scope(
        "auckland_central",
        {"state": "north-island", "region": "auckland", "subregion": "auckland-central"},
        interval_minutes=5,
        last_attempt_at=now - timedelta(minutes=10),
        last_success_at=now - timedelta(minutes=15),
    )

    ready = _scopes_ready_for_attempt(
        (auckland_central, all_nz),
        current_time=now,
    )
    selected = _select_broadest_due_scopes(ready)

    assert [scope.name for scope in selected] == ["auckland_central"]


def test_failed_broad_scope_becomes_ready_after_maximum_cooldown() -> None:
    now = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)
    all_nz = _scope(
        "all_nz",
        {},
        interval_minutes=1440,
        last_attempt_at=now - timedelta(minutes=60),
        last_success_at=now - timedelta(days=2),
    )

    assert _scopes_ready_for_attempt((all_nz,), current_time=now) == (all_nz,)


def test_successful_scope_is_not_put_in_failure_cooldown() -> None:
    now = datetime(2026, 9, 8, 10, 0, tzinfo=UTC)
    scope = _scope(
        "auckland_central",
        {"state": "north-island", "region": "auckland", "subregion": "auckland-central"},
        last_attempt_at=now - timedelta(minutes=6),
        last_success_at=now - timedelta(minutes=5),
    )

    assert _scopes_ready_for_attempt((scope,), current_time=now) == (scope,)


def _scope(
    name: str,
    site_filter: dict[str, str],
    *,
    interval_minutes: int = 5,
    last_attempt_at: datetime | None = None,
    last_success_at: datetime | None = None,
) -> ScrapeScope:
    return ScrapeScope(
        id=1,
        name=name,
        enabled=True,
        interval_minutes=interval_minutes,
        missing_threshold_runs=3,
        site_filter=site_filter,
        last_attempt_at=last_attempt_at,
        last_success_at=last_success_at,
    )
