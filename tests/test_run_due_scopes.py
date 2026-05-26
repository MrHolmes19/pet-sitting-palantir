from datetime import datetime
from zoneinfo import ZoneInfo

from pet_sitting_palantir.storage import ScrapeScope
from pet_sitting_palantir.workflows.run_due_scopes import (
    DueScopeRunResult,
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
        lambda connection, max_pages, scraper: expected_result,
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


def _scope(name: str, site_filter: dict[str, str]) -> ScrapeScope:
    return ScrapeScope(
        id=1,
        name=name,
        enabled=True,
        interval_minutes=5,
        missing_threshold_runs=3,
        site_filter=site_filter,
        last_attempt_at=None,
        last_success_at=None,
    )
