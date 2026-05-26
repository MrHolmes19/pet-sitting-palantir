"""Channel-independent matching and delivery timing for alert filters."""

from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pet_sitting_palantir.alerts.filter_config import AlertFilterDefinition, AlertQuietHours
from pet_sitting_palantir.kiwihousesitters.location_map import REGION_FILTERS, STATE_LABELS
from pet_sitting_palantir.storage.models import ListingRecord
from pet_sitting_palantir.utils.hashing import stable_content_hash

ANIMAL_PERMISSION_FIELDS = (
    ("dogs_count", "dogs_allowed"),
    ("cats_count", "cats_allowed"),
    ("fish_count", "fish_allowed"),
    ("birds_count", "birds_allowed"),
    ("rabbits_guinea_pigs_count", "rabbits_guinea_pigs_allowed"),
    ("chickens_ducks_geese_count", "chickens_ducks_geese_allowed"),
    ("farm_animals_count", "farm_animals_allowed"),
    ("horses_count", "horses_allowed"),
    ("reptiles_count", "reptiles_allowed"),
    ("other_pets_count", "other_pets_allowed"),
)
ALERT_FINGERPRINT_FIELDS = (
    "island",
    "region",
    "subregion",
    "city",
    "duration_days",
    "start_date",
    "end_date",
    "total_animals",
    *(field for field, _ in ANIMAL_PERMISSION_FIELDS),
    "no_pets",
)
SIT_LENGTH_RANGES = {
    "60": (0, 7),
    "61": (8, 14),
    "62": (15, 28),
    "63": (29, 60),
    "64": (61, None),
}


def listing_matches_filter(listing: ListingRecord, alert_filter: AlertFilterDefinition) -> bool:
    """Return whether a normalized listing qualifies for an enabled alert filter."""
    return (
        alert_filter.enabled
        and _matches_site_filter(listing, alert_filter.site_filter)
        and _matches_local_filter(listing, alert_filter.local_filter)
    )


def alert_fingerprint(listing: ListingRecord) -> str:
    """Hash only fields whose changes justify another alert event."""
    return stable_content_hash(
        {field: getattr(listing, field) for field in ALERT_FINGERPRINT_FIELDS}
    )


def deliver_after(detected_at: datetime, quiet_hours: AlertQuietHours) -> datetime:
    """Return the first delivery time, deferring events created in quiet hours."""
    if detected_at.tzinfo is None:
        raise ValueError("detected_at must include a timezone")

    timezone = ZoneInfo(quiet_hours.timezone)
    local_detected_at = detected_at.astimezone(timezone)
    local_start = local_detected_at.replace(
        hour=quiet_hours.start.hour,
        minute=quiet_hours.start.minute,
        second=0,
        microsecond=0,
    )
    local_end = local_detected_at.replace(
        hour=quiet_hours.end.hour,
        minute=quiet_hours.end.minute,
        second=0,
        microsecond=0,
    )

    if quiet_hours.start < quiet_hours.end:
        if local_start <= local_detected_at < local_end:
            return local_end
        return detected_at

    if local_detected_at >= local_start:
        return local_end + timedelta(days=1)
    if local_detected_at < local_end:
        return local_end
    return detected_at


def _matches_site_filter(listing: ListingRecord, site_filter: Mapping[str, Any]) -> bool:
    state = site_filter.get("state")
    if state is not None and listing.island != _state_label(state):
        return False

    region = site_filter.get("region")
    if region is not None and listing.region != _region_label(region):
        return False

    subregion = site_filter.get("subregion")
    if subregion is not None:
        if region is None:
            raise ValueError("subregion filters require a region")
        if listing.subregion != _subregion_label(region, subregion):
            return False

    sitlengths = site_filter.get("sitlengths")
    if sitlengths is not None and not _matches_sit_length(listing.duration_days, sitlengths):
        return False

    return True


def _matches_local_filter(listing: ListingRecord, local_filter: Mapping[str, Any]) -> bool:
    if not _matches_date_window(listing, local_filter):
        return False
    if not _matches_optional_minimum(listing.duration_days, local_filter.get("min_duration_days")):
        return False
    if not _matches_optional_maximum(listing.duration_days, local_filter.get("max_duration_days")):
        return False
    if not _matches_allowed_value(listing.island, local_filter.get("allowed_islands")):
        return False
    if not _matches_allowed_value(listing.region, local_filter.get("allowed_regions")):
        return False
    if not _matches_allowed_value(listing.subregion, local_filter.get("allowed_subregions")):
        return False
    if not _matches_optional_maximum(
        listing.total_animals, local_filter.get("max_total_animals")
    ):
        return False
    if not _matches_optional_maximum(listing.dogs_count, local_filter.get("max_dogs")):
        return False

    for count_field, permission_field in ANIMAL_PERMISSION_FIELDS:
        if getattr(listing, count_field) > 0 and not local_filter.get(permission_field, False):
            return False
    if listing.no_pets and not local_filter.get("no_pets_allowed", False):
        return False

    if not _matches_optional_minimum(
        listing.reply_rating_score,
        local_filter.get("min_reply_rating_score"),
    ):
        return False
    if not _matches_allowed_value(listing.house_type, local_filter.get("allowed_house_types")):
        return False
    if listing.house_type in local_filter.get("excluded_house_types", ()):
        return False

    listing_text = " ".join(
        value for value in (listing.title, listing.intro, listing.listing_tag) if value
    ).casefold()
    if any(
        keyword.casefold() not in listing_text
        for keyword in local_filter.get("include_keywords", ())
    ):
        return False
    if any(
        keyword.casefold() in listing_text for keyword in local_filter.get("exclude_keywords", ())
    ):
        return False

    return True


def _matches_date_window(listing: ListingRecord, local_filter: Mapping[str, Any]) -> bool:
    start_limit = _optional_date(local_filter.get("start_date_on_or_after"))
    end_limit = _optional_date(local_filter.get("end_date_on_or_before"))
    if start_limit is None and end_limit is None:
        return True

    mode = local_filter.get("date_window_match", "contained")
    if mode == "contained":
        if start_limit is not None and (
            listing.start_date is None or listing.start_date < start_limit
        ):
            return False
        if end_limit is not None and (listing.end_date is None or listing.end_date > end_limit):
            return False
        return True
    if mode == "overlaps":
        if start_limit is not None and (listing.end_date is None or listing.end_date < start_limit):
            return False
        if end_limit is not None and (
            listing.start_date is None or listing.start_date > end_limit
        ):
            return False
        return True
    raise ValueError(f"Unsupported local_filter.date_window_match: {mode}")


def _matches_optional_minimum(value: int | None, minimum: Any) -> bool:
    return minimum is None or (value is not None and value >= minimum)


def _matches_optional_maximum(value: int | None, maximum: Any) -> bool:
    return maximum is None or (value is not None and value <= maximum)


def _matches_allowed_value(value: str | None, allowed_values: Any) -> bool:
    return allowed_values is None or value in allowed_values


def _optional_date(value: Any) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("Alert filter date values must be ISO date strings")
    return date.fromisoformat(value)


def _matches_sit_length(duration_days: int | None, sitlengths: Any) -> bool:
    if not isinstance(sitlengths, str):
        raise TypeError("site_filter.sitlengths must be a string")
    try:
        minimum, maximum = SIT_LENGTH_RANGES[sitlengths]
    except KeyError as error:
        raise ValueError(f"Unsupported KiwiHouseSitters sitlengths filter: {sitlengths}") from error
    if duration_days is None or duration_days < minimum:
        return False
    return maximum is None or duration_days <= maximum


def _state_label(state: Any) -> str:
    try:
        return STATE_LABELS[state]
    except KeyError as error:
        raise ValueError(f"Unsupported KiwiHouseSitters state filter: {state}") from error


def _region_label(region: Any) -> str:
    try:
        return REGION_FILTERS[region].label
    except KeyError as error:
        raise ValueError(f"Unsupported KiwiHouseSitters region filter: {region}") from error


def _subregion_label(region: Any, subregion: Any) -> str:
    try:
        return REGION_FILTERS[region].subregions[subregion].label
    except KeyError as error:
        raise ValueError(
            f"Unsupported KiwiHouseSitters subregion filter: {region}/{subregion}"
        ) from error
