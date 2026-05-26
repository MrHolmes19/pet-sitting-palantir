from dataclasses import replace
from datetime import UTC, date, datetime, time

import pytest

from pet_sitting_palantir.alerts import (
    AlertDelivery,
    AlertFilterDefinition,
    AlertQuietHours,
    alert_fingerprint,
    deliver_after,
    listing_matches_filter,
)
from pet_sitting_palantir.storage.models import ListingRecord


def test_listing_matches_all_supported_local_rule_categories() -> None:
    assert listing_matches_filter(_listing(), _filter()) is True


@pytest.mark.parametrize(
    ("changes", "filter_changes"),
    [
        ({"island": "South Island"}, {}),
        ({"region": "Waikato"}, {}),
        ({"subregion": "North Shore City"}, {}),
        ({"start_date": date(2026, 7, 31)}, {}),
        ({"end_date": date(2026, 12, 1)}, {}),
        ({"duration_days": 7}, {}),
        ({"duration_days": 46}, {}),
        ({"total_animals": 5}, {}),
        ({"dogs_count": 3}, {}),
        ({"reply_rating_score": 4}, {}),
        ({"house_type": "Farm House"}, {}),
        ({"intro": "No internet is supplied."}, {}),
        ({"intro": "Wifi provided in a rural home."}, {}),
        ({"cats_count": 1}, {"cats_allowed": False}),
        ({"no_pets": True, "total_animals": 0, "dogs_count": 0}, {"no_pets_allowed": False}),
    ],
)
def test_listing_rejects_values_outside_local_rules(changes, filter_changes) -> None:
    assert (
        listing_matches_filter(
            replace(_listing(), **changes),
            _filter(local_changes=filter_changes),
        )
        is False
    )


@pytest.mark.parametrize(
    ("count_field", "allowed_field"),
    [
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
    ],
)
def test_each_animal_category_is_opt_in(count_field: str, allowed_field: str) -> None:
    animal_counts = {"dogs_count": 0, count_field: 1}
    listing = replace(_listing(), **animal_counts)
    local_changes = {"dogs_allowed": False, allowed_field: False}

    assert listing_matches_filter(listing, _filter(local_changes=local_changes)) is False
    assert (
        listing_matches_filter(
            listing,
            _filter(local_changes={**local_changes, allowed_field: True}),
        )
        is True
    )


def test_overlapping_date_window_matches_partial_intersection() -> None:
    listing = replace(
        _listing(),
        start_date=date(2026, 7, 20),
        end_date=date(2026, 8, 3),
    )

    assert (
        listing_matches_filter(
            listing,
            _filter(local_changes={"date_window_match": "overlaps"}),
        )
        is True
    )
    assert listing_matches_filter(listing, _filter()) is False


def test_site_sit_length_filter_can_be_evaluated_from_normalized_duration() -> None:
    assert listing_matches_filter(_listing(), _filter(site_changes={"sitlengths": "62"})) is True
    assert listing_matches_filter(_listing(), _filter(site_changes={"sitlengths": "60"})) is False


def test_alert_fingerprint_changes_only_for_alert_relevant_listing_fields() -> None:
    listing = _listing()

    assert alert_fingerprint(replace(listing, title="Changed title")) == alert_fingerprint(listing)
    assert alert_fingerprint(replace(listing, house_type="Flat")) == alert_fingerprint(listing)
    assert alert_fingerprint(replace(listing, start_date=date(2026, 8, 2))) != alert_fingerprint(
        listing
    )
    assert alert_fingerprint(replace(listing, cats_count=1)) != alert_fingerprint(listing)


def test_delivery_is_deferred_until_quiet_hours_end() -> None:
    quiet_hours = AlertQuietHours(timezone="Pacific/Auckland", start=time(0), end=time(6))
    detected_at = datetime(2026, 8, 1, 14, 30, tzinfo=UTC)

    assert deliver_after(detected_at, quiet_hours).isoformat() == "2026-08-02T06:00:00+12:00"


def test_delivery_supports_quiet_hours_crossing_midnight() -> None:
    quiet_hours = AlertQuietHours(timezone="Pacific/Auckland", start=time(22), end=time(6))
    detected_at = datetime(2026, 8, 1, 11, 30, tzinfo=UTC)

    assert deliver_after(detected_at, quiet_hours).isoformat() == "2026-08-02T06:00:00+12:00"


def _filter(
    *,
    local_changes: dict | None = None,
    site_changes: dict | None = None,
) -> AlertFilterDefinition:
    local_filter = {
        "date_window_match": "contained",
        "start_date_on_or_after": "2026-08-01",
        "end_date_on_or_before": "2026-11-30",
        "min_duration_days": 8,
        "max_duration_days": 45,
        "allowed_islands": ["North Island"],
        "allowed_regions": ["Auckland"],
        "allowed_subregions": ["Auckland - Central"],
        "max_total_animals": 4,
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
        "no_pets_allowed": True,
        "min_reply_rating_score": 5,
        "allowed_house_types": ["Duplex"],
        "excluded_house_types": ["Farm House"],
        "include_keywords": ["wifi"],
        "exclude_keywords": ["rural"],
    }
    local_filter.update(local_changes or {})
    site_filter = {
        "state": "north-island",
        "region": "auckland",
        "subregion": "auckland-central",
    }
    site_filter.update(site_changes or {})
    return AlertFilterDefinition(
        name="test filter",
        enabled=True,
        site_filter=site_filter,
        local_filter=local_filter,
        delivery=AlertDelivery(
            channels=("telegram", "email"),
            quiet_hours=AlertQuietHours(
                timezone="Pacific/Auckland",
                start=time(0),
                end=time(6),
            ),
        ),
    )


def _listing() -> ListingRecord:
    return ListingRecord(
        external_id="matching-listing",
        content_hash="hash-v1",
        island="North Island",
        region="Auckland",
        subregion="Auckland - Central",
        city="Stonefields",
        duration_days=21,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 22),
        house_type="Duplex",
        total_animals=1,
        dogs_count=1,
        reply_rating_score=10,
        listing_tag="Central sit",
        title="Auckland pet sit",
        intro="Fast wifi available.",
        url="https://example.test/listing/matching-listing",
    )
