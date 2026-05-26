import json

import pytest

from pet_sitting_palantir.alerts import (
    DEFAULT_ALERT_FILTER_DEFAULTS_PATH,
    DEFAULT_ALERT_FILTERS_PATH,
    load_alert_filters,
)


def test_configured_alert_filters_merge_local_defaults_with_named_overrides() -> None:
    configuration = json.loads(DEFAULT_ALERT_FILTERS_PATH.read_text())
    defaults = json.loads(DEFAULT_ALERT_FILTER_DEFAULTS_PATH.read_text())
    filters = load_alert_filters()

    assert len(filters) == len(configuration["filters"])
    configured = configuration["filters"][0]
    parsed = filters[0]
    assert parsed.name == configured["name"]
    assert parsed.enabled is defaults["enabled"]
    assert parsed.site_filter == configured["site_filter"]
    assert parsed.local_filter == {
        **defaults["local_filter"],
        **configured["local_filter"],
    }


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

    assert isinstance(defaults["enabled"], bool)
    assert isinstance(defaults["local_filter"], dict)
    assert set(defaults["delivery"]) == {"channels", "quiet_hours"}
