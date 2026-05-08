from pet_sitting_palantir.storage import ScrapeScope
from pet_sitting_palantir.workflows.run_due_scopes import _select_broadest_due_scopes


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
