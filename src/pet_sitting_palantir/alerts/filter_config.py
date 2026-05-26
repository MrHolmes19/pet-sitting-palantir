"""Loading of human-maintained alert filter definitions."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_ALERT_FILTERS_PATH = Path(__file__).parents[3] / "config" / "alert_filters.json"
DEFAULT_ALERT_FILTER_DEFAULTS_PATH = (
    Path(__file__).parents[3] / "config" / "alert_filter_defaults.json"
)


@dataclass(frozen=True)
class AlertQuietHours:
    """Local daily interval during which an alert delivery is withheld."""

    timezone: str
    start: time
    end: time


@dataclass(frozen=True)
class AlertDelivery:
    """Provider-independent delivery configuration for one alert filter."""

    channels: tuple[str, ...]
    quiet_hours: AlertQuietHours


@dataclass(frozen=True)
class AlertFilterDefinition:
    """One configured listing filter and its delivery policy."""

    name: str
    enabled: bool
    site_filter: Mapping[str, Any]
    local_filter: Mapping[str, Any]
    delivery: AlertDelivery


@dataclass(frozen=True)
class AlertFilterDefaults:
    """Default settings overridden by named alert filters."""

    enabled: bool
    local_filter: Mapping[str, Any]
    delivery: AlertDelivery


def load_alert_filters(
    path: Path = DEFAULT_ALERT_FILTERS_PATH,
    defaults_path: Path = DEFAULT_ALERT_FILTER_DEFAULTS_PATH,
) -> tuple[AlertFilterDefinition, ...]:
    """Read filter definitions and validate their envelope and delivery policy."""
    defaults = _parse_defaults(_load_json(defaults_path))
    raw_configuration = _load_json(path)
    configuration = _required_object(raw_configuration, "configuration")
    _require_exact_keys(configuration, {"filters"}, "configuration")
    raw_filters = configuration["filters"]
    if not isinstance(raw_filters, list):
        raise TypeError("configuration.filters must be an array")

    filters = tuple(
        _parse_filter(raw_filter, index, defaults) for index, raw_filter in enumerate(raw_filters)
    )
    names = [alert_filter.name for alert_filter in filters]
    if len(names) != len(set(names)):
        raise ValueError("configuration.filters must have unique names")

    return filters


def _parse_defaults(raw_defaults: Any) -> AlertFilterDefaults:
    label = "defaults"
    defaults = _required_object(raw_defaults, label)
    _require_exact_keys(defaults, {"enabled", "local_filter", "delivery"}, label)
    enabled = defaults["enabled"]
    if not isinstance(enabled, bool):
        raise TypeError(f"{label}.enabled must be a boolean")

    return AlertFilterDefaults(
        enabled=enabled,
        local_filter=_required_object(defaults["local_filter"], f"{label}.local_filter"),
        delivery=_parse_delivery(defaults["delivery"], label),
    )


def _parse_filter(
    raw_filter: Any,
    index: int,
    defaults: AlertFilterDefaults,
) -> AlertFilterDefinition:
    label = f"configuration.filters[{index}]"
    configuration = _required_object(raw_filter, label)
    _require_allowed_keys(
        configuration,
        {"name", "enabled", "site_filter", "local_filter", "delivery"},
        label,
    )
    _require_fields(configuration, {"name", "site_filter"}, label)

    name = configuration["name"]
    if not isinstance(name, str) or not name.strip():
        raise TypeError(f"{label}.name must be a non-empty string")
    enabled = configuration.get("enabled", defaults.enabled)
    if not isinstance(enabled, bool):
        raise TypeError(f"{label}.enabled must be a boolean")
    local_label = f"{label}.local_filter"
    local_overrides = _required_object(configuration.get("local_filter", {}), local_label)
    _require_allowed_keys(local_overrides, set(defaults.local_filter), local_label)
    local_filter = {**defaults.local_filter, **local_overrides}
    delivery = (
        defaults.delivery
        if "delivery" not in configuration
        else _parse_delivery_override(configuration["delivery"], defaults.delivery, label)
    )

    return AlertFilterDefinition(
        name=name,
        enabled=enabled,
        site_filter=_required_object(configuration["site_filter"], f"{label}.site_filter"),
        local_filter=local_filter,
        delivery=delivery,
    )


def _parse_delivery(raw_delivery: Any, filter_label: str) -> AlertDelivery:
    label = f"{filter_label}.delivery"
    delivery = _required_object(raw_delivery, label)
    _require_exact_keys(delivery, {"channels", "quiet_hours"}, label)

    raw_channels = delivery["channels"]
    if not isinstance(raw_channels, list) or not raw_channels:
        raise TypeError(f"{label}.channels must be a non-empty array")
    if any(not isinstance(channel, str) or not channel.strip() for channel in raw_channels):
        raise TypeError(f"{label}.channels entries must be non-empty strings")
    if len(raw_channels) != len(set(raw_channels)):
        raise ValueError(f"{label}.channels must not contain duplicates")

    return AlertDelivery(
        channels=tuple(raw_channels),
        quiet_hours=_parse_quiet_hours(delivery["quiet_hours"], label),
    )


def _parse_delivery_override(
    raw_delivery: Any,
    defaults: AlertDelivery,
    filter_label: str,
) -> AlertDelivery:
    label = f"{filter_label}.delivery"
    override = _required_object(raw_delivery, label)
    _require_allowed_keys(override, {"channels", "quiet_hours"}, label)
    quiet_hours_override = _required_object(
        override.get("quiet_hours", {}),
        f"{label}.quiet_hours",
    )
    _require_allowed_keys(
        quiet_hours_override,
        {"timezone", "start", "end"},
        f"{label}.quiet_hours",
    )

    merged_delivery = {
        "channels": override["channels"] if "channels" in override else list(defaults.channels),
        "quiet_hours": {
            "timezone": quiet_hours_override.get("timezone", defaults.quiet_hours.timezone),
            "start": quiet_hours_override.get(
                "start",
                defaults.quiet_hours.start.strftime("%H:%M"),
            ),
            "end": quiet_hours_override.get(
                "end",
                defaults.quiet_hours.end.strftime("%H:%M"),
            ),
        },
    }
    return _parse_delivery(merged_delivery, filter_label)


def _parse_quiet_hours(raw_quiet_hours: Any, delivery_label: str) -> AlertQuietHours:
    label = f"{delivery_label}.quiet_hours"
    quiet_hours = _required_object(raw_quiet_hours, label)
    _require_exact_keys(quiet_hours, {"timezone", "start", "end"}, label)

    timezone = quiet_hours["timezone"]
    if not isinstance(timezone, str):
        raise TypeError(f"{label}.timezone must be a string")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"{label}.timezone is not recognized: {timezone}") from error

    start = _parse_time(quiet_hours["start"], f"{label}.start")
    end = _parse_time(quiet_hours["end"], f"{label}.end")
    if start == end:
        raise ValueError(f"{label}.start and {label}.end must differ")

    return AlertQuietHours(timezone=timezone, start=start, end=end)


def _parse_time(value: Any, label: str) -> time:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be an HH:MM string")
    try:
        parsed = time.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label} must be an HH:MM string") from error
    if parsed.second or parsed.microsecond or len(value) != 5:
        raise ValueError(f"{label} must be an HH:MM string")
    return parsed


def _required_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return value


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid alert filter JSON in {path}: {error.msg}") from error


def _require_exact_keys(configuration: Mapping[str, Any], keys: set[str], label: str) -> None:
    missing = keys - configuration.keys()
    if missing:
        raise ValueError(f"{label} is missing fields: {', '.join(sorted(missing))}")
    _require_allowed_keys(configuration, keys, label)


def _require_allowed_keys(configuration: Mapping[str, Any], keys: set[str], label: str) -> None:
    unexpected = configuration.keys() - keys
    if unexpected:
        raise ValueError(f"{label} has unexpected fields: {', '.join(sorted(unexpected))}")


def _require_fields(configuration: Mapping[str, Any], fields: set[str], label: str) -> None:
    missing = fields - configuration.keys()
    if missing:
        raise ValueError(f"{label} is missing fields: {', '.join(sorted(missing))}")
