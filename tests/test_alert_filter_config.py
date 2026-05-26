import json
from datetime import time

import pytest

from pet_sitting_palantir.alerts import (
    DEFAULT_ALERT_FILTER_DEFAULTS_PATH,
    DEFAULT_ALERT_FILTERS_PATH,
    load_alert_filters,
)


def test_default_alert_filter_configuration_contains_post_luka() -> None:
    filters = load_alert_filters()

    assert len(filters) == 1
    post_luka = filters[0]
    assert post_luka.name == "Post Luka"
    assert post_luka.enabled is True
    assert post_luka.site_filter == {
        "state": "north-island",
        "region": "auckland",
        "subregion": "auckland-central",
    }
    assert post_luka.local_filter == {
        "date_window_match": "contained",
        "start_date_on_or_after": "2026-08-01",
        "end_date_on_or_before": "2026-11-30",
        "min_duration_days": 8,
        "max_duration_days": None,
        "allowed_islands": None,
        "allowed_regions": None,
        "allowed_subregions": None,
        "max_total_animals": None,
        "max_dogs": 2,
        "dogs_allowed": True,
        "cats_allowed": True,
        "fish_allowed": False,
        "birds_allowed": False,
        "rabbits_guinea_pigs_allowed": False,
        "chickens_ducks_geese_allowed": False,
        "farm_animals_allowed": False,
        "horses_allowed": False,
        "reptiles_allowed": False,
        "other_pets_allowed": False,
        "no_pets_allowed": False,
        "min_reply_rating_score": None,
        "allowed_house_types": None,
        "excluded_house_types": [],
        "include_keywords": [],
        "exclude_keywords": [],
    }
    assert post_luka.delivery.channels == ("telegram",)
    assert post_luka.delivery.quiet_hours.timezone == "Pacific/Auckland"
    assert post_luka.delivery.quiet_hours.start == time(hour=0)
    assert post_luka.delivery.quiet_hours.end == time(hour=6)


def test_load_alert_filters_rejects_duplicate_filter_names(tmp_path) -> None:
    configuration = json.loads(DEFAULT_ALERT_FILTERS_PATH.read_text())
    configuration["filters"].append(configuration["filters"][0])
    path = tmp_path / "alert_filters.json"
    path.write_text(json.dumps(configuration))

    with pytest.raises(ValueError, match="unique names"):
        load_alert_filters(path)


def test_load_alert_filters_rejects_invalid_delivery_quiet_hours(tmp_path) -> None:
    configuration = json.loads(DEFAULT_ALERT_FILTERS_PATH.read_text())
    configuration["filters"][0]["delivery"] = {"quiet_hours": {"start": "midnight"}}
    path = tmp_path / "alert_filters.json"
    path.write_text(json.dumps(configuration))

    with pytest.raises(ValueError, match="HH:MM"):
        load_alert_filters(path)


def test_load_alert_filters_rejects_unknown_local_override(tmp_path) -> None:
    configuration = json.loads(DEFAULT_ALERT_FILTERS_PATH.read_text())
    configuration["filters"][0]["local_filter"]["unsupported_rule"] = True
    path = tmp_path / "alert_filters.json"
    path.write_text(json.dumps(configuration))

    with pytest.raises(ValueError, match="unexpected fields"):
        load_alert_filters(path)


def test_default_file_contains_values_for_all_supported_local_fields() -> None:
    defaults = json.loads(DEFAULT_ALERT_FILTER_DEFAULTS_PATH.read_text())

    assert defaults["local_filter"]["max_duration_days"] is None
    assert defaults["local_filter"]["excluded_house_types"] == []
